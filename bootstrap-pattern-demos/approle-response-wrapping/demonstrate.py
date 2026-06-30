#!/usr/bin/env python3
"""demonstrate.py — an INTERACTIVE experience of AppRole Response-Wrapping.

YOU drive it against a REAL OpenBao (Docker): set up AppRole, run the Ansible playbook to
wrap+deliver a SecretID, watch the materializer unwrap and authenticate, then see replay
and expiry protection in action.

    ./demonstrate.py     # needs Docker + Ansible; brings the stack up/down for you

The root token is an obvious dev value — it IS the bootstrap secret this pattern replaces
in production (see README "Delivery pattern — out of scope").
"""
import getpass
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

HERE = Path(__file__).resolve().parent
RUN_DIR = HERE / "run"
BAO_ADDR = "http://127.0.0.1:58201"
BAO_TOKEN = "dev-only-root-token"  # BOOTSTRAP SECRET (obvious dev value)
APPROLE_NAME = "demo-app"
WRAP_TTL = "30s"
WRITEUP = HERE / "enlighten.html"

os.environ["BAO_ADDR"] = BAO_ADDR
os.environ["BAO_TOKEN"] = BAO_TOKEN

# --- pretty (same visual grammar as the other demos) ---------------------------
TTY = sys.stdout.isatty()
def _c(code, s): return f"\033[{code}m{s}\033[0m" if TTY else s
def GREEN(s): return _c("1;32", s)
def RED(s):   return _c("1;31", s)
def DIM(s):   return _c("2", s)
def BOLD(s):  return _c("1", s)
def CYAN(s):  return _c("36", s)
CURSOR = "\033[7m \033[0m" if TTY else ""

def clear_screen():
    if TTY:
        print("\033[H\033[2J\033[3J", end="", flush=True)

_PROMPT = None
def prompt_string() -> str:
    global _PROMPT
    if _PROMPT is not None:
        return _PROMPT
    sentinel = "@@PS1@@"
    try:
        r = subprocess.run(["bash", "-ic", f'printf "%s" "{sentinel}${{PS1@P}}"'],
                           capture_output=True, text=True, timeout=5)
        out = r.stdout
        if sentinel in out:
            out = out.split(sentinel, 1)[1]
        out = out.replace("\x01", "").replace("\x02", "").rstrip("\n")
        if out.strip():
            _PROMPT = out if out.endswith(" ") else out + " "
            return _PROMPT
    except Exception:
        pass
    user = getpass.getuser()
    host = socket.gethostname().split(".")[0]
    where = "~" if Path.cwd() == Path.home() else Path.cwd().name
    sigil = "#" if getattr(os, "geteuid", lambda: 1)() == 0 else "$"
    _PROMPT = f"[{user}@{host} {where}]{sigil} "
    return _PROMPT

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

def shell(cmd):
    print()
    print(prompt_string() + cmd + CURSOR, end="", flush=True)
    _enter()
    if not TTY:
        print()
    subprocess.run(cmd, shell=True, cwd=HERE)

def _have(tool): return shutil.which(tool) is not None


def bao_request(path, method="GET", data=None, token=None, wrap_ttl=None):
    """Make an HTTP request to the OpenBao API."""
    url = f"{BAO_ADDR}/v1/{path}"
    headers = {"Content-Type": "application/json"}
    if token:
        headers["X-Vault-Token"] = token
    if wrap_ttl:
        headers["X-Vault-Wrap-TTL"] = wrap_ttl
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        if e.code == 204:
            return {}
        error_body = e.read().decode() if e.fp else ""
        raise RuntimeError(f"HTTP {e.code}: {error_body}") from e


# --- state ------------------------------------------------------------------
done = {"up": False, "wrap": False, "replay": False}
last_token = None

def _stack_up() -> bool:
    r = subprocess.run(["docker", "compose", "ps", "--status=running", "-q"],
                       cwd=HERE, capture_output=True, text=True)
    return bool(r.stdout.strip())

