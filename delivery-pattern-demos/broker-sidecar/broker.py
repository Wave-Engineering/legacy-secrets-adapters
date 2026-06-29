#!/usr/bin/env python3
"""broker.py — the generalized secret-broker sidecar.

Authenticates to OpenBao/Vault, fetches a secret from a KV v2 path, renders it through a
Jinja2 template into a file the legacy app reads, and watches for new versions (rotation).
On each poll cycle, if the secret version has changed, the broker re-renders the template.

This generalizes the dynamic-credential-shim's one-shot fetch into a sidecar that:
  1. Supports ANY secret shape (not just database credentials)
  2. Renders through a template (the app's config format stays unchanged)
  3. Polls for rotation and re-renders automatically
  4. Logs lifecycle events (fetch, render, rotation detected)

Bootstrap secret: the OpenBao token below is an OBVIOUS dev value and is out of scope — see
README "Bootstrap secret — out of scope".
"""
import json
import os
import signal
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

try:
    import jinja2
except ImportError:
    sys.exit("broker: jinja2 required — pip install jinja2")

HERE = Path(__file__).resolve().parent

# --- Configuration (env or defaults pinned to the local demo container) --------
BAO_ADDR = os.environ.get("BROKER_BAO_ADDR", "http://127.0.0.1:58201")
BAO_TOKEN = os.environ.get("BROKER_BAO_TOKEN", "dev-only-root-token")  # BOOTSTRAP SECRET
KV_MOUNT = os.environ.get("BROKER_KV_MOUNT", "secret")
KV_PATH = os.environ.get("BROKER_KV_PATH", "apps/legacy-db")
TEMPLATE_PATH = Path(os.environ.get("BROKER_TEMPLATE", str(HERE / "templates" / "db.conf.j2")))
OUTPUT_PATH = Path(os.environ.get("BROKER_OUTPUT", str(HERE / "run" / "db.conf")))
POLL_INTERVAL = int(os.environ.get("BROKER_POLL_INTERVAL", "2"))

_running = True


def _signal_handler(signum, frame):
    global _running
    _running = False


signal.signal(signal.SIGTERM, _signal_handler)
signal.signal(signal.SIGINT, _signal_handler)


def _bao_request(path: str) -> dict:
    """Make an HTTP request to the OpenBao API."""
    url = f"{BAO_ADDR}/v1/{path}"
    req = urllib.request.Request(url, headers={"X-Vault-Token": BAO_TOKEN})
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"OpenBao API error {e.code}: {body}") from e
    except urllib.error.URLError as e:
        raise RuntimeError(f"Cannot reach OpenBao at {BAO_ADDR}: {e.reason}") from e


def fetch_secret() -> tuple:
    """Fetch the secret data and its version from KV v2."""
    resp = _bao_request(f"{KV_MOUNT}/data/{KV_PATH}")
    data = resp["data"]["data"]
    version = resp["data"]["metadata"]["version"]
    return data, version


def render_template(secret_data: dict) -> str:
    """Render the Jinja2 template with the secret data."""
    template_text = TEMPLATE_PATH.read_text()
    env = jinja2.Environment(
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
    )
    template = env.from_string(template_text)
    return template.render(**secret_data)


def write_output(content: str):
    """Write rendered content to the output file with restricted permissions."""
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(OUTPUT_PATH), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    os.write(fd, content.encode())
    os.close(fd)


def log(msg: str):
    """Log a broker lifecycle event."""
    print(f"[broker] {msg}", flush=True)


def fetch_and_render() -> int:
    """Fetch the secret, render, write. Returns the version number."""
    data, version = fetch_secret()
    content = render_template(data)
    write_output(content)
    return version


def run_once():
    """Single-shot mode: fetch, render, write, exit."""
    version = fetch_and_render()
    log(f"fetched secret v{version}, rendered {TEMPLATE_PATH.name} -> {OUTPUT_PATH}")


def run_sidecar():
    """Sidecar mode: poll for changes and re-render on rotation."""
    log(f"starting — watching {KV_MOUNT}/{KV_PATH} (poll every {POLL_INTERVAL}s)")
    version = fetch_and_render()
    log(f"initial fetch: secret v{version}, rendered -> {OUTPUT_PATH}")

    while _running:
        time.sleep(POLL_INTERVAL)
        if not _running:
            break
        try:
            data, new_version = fetch_secret()
            if new_version != version:
                content = render_template(data)
                write_output(content)
                log(f"rotation detected: v{version} -> v{new_version}, re-rendered {OUTPUT_PATH}")
                version = new_version
        except Exception as e:
            log(f"poll error (will retry): {e}")

    log("shutting down (signal received)")


if __name__ == "__main__":
    if "--sidecar" in sys.argv:
        run_sidecar()
    else:
        run_once()
