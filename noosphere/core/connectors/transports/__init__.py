"""Transport handlers for the manifest-driven adapter framework.

A Transport implements the actual mechanics of talking to a source — running
a CLI subprocess, calling an MCP tool, hitting an HTTP endpoint, parsing a
forwarded email, or reading a file. Each transport exposes two operations:

- ``check_auth(config)`` — validate the transport is configured and authorised
  to fetch (binary on PATH, OAuth token valid, MCP server reachable, etc.)
- ``fetch(config, op)`` — execute one ingest operation defined by the manifest
  and return a list of raw record dicts. Mapping records onto IngestDoc happens
  in ``ManifestConnector``, so transports stay protocol-pure.

The framework is intentionally additive: existing Python connectors (file
upload, URL, RSS, Twitter ZIP, Notion ZIP, chat capture, directory sync)
continue to live in sibling modules and don't go through transports. New
sources that talk to external systems via standardised protocols use a
manifest + transport instead of bespoke connector code.
"""

from noosphere.core.connectors.transports.cli import CLITransport


_TRANSPORTS = {
    "cli": CLITransport(),
}


def get_transport(name: str):
    """Return a transport handler by name, or None if unknown."""
    return _TRANSPORTS.get(name)


def all_transports() -> dict:
    """Return all registered transports keyed by name."""
    return dict(_TRANSPORTS)


__all__ = ["CLITransport", "get_transport", "all_transports"]