def _all_done() -> bool:
    return done["wrap"] and done["replay"]

# --- menu actions -----------------------------------------------------------
def bring_up():
    coach("[deployer] Bring up REAL OpenBao (dev mode), configure AppRole auth,\n"
          "create a demo policy + secret, and fetch the RoleID.")
    subprocess.run(["docker", "compose", "down", "-v"], cwd=HERE, capture_output=True)
    coach("First, let's see what we're about to run:")
    shell("cat docker-compose.yml")
    shell("docker compose up -d")
    # Wait for OpenBao
    print(DIM("    waiting for OpenBao ..."), end="", flush=True)
    for _ in range(30):
        try:
            req = urllib.request.Request(f"{BAO_ADDR}/v1/sys/health")
            with urllib.request.urlopen(req):
                break
        except (urllib.error.URLError, ConnectionError):
            time.sleep(0.5)
    print(GREEN(" ready"))

    # Setup
    coach("[deployer] Configuring AppRole + policy + demo secret ...")
    try:
        bao_request("sys/auth/approle", method="POST",
                    data={"type": "approle"}, token=BAO_TOKEN)
    except RuntimeError:
        pass

    bao_request(f"auth/approle/role/{APPROLE_NAME}", method="POST", data={
        "token_policies": ["demo-app-policy"],
        "secret_id_ttl": "60s",
        "token_ttl": "300s",
    }, token=BAO_TOKEN)
    bao_request("sys/policies/acl/demo-app-policy", method="PUT", data={
        "policy": 'path "secret/data/demo-app/*" { capabilities = ["read"] }'
    }, token=BAO_TOKEN)
    bao_request("secret/data/demo-app/config", method="POST", data={
        "data": {"password": "S3cr3t-Pg-Pass", "host": "db.example.com"}
    }, token=BAO_TOKEN)
    result = bao_request(f"auth/approle/role/{APPROLE_NAME}/role-id", token=BAO_TOKEN)
    RUN_DIR.mkdir(parents=True, exist_ok=True)
    (RUN_DIR / "role-id").write_text(result["data"]["role_id"])
    verdict("AppRole configured. RoleID saved to run/role-id.", ok=True)
    done["up"] = True


def wrap_and_deliver():
    global last_token
    if not _stack_up():
        print(RED("    Stack isn't up yet — choose 1 first.")); return
    if not _have("ansible-playbook"):
        print(RED("    ansible-playbook not found — install it: pip install ansible-core")); return

    coach("[deployer] Running the Ansible playbook to wrap a SecretID and deliver it\n"
          "to run/wrapped-token. The wrapping token is single-use, TTL=30s:")
    shell("ansible-playbook -i inventory.yml playbook.yml")

    token_file = RUN_DIR / "wrapped-token"
    if token_file.exists():
        last_token = token_file.read_text().strip()
        coach(f"[deployer] Wrapping token delivered: {last_token[:8]}...{last_token[-4:]}")
    else:
        print(RED("    wrapped-token file not found")); return

    coach("[target] Now the materializer unwraps → authenticates → fetches the secret:")
    shell(f"{sys.executable} materializer.py")
    verdict("Materializer authenticated via single-use wrapped token.", ok=True)
    done["wrap"] = True


