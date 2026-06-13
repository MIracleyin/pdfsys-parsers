"""pdfsys-types — pure-type contracts vendored from the main ``pdfsys`` repo.

This package mirrors the read-only subset of ``pdfsys-core`` that the parser
backends need to produce :class:`ExtractedDoc`. It contains **only**
pure-Python dataclasses, enums, and configuration — no PDF, OCR, or ML
imports.

The package is hand-vendored from ``pdfsys-core`` (modules ``types.py``,
``layout.py``, ``extract.py``, ``config.py``). A future CI sync job will
diff it against the upstream source pinned in ``system_release.toml`` and
fail on drift.

Public surface mirrors the same symbols as ``pdfsys-core``'s top level,
so an existing ``from pdfsys_core import Backend, ExtractedDoc`` becomes
``from pdfsys_types import Backend, ExtractedDoc`` with no other change.
"""

from __future__ import annotations

from .config import (
    LayoutConfig,
    MupdfConfig,
    PathsConfig,
    PdfsysConfig,
    PipelineConfig,
    RouterConfig,
    RuntimeConfig,
    VlmConfig,
)
from .extract import ExtractedDoc, Segment, merge_segments_to_markdown
from .layout import BBox, LayoutDocument, LayoutPage, LayoutRegion, make_region_id
from .types import Backend, PdfRecord, RegionType

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # enums
    "Backend",
    "RegionType",
    # metadata
    "PdfRecord",
    # layout
    "BBox",
    "LayoutRegion",
    "LayoutPage",
    "LayoutDocument",
    "make_region_id",
    # extract
    "Segment",
    "ExtractedDoc",
    "merge_segments_to_markdown",
    # config
    "PdfsysConfig",
    "PathsConfig",
    "RouterConfig",
    "LayoutConfig",
    "MupdfConfig",
    "PipelineConfig",
    "VlmConfig",
    "RuntimeConfig",
]
