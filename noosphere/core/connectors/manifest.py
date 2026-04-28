"""Manifest-driven adapter framework.

A *manifest* is a TOML file that declares how to ingest from one external
source: which **transport** to use (CLI, MCP, REST, email, file), how to
authenticate, what operations to run, and how to map fetched records onto
``IngestDoc``. Adding a new source is writing a manifest, not writing a
Python connector module.

Why TOML: stdlib-only (``tomllib``, no extra deps), comment-friendly,
nested-structure-friendly, and clearly the lowest-friction format for a
file humans will edit by hand.

Loaded manifests are wrapped by ``ManifestConnector``, which adheres to the
existing ``Connector`` Protocol — so the registry, scheduler, and UI don't
need to distinguish manifest-driven adapters from the older Python
connectors. Both shapes coexist; manifests are the additive path for new
sources.
"""

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import tomllib

from noosphere.core.connectors.base import (
    ConnectorResult,
    IngestDoc,
    SOURCE_KIND_USER_CAPTURE,
)


# Keys in a manifest [[ingest]] block that map record fields to IngestDoc fields.
# Anything else in the block is opaque to the framework and forwarded to the
# transport handler verbatim (e.g. CLI gets cmd, record_path, timeout_seconds).
_FIELD_MAP_KEYS = frozenset({
    "title_field", "content_field", "url_field",
    "external_id_field", "created_at_field", "tags_field",
    "author_field",
})


@dataclass
class IngestOp:
    """One operation a transport executes per ``run()``.

    ``transport_op`` is whatever shape the chosen transport understands —
    for CLI that means ``{"cmd": [...], "record_path": [...]}``; for REST
    it would be ``{"method": "GET", "path": "/issues", ...}``. The
    framework does not introspect it.

    ``field_map`` translates record keys into IngestDoc fields. Keys are
    bare names (``title``, ``content``, ``url``, ``external_id``,
    ``created_at``, ``tags``, ``author``); values are the corresponding
    keys in the fetched record dict.
    """

    transport_op: dict
    field_map: dict
    source_kind: str | None = None
    doc_type: str = "doc"


@dataclass
class Manifest:
    """A parsed adapter manifest."""

    kind: str
    display_name: str
    transport: str
    default_source_kind: str = SOURCE_KIND_USER_CAPTURE
    supports_incremental: bool = False
    supports_oauth: bool = False
    default_cron: str | None = None
    transport_config: dict = field(default_factory=dict)
    ingest_ops: list[IngestOp] = field(default_factory=list)


class ManifestError(ValueError):
    """Raised when a manifest file is missing required fields or malformed."""


def load_manifest(path: str | Path) -> Manifest:
    """Parse a TOML manifest file into a ``Manifest``."""
    path = Path(path)
    with open(path, "rb") as f:
        data = tomllib.load(f)
    if "kind" not in data or "transport" not in data:
        raise ManifestError(f"{path}: manifest must declare 'kind' and 'transport'")
    ops = []
    for raw_op in data.get("ingest", []):
        if not isinstance(raw_op, dict):
            raise ManifestError(f"{path}: each [[ingest]] entry must be a table")
        transport_op = {
            k: v for k, v in raw_op.items()
            if k not in _FIELD_MAP_KEYS and k not in ("source_kind", "doc_type")
        }
        field_map = {
            k.removesuffix("_field"): v
            for k, v in raw_op.items()
            if k in _FIELD_MAP_KEYS
        }
        ops.append(IngestOp(
            transport_op=transport_op,
            field_map=field_map,
            source_kind=raw_op.get("source_kind"),
            doc_type=raw_op.get("doc_type", "doc"),
        ))
    return Manifest(
        kind=data["kind"],
        display_name=data.get("display_name", data["kind"]),
        transport=data["transport"],
        default_source_kind=data.get("default_source_kind", SOURCE_KIND_USER_CAPTURE),
        supports_incremental=bool(data.get("supports_incremental", False)),
        supports_oauth=bool(data.get("supports_oauth", False)),
        default_cron=data.get("default_cron"),
        transport_config=dict(data.get("transport_config", {})),
        ingest_ops=ops,
    )