def replay_and_expire():
    global last_token
    if not _stack_up():
        print(RED("    Stack isn't up yet — choose 1 first.")); return
    if not last_token:
        print(RED("    No wrapping token to replay — choose 2 first.")); return

    coach("[attacker] Attempting to REPLAY the already-consumed wrapping token ...")
    print(DIM(f"    token: {last_token[:8]}...{last_token[-4:]}"))
    try:
        bao_request("sys/wrapping/unwrap", method="POST", data={}, token=last_token)
        verdict("ERROR: replay succeeded (this should not happen)", ok=False)
    except RuntimeError as e:
        verdict(f"Replay REJECTED: {e}", ok=True)

    coach("[attacker] Now testing TTL expiry — generating a token with TTL=2s, waiting 3s ...")
    result = bao_request(f"auth/approle/role/{APPROLE_NAME}/secret-id", method="POST",
                         data={}, token=BAO_TOKEN, wrap_ttl="2s")
    short_token = result["wrap_info"]["token"]
    print(DIM(f"    short-lived token: {short_token[:8]}... (TTL=2s)"))
    print(DIM("    waiting 3s ..."), end="", flush=True)
    time.sleep(3)
    print(GREEN(" expired"))
    try:
        bao_request("sys/wrapping/unwrap", method="POST", data={}, token=short_token)
        verdict("ERROR: expired unwrap succeeded (this should not happen)", ok=False)
    except RuntimeError as e:
        verdict(f"Expired token REJECTED: {e}", ok=True)

    verdict("Single-use + TTL: both kill replay.", ok=True)
    done["replay"] = True


def explore():
    sh = os.environ.get("SHELL", "/bin/bash")
    coach(BOLD("Explorer — forking a shell. Try ") + CYAN("bao read auth/approle/role/demo-app/role-id")
          + BOLD(" or ") + CYAN("docker compose ps") + BOLD("; type ") + CYAN("exit") + BOLD(" to return."))
    if not sys.stdin.isatty():
        print(DIM("    (no interactive terminal — skipping)")); return
    subprocess.run([sh], cwd=HERE)
    print(DIM("    ...back from the explorer."))


def tear_down():
    coach("Tear the stack down (the container is disposable — nothing real here).")
    shell("docker compose down -v")
    done["up"] = False


def enlighten():
    if not WRITEUP.exists():
        print(DIM(f"    deck not found — build it: python3 ../../tools/build_deck.py {HERE.name}")); return
    for opener in ("xdg-open", "sensible-browser", "open"):
        if _have(opener):
            subprocess.run([opener, str(WRITEUP)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(DIM(f"    opened {WRITEUP.name} in your browser")); return
    print(DIM(f"    no GUI opener found — open this yourself: file://{WRITEUP}"))


# --- menu -------------------------------------------------------------------
def menu():
    up = GREEN("UP") if _stack_up() else RED("down")
    w = "+" if done["wrap"] else " "
    r = "+" if done["replay"] else " "
    print("\n" + BOLD("==== AppRole Response-Wrapping — an experience ===="))
    print(f"     Stack: {up}     Experienced:  [{w}] wrap+auth   [{r}] replay-fail")
    print()
    print("  0) Enlighten me                   " + DIM("(open the concept page)"))
    print("  1) Bring up OpenBao + AppRole     " + DIM("(docker compose up + configure)"))
    print("  2) Wrap & deliver (Ansible)       " + DIM("(playbook wraps SecretID → materializer authenticates)"))
    print("  3) Replay & expiry test           " + DIM("(consumed token rejected + expired token rejected)"))
    print("  4) Explore                        " + DIM("(fork a shell; type 'exit' to return)"))
    print("  5) Tear down                      " + DIM("(docker compose down -v)"))
    print("  " + (GREEN("6) Finish") if _all_done() else "6) Abort"))


def main():
    os.chdir(HERE)
    shutil.rmtree(HERE / "__pycache__", ignore_errors=True)
    actions = {"0": enlighten, "1": bring_up, "2": wrap_and_deliver,
               "3": replay_and_expire, "4": explore, "5": tear_down}
    while True:
        clear_screen()
        menu()
        print("\n  Please select: ", end="", flush=True)
        try:
            choice = input().strip()
        except EOFError:
            break
        if choice == "6":
            print(GREEN("\n  Finished — a single-use wrapped token kills replay. \U0001f44b")
                  if _all_done() else DIM("\n  Aborted."))
            break
        action = actions.get(choice)
        if not action:
            continue
        action()
        pause()

    if done.get("up"):
        tear_down()


if __name__ == "__main__":
    main()
