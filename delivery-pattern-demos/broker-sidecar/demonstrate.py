#!/usr/bin/env python3
"""demonstrate.py — an INTERACTIVE experience of the Broker Sidecar pattern.

YOU drive it against a REAL OpenBao (Docker): bring up the stack, watch the broker fetch a
secret, render it through a template, then rotate and watch the broker detect and re-render —
while the legacy reader keeps getting the right credential without any code change.

    ./demonstrate.py     # needs Docker; brings the stack up/down for you

Bootstrap secrets (the OpenBao dev token) are obvious dev values, out of scope — see README
"Bootstrap secret — out of scope".
"""
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent

BAO_ADDR = "http://127.0.0.1:58201"
BAO_TOKEN = "dev-only-root-token"  # BOOTSTRAP SECRET (obvious dev value)
KV_MOUNT = "secret"
KV_PATH = "apps/legacy-db"
OUTPUT = HERE / "run" / "db.conf"

INITIAL_SECRET = {
    "host": "127.0.0.1",
    "port": "5432",
    "dbname": "appdb",
    "username": "app_pg_user",
    "password": "S3cr3t-Pg-Pass",
}

ROTATED_SECRET = {
    "host": "127.0.0.1",
    "port": "5432",
    "dbname": "appdb",
    "username": "app_pg_user",
    "password": "R0tated-Pg-Pass-v2",
}

# --- pretty (same visual grammar as sibling demos) ----------------------------
TTY = sys.stdout.isatty()
def _c(code, s): return f"\033[{code}m{s}\033[0m" if TTY else s
def GREEN(s): return _c("1;32", s)
def RED(s):   return _c("1;31", s)
def DIM(s):   return _c("2", s)
def BOLD(s):  return _c("1", s)

def clear_screen():
    if TTY:
        print("\033[H\033[2J\033[3J", end="", flush=True)

def _enter():
    try:
        input()
    except EOFError:
        raise SystemExit(0)

def pause(prompt="Press [enter] to return to the menu ..."):
    print("\n    " + DIM(prompt), end="", flush=True)
    _enter()

def coach(text):
    print("\n    " + DIM(text.replace("\n", "\n    ")))

def verdict(text, ok=True):
    print("\n    " + (GREEN if ok else RED)(text))


