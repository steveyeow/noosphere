"""Tests for the manifest-driven adapter framework.

Covers:

- TOML manifest loading + validation
- ``discover_bundled_manifests`` picking up the bundled github.toml
- ``CLITransport.check_auth`` and ``CLITransport.fetch`` happy and error paths
- ``ManifestConnector.run`` end-to-end with subprocess mocked
"""

import json
from pathlib import Path
from unittest.mock import patch
from subprocess import CompletedProcess

import pytest

from noosphere.core.connectors import REGISTRY, get, all_kinds
from noosphere.core.connectors.manifest import (
    Manifest,
    ManifestConnector,
    ManifestError,
    discover_bundled_manifests,
    load_manifest,
)
from noosphere.core.connectors.transports.cli import CLITransport
from noosphere.core.corpus import create_corpus
from noosphere.core.ingest import get_documents


# --- manifest loading -------------------------------------------------------

def _write_manifest(tmp_path: Path, body: str) -> Path:
    p = tmp_path / "test.toml"
    p.write_text(body)
    return p


def test_load_manifest_minimal(tmp_path):
    path = _write_manifest(tmp_path, """
kind = "demo"
transport = "cli"

[[ingest]]
cmd = ["echo", "[]"]
title_field = "name"
content_field = "body"
""")
    m = load_manifest(path)
    assert m.kind == "demo"
    assert m.display_name == "demo"  # falls back to kind
    assert m.transport == "cli"
    assert len(m.ingest_ops) == 1
    op = m.ingest_ops[0]
    assert op.transport_op == {"cmd": ["echo", "[]"]}
    assert op.field_map == {"title": "name", "content": "body"}


def test_load_manifest_full(tmp_path):
    path = _write_manifest(tmp_path, """
kind = "github"
display_name = "GitHub"
transport = "cli"
default_source_kind = "user_capture"
supports_incremental = true
default_cron = "0 */6 * * *"

[transport_config]
binary = "gh"
auth_check_cmd = ["gh", "auth", "status"]

[[ingest]]
cmd = ["gh", "issue", "list", "--json", "number,title,body"]
title_field = "title"
content_field = "body"
external_id_field = "number"
doc_type = "issue"
source_kind = "user_capture"
""")
    m = load_manifest(path)
    assert m.display_name == "GitHub"
    assert m.supports_incremental is True
    assert m.default_cron == "0 */6 * * *"
    assert m.transport_config["binary"] == "gh"
    op = m.ingest_ops[0]
    assert op.doc_type == "issue"
    assert op.source_kind == "user_capture"
    assert op.field_map["external_id"] == "number"


def test_load_manifest_rejects_missing_required(tmp_path):
    path = _write_manifest(tmp_path, "kind = \"x\"\n")  # no transport
    with pytest.raises(ManifestError):
        load_manifest(path)


def test_discover_bundled_manifests_finds_github():
    connectors = discover_bundled_manifests()
    kinds = [c.kind for c in connectors]
    assert "github" in kinds
    gh = next(c for c in connectors if c.kind == "github")
    assert gh.transport == "cli"
    assert gh.default_cron() == "0 */6 * * *"


def test_registry_contains_manifest_connectors():
    # github is the bundled manifest; it must end up in the global registry
    # alongside the built-in Python connectors.
    assert "github" in all_kinds()
    assert "file_upload" in all_kinds()  # built-in still there
    gh = get("github")
    assert isinstance(gh, ManifestConnector)


# --- CLI transport ----------------------------------------------------------

def test_cli_transport_check_auth_missing_binary():
    t = CLITransport()
    out = t.check_auth({"binary": "this-binary-does-not-exist-anywhere"})
    assert out["ok"] is False
    assert "not on PATH" in out["detail"]


def test_cli_transport_check_auth_no_binary_field():
    t = CLITransport()
    out = t.check_auth({})
    assert out["ok"] is False


def test_cli_transport_check_auth_auth_check_fails():
    t = CLITransport()
    fake = CompletedProcess(args=[], returncode=1, stdout="", stderr="not logged in")
    with patch("shutil.which", return_value="/usr/bin/echo"), \
         patch("subprocess.run", return_value=fake):
        out = t.check_auth({"binary": "echo", "auth_check_cmd": ["echo", "x"]})
    assert out["ok"] is False
    assert "not logged in" in out["detail"]


def test_cli_transport_check_auth_happy(tmp_path):
    t = CLITransport()
    fake = CompletedProcess(args=[], returncode=0, stdout="ok", stderr="")
    with patch("shutil.which", return_value="/usr/bin/echo"), \
         patch("subprocess.run", return_value=fake):
        out = t.check_auth({"binary": "echo", "auth_check_cmd": ["echo", "x"]})
    assert out["ok"] is True


def test_cli_transport_fetch_parses_top_level_array():
    t = CLITransport()
    payload = [{"id": 1, "title": "a"}, {"id": 2, "title": "b"}]
    fake = CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload), stderr="")
    with patch("subprocess.run", return_value=fake):
        records = t.fetch({}, {"cmd": ["echo", "..."]})
    assert records == payload


