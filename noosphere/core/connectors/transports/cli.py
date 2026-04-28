"""CLI transport — shell out to a binary, parse JSON output.

The right transport for sources whose canonical interface is a stable CLI
with reliable JSON output (``gh``, ``linear-cli``, ``gcloud``). Auth is
delegated to the binary's own auth flow (``gh auth login``, etc.) — we
inherit whatever credentials the user has configured at the OS level.

Manifest contract:

- ``transport_config.binary`` — required; the executable name (must be on PATH)
- ``transport_config.auth_check_cmd`` — optional list/str; runs as a
  pre-flight check during ``test_connection``
- per-op ``cmd`` — required list of argv tokens; the command to run
- per-op ``record_path`` — optional list of dict keys to walk into the
  parsed JSON before treating values as a list of records (default: root
  must already be a list)
"""

import json
import shlex
import shutil
import subprocess


class CLITransport:
    name = "cli"

    def check_auth(self, config: dict) -> dict:
        """Verify the binary is on PATH and (optionally) auth is set up."""
        binary = config.get("binary")
        if not binary:
            return {"ok": False, "detail": "manifest missing transport_config.binary"}
        if not shutil.which(binary):
            return {"ok": False, "detail": f"binary not on PATH: {binary}"}
        auth_cmd = config.get("auth_check_cmd")
        if auth_cmd:
            cmd_list = auth_cmd if isinstance(auth_cmd, list) else shlex.split(auth_cmd)
            try:
                proc = subprocess.run(
                    cmd_list, capture_output=True, text=True, timeout=15,
                )
            except subprocess.TimeoutExpired:
                return {"ok": False, "detail": "auth check timed out"}
            except Exception as e:
                return {"ok": False, "detail": f"auth check error: {e}"}
            if proc.returncode != 0:
                msg = (proc.stderr or proc.stdout or "").strip() or "non-zero exit"
                return {"ok": False, "detail": f"auth check failed: {msg}"}
        return {"ok": True, "detail": f"{binary} ready"}

    def fetch(self, config: dict, op: dict) -> list[dict]:
        """Run one ingest op; return parsed JSON records as a list of dicts.

        Raises ``RuntimeError`` if the command fails or output is not parseable
        JSON. Raises ``ValueError`` if the manifest is malformed.
        """
        cmd = op.get("cmd")
        if not cmd or not isinstance(cmd, list):
            raise ValueError("ingest op missing 'cmd' (must be a list of argv tokens)")
        timeout = int(op.get("timeout_seconds", config.get("timeout_seconds", 120)))
        try:
            proc = subprocess.run(
                cmd, capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"command timed out after {timeout}s")
        if proc.returncode != 0:
            msg = (proc.stderr or proc.stdout or "").strip() or "non-zero exit"
            raise RuntimeError(f"command failed (exit {proc.returncode}): {msg}")
        stdout = proc.stdout.strip()
        if not stdout:
            return []
        try:
            data = json.loads(stdout)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"could not parse JSON output: {e}")
        cursor = data
        for key in op.get("record_path", []):
            if not isinstance(cursor, dict):
                raise RuntimeError(f"record_path key {key!r} not reachable in output")
            cursor = cursor.get(key)
        if cursor is None:
            return []
        if isinstance(cursor, dict):
            return [cursor]
        if isinstance(cursor, list):
            return [r for r in cursor if isinstance(r, dict)]
        raise RuntimeError(f"expected list or dict at record path, got {type(cursor).__name__}")