def bao_request(method: str, path: str, data: dict = None) -> dict:
    """Make an HTTP request to the OpenBao API."""
    url = f"{BAO_ADDR}/v1/{path}"
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, method=method,
                                headers={"X-Vault-Token": BAO_TOKEN,
                                         "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        body_text = e.read().decode() if e.fp else ""
        raise RuntimeError(f"OpenBao API error {e.code}: {body_text}") from e


def wait_for_openbao(timeout=30):
    """Wait for OpenBao to become ready."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            url = f"{BAO_ADDR}/v1/sys/health"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=2):
                return True
        except Exception:
            time.sleep(1)
    return False


def run_broker():
    """Run the broker in one-shot mode."""
    env = {**os.environ,
           "BROKER_BAO_ADDR": BAO_ADDR,
           "BROKER_BAO_TOKEN": BAO_TOKEN,
           "BROKER_KV_MOUNT": KV_MOUNT,
           "BROKER_KV_PATH": KV_PATH}
    r = subprocess.run([sys.executable, str(HERE / "broker.py")],
                       env=env, capture_output=True, text=True)
    print(r.stdout, end="")
    if r.returncode != 0:
        print(RED(f"    broker error: {r.stderr}"))
    return r.returncode == 0


def run_reader():
    """Run the legacy reader."""
    r = subprocess.run([sys.executable, str(HERE / "legacy_reader.py")],
                       capture_output=True, text=True)
    print(r.stdout, end="")
    if r.returncode != 0:
        print(RED(f"    reader error: {r.stderr}"))
    return r.returncode == 0


# --- state ------------------------------------------------------------------
done = {"up": False, "seeded": False, "rendered": False, "rotated": False}

def _stack_up() -> bool:
    r = subprocess.run(["docker", "compose", "ps", "--status=running", "-q"],
                       cwd=HERE, capture_output=True, text=True)
    return bool(r.stdout.strip())

def _all_done() -> bool:
    return done["rendered"] and done["rotated"]

# --- menu actions -----------------------------------------------------------
def bring_up():
    coach("Bring up OpenBao (dev mode) and seed the initial secret into KV v2.\n"
          "The broker will later fetch from this path and render it through a template.")
    subprocess.run(["docker", "compose", "down", "-v"], cwd=HERE, capture_output=True)
    subprocess.run(["docker", "compose", "up", "-d"], cwd=HERE)
    print()
    coach("Waiting for OpenBao to be ready ...")
    if not wait_for_openbao():
        print(RED("    OpenBao did not become ready in time."))
        return
    print(DIM("    OpenBao ready"))
    coach("Seeding the initial secret (password: S3cr3t-Pg-Pass) ...")
    bao_request("POST", f"{KV_MOUNT}/data/{KV_PATH}", {"data": INITIAL_SECRET})
    print(DIM("    secret written to secret/apps/legacy-db"))
    done["up"] = True
    done["seeded"] = True

def fetch_and_render():
    if not _stack_up():
        print(RED("    Stack isn't up yet — choose 1 first.")); return
    coach("The broker fetches the secret from OpenBao KV v2, renders it through the\n"
          "Jinja2 template (templates/db.conf.j2), and writes the result to run/db.conf:")
    if run_broker():
        verdict("Broker rendered the secret into the app's config file.", ok=True)
        done["rendered"] = True
    coach("The legacy reader opens the rendered config — no idea it came from a broker:")
    run_reader()

def rotate_and_rerender():
    if not _stack_up():
        print(RED("    Stack isn't up yet — choose 1 first.")); return
    coach("Simulate rotation: write a new version of the secret to KV v2.")
    bao_request("POST", f"{KV_MOUNT}/data/{KV_PATH}", {"data": ROTATED_SECRET})
    print(DIM("    new secret version written (password: R0tated-Pg-Pass-v2)"))
    coach("The broker fetches again — detects the new version — re-renders:")
    if run_broker():
        verdict("Rotation detected; broker re-rendered with the new credential.", ok=True)
        done["rotated"] = True
    coach("The legacy reader sees the new value — untouched code, new secret:")
    run_reader()

def tear_down():
    coach("Tear the stack down (the container is disposable).")
    subprocess.run(["docker", "compose", "down", "-v"], cwd=HERE)
    done["up"] = False

def enlighten():
    deck = HERE / "deck.html"
    if not deck.exists():
        print(DIM(f"    deck not found — build it: python3 ../../tools/build_deck.py {HERE.name}")); return
    for opener in ("xdg-open", "sensible-browser", "open"):
        if shutil.which(opener):
            subprocess.run([opener, str(deck)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(DIM(f"    opened {deck.name} in your browser")); return
    print(DIM(f"    no GUI opener found — open this yourself: file://{deck}"))

# --- menu -------------------------------------------------------------------
def menu():
    up = GREEN("UP") if _stack_up() else RED("down")
    r = GREEN("done") if done["rendered"] else DIM("pending")
    rot = GREEN("done") if done["rotated"] else DIM("pending")
    print("\n" + BOLD("==== The Broker Sidecar — an experience ===="))
    print(f"     Stack: {up}     Rendered: {r}     Rotated: {rot}")
    print()
    print("  0) Enlighten me                  " + DIM("(open the slide deck)"))
    print("  1) Bring up OpenBao + seed       " + DIM("(docker compose up + write KV secret)"))
    print("  2) Fetch, render, read           " + DIM("(broker fetches + templates -> reader reads)"))
    print("  3) Rotate & re-render            " + DIM("(write new KV version -> broker detects -> re-renders)"))
    print("  4) Tear down                     " + DIM("(docker compose down -v)"))
    print("  " + (GREEN("5) Finish") if _all_done() else "5) Abort"))

def main():
    os.chdir(HERE)
    shutil.rmtree(HERE / "__pycache__", ignore_errors=True)
    actions = {"0": enlighten, "1": bring_up, "2": fetch_and_render,
               "3": rotate_and_rerender, "4": tear_down}
    while True:
        clear_screen()
        menu()
        print("\n  Please select: ", end="", flush=True)
        try:
            choice = input().strip()
        except EOFError:
            break
        if choice == "5":
            print(GREEN("\n  Finished — secrets delivered through a sidecar broker.")
                  if _all_done() else DIM("\n  Aborted."))
            break
        action = actions.get(choice)
        if not action:
            continue
        action()
        pause()

if __name__ == "__main__":
    main()