def test_cli_transport_fetch_walks_record_path():
    t = CLITransport()
    payload = {"data": {"items": [{"id": 7}]}}
    fake = CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload), stderr="")
    with patch("subprocess.run", return_value=fake):
        records = t.fetch({}, {"cmd": ["x"], "record_path": ["data", "items"]})
    assert records == [{"id": 7}]


def test_cli_transport_fetch_filters_non_dict_entries():
    t = CLITransport()
    payload = [{"id": 1}, "string", 42, {"id": 2}]
    fake = CompletedProcess(args=[], returncode=0, stdout=json.dumps(payload), stderr="")
    with patch("subprocess.run", return_value=fake):
        records = t.fetch({}, {"cmd": ["x"]})
    assert records == [{"id": 1}, {"id": 2}]


def test_cli_transport_fetch_empty_stdout():
    t = CLITransport()
    fake = CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with patch("subprocess.run", return_value=fake):
        records = t.fetch({}, {"cmd": ["x"]})
    assert records == []


def test_cli_transport_fetch_command_failure_raises():
    t = CLITransport()
    fake = CompletedProcess(args=[], returncode=2, stdout="", stderr="boom")
    with patch("subprocess.run", return_value=fake):
        with pytest.raises(RuntimeError, match="exit 2"):
            t.fetch({}, {"cmd": ["x"]})


def test_cli_transport_fetch_invalid_json_raises():
    t = CLITransport()
    fake = CompletedProcess(args=[], returncode=0, stdout="not json", stderr="")
    with patch("subprocess.run", return_value=fake):
        with pytest.raises(RuntimeError, match="JSON"):
            t.fetch({}, {"cmd": ["x"]})


def test_cli_transport_fetch_missing_cmd_raises():
    t = CLITransport()
    with pytest.raises(ValueError, match="cmd"):
        t.fetch({}, {})


# --- ManifestConnector end-to-end ------------------------------------------

def _toy_manifest(tmp_path: Path) -> Path:
    return _write_manifest(tmp_path, """
kind = "toy"
transport = "cli"
default_source_kind = "user_capture"

[transport_config]
binary = "echo"

[[ingest]]
cmd = ["echo", "doesn't matter — mocked"]
title_field = "subject"
content_field = "body"
url_field = "link"
external_id_field = "id"
doc_type = "note"
""")


def test_manifest_connector_run_ingests_records(tmp_path):
    path = _toy_manifest(tmp_path)
    m = load_manifest(path)
    conn = ManifestConnector(m)
    corpus = create_corpus("ManifestTest")

    records = [
        {"id": 1, "subject": "First", "body": "alpha content", "link": "https://x/1"},
        {"id": 2, "subject": "Second", "body": "beta content", "link": "https://x/2"},
        # Should be skipped — no title and no content.
        {"id": 3, "subject": "", "body": "   "},
    ]
    fake = CompletedProcess(args=[], returncode=0, stdout=json.dumps(records), stderr="")
    with patch("subprocess.run", return_value=fake):
        result = conn.run(corpus["id"], cfg={})

    assert result.error is None
    assert result.fetched == 3
    assert result.ingested == 2
    assert result.skipped == 1

    docs = get_documents(corpus["id"])
    titles = sorted(d["title"] for d in docs)
    assert titles == ["First", "Second"]
    for d in docs:
        assert d["doc_type"] == "note"
        assert d["source_kind"] == "user_capture"


def test_manifest_connector_run_propagates_command_failure(tmp_path):
    path = _toy_manifest(tmp_path)
    m = load_manifest(path)
    conn = ManifestConnector(m)
    corpus = create_corpus("ManifestFail")
    fake = CompletedProcess(args=[], returncode=1, stdout="", stderr="api rate limit")
    with patch("subprocess.run", return_value=fake):
        result = conn.run(corpus["id"], cfg={})
    assert result.error is not None
    assert "rate limit" in result.error
    assert result.ingested == 0


def test_manifest_connector_test_connection_dispatches_to_transport(tmp_path):
    path = _toy_manifest(tmp_path)
    m = load_manifest(path)
    conn = ManifestConnector(m)
    out = conn.test_connection(cfg={})
    # `echo` is on PATH on every supported platform; no auth_check_cmd in the
    # toy manifest, so we expect a clean OK.
    assert out["ok"] is True


def test_manifest_connector_unknown_transport_returns_error(tmp_path):
    path = _write_manifest(tmp_path, """
kind = "broken"
transport = "carrier-pigeon"

[[ingest]]
cmd = ["x"]
""")
    m = load_manifest(path)
    conn = ManifestConnector(m)
    corpus = create_corpus("Broken")
    out = conn.test_connection(cfg={})
    assert out["ok"] is False
    result = conn.run(corpus["id"], cfg={})
    assert result.error is not None
    assert "carrier-pigeon" in result.error