def _record_to_doc(record: dict, op: IngestOp, default_source_kind: str) -> IngestDoc:
    def get(key_name: str) -> Any:
        record_key = op.field_map.get(key_name)
        if not record_key:
            return None
        return record.get(record_key)

    raw_id = get("external_id")
    return IngestDoc(
        title=str(get("title")) if get("title") is not None else None,
        content=str(get("content") or ""),
        source_url=str(get("url")) if get("url") is not None else None,
        author=str(get("author")) if get("author") is not None else None,
        external_id=str(raw_id) if raw_id is not None else None,
        source_kind=op.source_kind or default_source_kind,
        metadata={"raw": record},
    )


class ManifestConnector:
    """A ``Connector`` whose behaviour is declared by a manifest.

    Adheres to the ``Connector`` Protocol so the registry, scheduler, and
    UI treat it identically to the Python-coded connectors. Dispatches
    actual fetching to the transport handler named by ``manifest.transport``.
    """

    def __init__(self, manifest: Manifest):
        self._manifest = manifest
        self.kind = manifest.kind
        self.default_source_kind = manifest.default_source_kind
        self.supports_incremental = manifest.supports_incremental
        self.supports_oauth = manifest.supports_oauth

    @property
    def display_name(self) -> str:
        return self._manifest.display_name

    @property
    def transport(self) -> str:
        return self._manifest.transport

    def test_connection(self, cfg: dict, credentials: dict | None = None) -> dict:
        # Imported lazily to avoid a registry/runtime import cycle when the
        # transports module itself wants to import from manifest.
        from noosphere.core.connectors.transports import get_transport

        transport = get_transport(self._manifest.transport)
        if transport is None:
            return {"ok": False, "detail": f"unknown transport: {self._manifest.transport}"}
        config = {**self._manifest.transport_config, **(cfg or {})}
        return transport.check_auth(config)

    def run(
        self,
        corpus_id: str,
        cfg: dict,
        credentials: dict | None = None,
        since: datetime | None = None,
    ) -> ConnectorResult:
        from noosphere.core.connectors.transports import get_transport
        from noosphere.core.ingest import ingest_text

        result = ConnectorResult()
        transport = get_transport(self._manifest.transport)
        if transport is None:
            result.error = f"unknown transport: {self._manifest.transport}"
            return result
        config = {**self._manifest.transport_config, **(cfg or {})}
        errors: list[str] = []
        for op in self._manifest.ingest_ops:
            try:
                records = transport.fetch(config, op.transport_op)
            except Exception as e:
                result.error = str(e)
                return result
            for record in records:
                result.fetched += 1
                if not isinstance(record, dict):
                    result.skipped += 1
                    continue
                try:
                    doc = _record_to_doc(record, op, self._manifest.default_source_kind)
                    if not doc.content.strip() and not (doc.title or "").strip():
                        result.skipped += 1
                        continue
                    ingest_text(
                        corpus_id,
                        title=(doc.title or "(untitled)"),
                        content=doc.content,
                        doc_type=op.doc_type,
                        source_kind=doc.source_kind or self._manifest.default_source_kind,
                        metadata={
                            "external_id": doc.external_id,
                            "source_url": doc.source_url,
                            "author": doc.author,
                            "adapter_kind": self.kind,
                        },
                    )
                    result.ingested += 1
                except Exception as e:
                    result.skipped += 1
                    errors.append(str(e))
        if errors:
            result.detail["errors"] = errors[:10]  # cap to keep the audit row small
        return result

    def default_cron(self) -> str | None:
        return self._manifest.default_cron


def discover_bundled_manifests() -> list[ManifestConnector]:
    """Load every ``*.toml`` manifest bundled with the package.

    Manifests live in ``noosphere/core/connectors/manifests/``. Failures to
    parse a manifest are logged and the manifest is skipped — one bad file
    must not break the registry.
    """
    manifests_dir = Path(__file__).parent / "manifests"
    if not manifests_dir.exists():
        return []
    out: list[ManifestConnector] = []
    for path in sorted(manifests_dir.glob("*.toml")):
        try:
            m = load_manifest(path)
        except Exception:
            # Bad manifest — skip; surfaces during tests, not at import time.
            continue
        out.append(ManifestConnector(m))
    return out
