"""Mineru pipeline parser — talks to a ``mineru-api`` subprocess over HTTP.

**Out-of-process design.** Each :class:`PipelineParser` instance owns a
``mineru-api`` subprocess that loads mineru's pipeline-mode stack
(torch + DocLayout-YOLO + LayoutReader + PaddleOCR-derived models) in
isolation. The bench / CLI client never imports mineru, so its heavy
import surface cannot collide with mineru's multiprocessing/Metal
machinery on macOS.

See ``docs/superpowers/specs/2026-05-22-mineru-parsers-migration-design.md``.
The lifecycle mirrors :mod:`pdfsys_parser_vlm.extract`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import re
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

import httpx

from pdfsys_types import Backend, ExtractedDoc, PipelineConfig

_LOG = logging.getLogger(__name__)

_READY_TIMEOUT_S = 120.0
_READY_POLL_S = 1.0
_EXTRACT_TIMEOUT_S = 600.0


def _resolve_mineru_api_bin() -> str:
    on_path = shutil.which("mineru-api")
    if on_path:
        return on_path
    sibling = Path(sys.executable).parent / "mineru-api"
    if sibling.exists():
        return str(sibling)
    raise FileNotFoundError(
        "mineru-api not found on PATH or next to sys.executable. "
        "Install via `mineru[pipeline]` (or `mineru[vlm]`)."
    )


def _pick_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class PipelineParser:
    """Mineru pipeline-mode parser (out-of-process HTTP client)."""

    def __init__(self, config: PipelineConfig | None = None) -> None:
        self.config = config or PipelineConfig()
        self._proc: subprocess.Popen | None = None
        self._base_url: str | None = None

    def _ensure_server(self) -> str:
        if self._base_url is not None:
            return self._base_url

        # External server: when MINERU_PIPELINE_URL is set, point the
        # client at an existing mineru-api (e.g. a sibling container in
        # docker-compose) and skip the subprocess lifecycle entirely.
        # `close()` becomes a no-op because `self._proc` stays None.
        external = os.environ.get("MINERU_PIPELINE_URL")
        if external:
            base = external.rstrip("/")
            _LOG.info("using external mineru-api (pipeline) at %s", base)
            self._base_url = base
            return base

        bin_path = _resolve_mineru_api_bin()
        port = _pick_free_port()
        _LOG.info("starting mineru-api (pipeline) at 127.0.0.1:%d", port)
        # Force offline model resolution — see VLM parser for rationale.
        env = {**os.environ, "HF_HUB_OFFLINE": "1", "TRANSFORMERS_OFFLINE": "1"}
        self._proc = subprocess.Popen(
            [bin_path, "--host", "127.0.0.1", "--port", str(port)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            env=env,
        )

        base = f"http://127.0.0.1:{port}"
        deadline = time.monotonic() + _READY_TIMEOUT_S
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise RuntimeError(
                    f"mineru-api exited early (rc={self._proc.returncode})"
                )
            try:
                r = httpx.get(f"{base}/health", timeout=2.0)
                if r.status_code == 200:
                    _LOG.info(
                        "mineru-api ready at %s (pid=%s)", base, self._proc.pid
                    )
                    self._base_url = base
                    return base
            except httpx.HTTPError:
                pass
            time.sleep(_READY_POLL_S)

        self.close()
        raise TimeoutError(
            f"mineru-api did not become ready at {base} in {_READY_TIMEOUT_S}s"
        )

    def extract(self, pdf_path: Path) -> ExtractedDoc:
        pdf_path = Path(pdf_path)
        pdf_bytes = pdf_path.read_bytes()
        sha = hashlib.sha256(pdf_bytes).hexdigest()
        backend = "pipeline"

        url = self._ensure_server()

        with pdf_path.open("rb") as f:
            resp = httpx.post(
                f"{url}/file_parse",
                files={"files": (f"{sha}.pdf", f, "application/pdf")},
                data={
                    "backend": backend,
                    "lang_list": self.config.p_lang,
                    "formula_enable": str(self.config.formula_enable).lower(),
                    "table_enable": str(self.config.table_enable).lower(),
                    "return_md": "true",
                    "return_middle_json": "true",
                    "return_content_list": "true",
                    "return_layout_pdf": "false",
                    "return_images": str(self.config.return_images).lower(),
                },
                timeout=_EXTRACT_TIMEOUT_S,
            )

        if resp.status_code != 200:
            raise RuntimeError(
                f"mineru-api /file_parse returned {resp.status_code}: {resp.text[:200]}"
            )
        payload = resp.json()
        if payload.get("status") != "completed":
            raise RuntimeError(
                f"mineru-api task failed: {payload.get('error') or payload}"
            )

        results = payload.get("results") or {}
        if not results:
            raise RuntimeError("mineru-api returned no results")
        file_key = next(iter(results))
        result = results[file_key]
        markdown = result.get("md_content") or ""
        if not markdown:
            raise RuntimeError(
                f"mineru-api returned empty markdown for {file_key}"
            )

        stats: dict[str, Any] = {
            "mineru_backend": backend,
            "mineru_api_url": url,
            "mineru_version": payload.get("version"),
        }
        stats["middle_json_path"] = _persist_sidecar(
            result.get("middle_json"),
            self.config.output_dir,
            sha,
            f"{sha}_middle.json",
        )
        stats["content_list_path"] = _persist_sidecar(
            result.get("content_list"),
            self.config.output_dir,
            sha,
            f"{sha}_content_list.json",
        )
        stats["images_written"] = _persist_images(
            result.get("images"), self.config.output_dir, sha
        )

        return ExtractedDoc(
            sha256=sha,
            backend=Backend.PIPELINE,
            segments=(),
            markdown=markdown,
            stats=stats,
        )

    def close(self) -> None:
        proc = self._proc
        self._proc = None
        self._base_url = None
        if proc is None or proc.poll() is not None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        except Exception:
            pass

    def __del__(self) -> None:  # pragma: no cover
        self.close()


def _persist_sidecar(
    payload: Any,
    output_dir: Path | None,
    sha: str,
    filename: str,
) -> str | None:
    if output_dir is None or payload is None:
        return None
    out_dir = Path(output_dir) / sha
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / filename
    text = payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)
    out_path.write_text(text, encoding="utf-8")
    return str(out_path.relative_to(output_dir))


#: mineru-api returns each crop as ``data:<mime>;base64,<payload>``.
_DATA_URI_RE = re.compile(r"^data:[^;,]+;base64,(?P<payload>.*)$", re.DOTALL)


def _persist_images(
    images: Any,
    output_dir: Path | None,
    sha: str,
) -> int:
    """Write the returned figure crops to ``<output_dir>/<sha>/images/``.

    That is the layout ``content_list.json`` already refers to — its image
    entries carry ``img_path`` values like ``images/<hash>.jpg`` relative to
    the document directory — so writing them here is what makes those
    references resolve. Without this the crops exist only inside the
    mineru-api process's own filesystem, which in a container deployment is
    not the one the client can read.

    Returns the number of files written.
    """
    if output_dir is None or not isinstance(images, dict) or not images:
        return 0
    out_dir = Path(output_dir) / sha / "images"
    out_dir.mkdir(parents=True, exist_ok=True)
    written = 0
    for name, uri in images.items():
        match = _DATA_URI_RE.match(uri) if isinstance(uri, str) else None
        if match is None:
            _LOG.warning("skipping crop %r: not a base64 data URI", name)
            continue
        # Basename only: the filename comes from the server, and a crop is
        # never worth letting a path escape the output directory.
        try:
            (out_dir / Path(str(name)).name).write_bytes(
                base64.b64decode(match.group("payload"))
            )
        except (OSError, ValueError) as e:
            _LOG.warning("skipping crop %r: %s", name, e)
            continue
        written += 1
    return written
