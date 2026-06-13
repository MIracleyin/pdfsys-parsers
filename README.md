# pdfsys-parsers

Parser submodule for [`MIracleyin/pdfsystem_mnbvc`](https://github.com/MIracleyin/pdfsystem_mnbvc). Hosts the four document-understanding packages plus the vendored pure-type contracts they share with the main repo.

| Package | Purpose |
|---|---|
| `pdfsys-types` | Vendored pure-type contracts (Backend, RegionType, BBox, Segment, ExtractedDoc, …). Zero runtime deps. Mirrors `pdfsys-core`'s top-level surface from the main repo. |
| `pdfsys-parser-mupdf` | Text-ok backend — PyMuPDF block extraction. |
| `pdfsys-parser-pipeline` | OCR pipeline backend — out-of-process HTTP client to `mineru-api` (pipeline mode). |
| `pdfsys-parser-vlm` | VLM backend — out-of-process HTTP client to `mineru-api` (vlm mode; MLX on Apple Silicon, vLLM on NVIDIA, transformers fallback). |
| `pdfsys-layout-analyser` | DocLayout-YOLO runner — emits `LayoutDocument` to a content-addressable cache. |

## Layout

```
pdfsys-parsers/
├── pyproject.toml         # uv workspace root
├── schema/
│   └── extracted_doc.v1.json   # wire-contract mirror (synced from main repo)
└── packages/
    ├── pdfsys-types/
    ├── pdfsys-parser-mupdf/
    ├── pdfsys-parser-pipeline/
    ├── pdfsys-parser-vlm/
    └── pdfsys-layout-analyser/
```

## Wire contract

`schema/extracted_doc.v1.json` is the JSON Schema for `ExtractedDoc`. It is **vendored from the main repo's `docs/schema/extracted_doc.v1.json`** and must stay byte-identical. Drift is caught by `scripts/check_schema_drift.sh` (TODO — to be added).

The Python dataclasses in `pdfsys-types` are kept in sync with the schema by `docs/schema/generate_dataclass.py` in the main repo. To regenerate the mirror after a schema change, update both repos together.

## Versioning

This repo is pinned by commit SHA in the main repo's [`system_release.toml`](https://github.com/MIracleyin/pdfsystem_mnbvc/blob/main/system_release.toml) under `[components.parsers]`. The tag `v0.1.0` marks the extraction baseline.

See [`docs/superpowers/specs/2026-05-30-parsers-submodule-design.md`](https://github.com/MIracleyin/pdfsystem_mnbvc/blob/main/docs/superpowers/specs/2026-05-30-parsers-submodule-design.md) in the main repo for the full versioning rationale.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
