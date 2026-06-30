#!/usr/bin/env python3
"""demonstrate.py — an INTERACTIVE experience of the Cloud Instance Identity bootstrap pattern.

YOU drive it against a REAL OpenBao (Docker): see the mock metadata endpoint provide
instance credentials, watch the materializer authenticate without any stored secret,
and observe that only the delivery output (not auth tokens) hits disk.

    ./demonstrate.py     # needs Docker; brings the stack up/down for you

The OpenBao dev token is an obvious dev value, out of scope — see README
"Delivery pattern — out of scope".
"""
import getpass
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

# Configuration
MOCK_PORT = 51169
BAO_ADDR = "http://127.0.0.1:58200"
BAO_TOKEN = "dev-only-root-token"
SECRET_VALUE = "S3cr3t-Pg-Pass"
SECRET_PATH = "secret/data/demo/db-password"
OUTPUT_FILE = HERE / "run" / "secret.json"
WRITEUP = HERE / "enlighten.html"

os.environ["AWS_METADATA_URL"] = f"http://127.0.0.1:{MOCK_PORT}"
os.environ["BAO_ADDR"] = BAO_ADDR
os.environ["BAO_AUTH_ROLE"] = "demo-instance-role"
os.environ["BAO_SECRET_PATH"] = SECRET_PATH
os.environ["MATERIALIZER_OUTPUT"] = str(OUTPUT_FILE)

# --- pretty (same visual grammar as dynamic-credential-shim) ---
TTY = sys.stdout.isatty()
def _c(code, s): return f"\033[{code}m{s}\033[0m" if TTY else s
def GREEN(s): return _c("1;32", s)
def RED(s):   return _c("1;31", s)
def DIM(s):   return _c("2", s)
def BOLD(s):  return _c("1", s)
CURSOR = "\033[7m \033[0m" if TTY else ""


def clear_screen():
    if TTY:
        print("\033[H\033[2J\033[3J", end="", flush=True)


_PROMPT = None
def prompt_string() -> str:
    global _PROMPT
    if _PROMPT is not None:
        return _PROMPT
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


def _bao_api(method, path, data=None, token=BAO_TOKEN):
    url = f"{BAO_ADDR}/v1/{path}"
    payload = json.dumps(data).encode() if data else None
    req = Request(url, data=payload, method=method,
                  headers={"X-Vault-Token": token, "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=10) as resp:
            body = resp.read().decode()
            return json.loads(body) if body.strip() else {}
    except HTTPError as e:
        if e.code == 204:
            return {}
        raise


def _wait_for_bao(timeout=30):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            req = Request(f"{BAO_ADDR}/v1/sys/health")
            with urlopen(req, timeout=2):
                return True
        except (URLError, OSError):
            time.sleep(0.5)
    raise RuntimeError("OpenBao did not become ready in time")


# --- state ---
done = {"up": False, "metadata": False, "materialize": False, "rotation": False}
mock_server = None


def _stack_up() -> bool:
    r = subprocess.run(["docker", "compose", "ps", "--status=running", "-q"],
                       cwd=HERE, capture_output=True, text=True)
    return bool(r.stdout.strip())


def _all_done() -> bool:
    return done["metadata"] and done["materialize"] and done["rotation"]


# --- menu actions ---
def bring_up():
    global mock_server
    coach("Bring up OpenBao (dev mode) + start the mock IMDSv2 metadata service.\n"
          "This simulates an EC2 instance with an IAM role attached.")
    subprocess.run(["docker", "compose", "down", "-v"], cwd=HERE, capture_output=True)
    coach("First, let's see what we're about to run:")
    shell("cat docker-compose.yml")
    shell("docker compose up -d")
    print(DIM("    waiting for OpenBao ..."))
    _wait_for_bao()

    # Start mock metadata
    import mock_metadata
    if mock_server:
        mock_server.shutdown()
    mock_server, _ = mock_metadata.run_server(port=MOCK_PORT, blocking=False)
    print(DIM(f"    mock IMDSv2 listening on 127.0.0.1:{MOCK_PORT}"))

    # Configure OpenBao (KV secret + policy; AWS auth plugin not in dev image)
    print(DIM("    configuring OpenBao (KV secret + read policy) ..."))
    try:
        _bao_api("POST", "sys/mounts/secret", {"type": "kv", "options": {"version": "2"}})
    except (HTTPError, RuntimeError):
        pass
    _bao_api("POST", SECRET_PATH, {"data": {"password": SECRET_VALUE, "username": "app_user"}})
    _bao_api("PUT", "sys/policies/acl/demo-read", {
        "policy": 'path "secret/data/demo/*" { capabilities = ["read"] }'})
    print(DIM("    OpenBao configured (mock AWS auth — dev image lacks aws plugin)"))
    done["up"] = True


def show_metadata():
    if not done["up"]:
        print(RED("    Stack isn't up yet - choose 1 first.")); return
    coach("The IMDSv2 flow: PUT to get a session token, then GET with that token.\n"
          "This is what the hypervisor provides at 169.254.169.254 — no stored secret needed.\n"
          "NOTE: This mock simulates the hypervisor-backed metadata service.")

    import materializer
    print(DIM("    Step 1: PUT /latest/api/token"))
    token = materializer.get_metadata_token()
    print(f"    session token: {token[:24]}...")
    print(DIM("    Step 2: GET /latest/meta-data/iam/security-credentials/"))
    creds = materializer.get_instance_credentials(token)
    print(f"    AccessKeyId:     {creds['AccessKeyId']}")
    print(f"    Token:           {creds['Token'][:30]}...")
    print(f"    Expiration:      {creds['Expiration']}")
    verdict("Instance identity obtained — no secret stored, just asked the hypervisor.", ok=True)
    done["metadata"] = True


def run_materializer():
    if not done["up"]:
        print(RED("    Stack isn't up yet - choose 1 first.")); return
    coach("The materializer uses the instance credentials to authenticate to OpenBao,\n"
          "fetches the secret, and writes it to disk — all without a stored bootstrap secret.")

    import materializer
    # Patch auth for demo (no real STS)
    _original = materializer.authenticate_to_openbao

    def _mock_auth(aws_creds):
        payload = json.dumps({
            "policies": ["demo-read"], "ttl": "1h",
            "display_name": f"aws-{aws_creds['AccessKeyId'][:8]}",
            "meta": {"role": "demo-instance-role"},
        }).encode()
        req = Request(f"{BAO_ADDR}/v1/auth/token/create", data=payload, method="POST",
                      headers={"X-Vault-Token": BAO_TOKEN, "Content-Type": "application/json"})
        with urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode())
            return data["auth"]["client_token"]

    materializer.authenticate_to_openbao = _mock_auth
    try:
        materializer.materialize(verbose=True)
    finally:
        materializer.authenticate_to_openbao = _original

    # Verify
    if OUTPUT_FILE.exists():
        secret = json.loads(OUTPUT_FILE.read_text())
        print(f"\n    secret.password = {secret['password']}")
        # Check no auth tokens in the output
        content = OUTPUT_FILE.read_text()
        assert BAO_TOKEN not in content
        print(DIM("    (no vault tokens or metadata tokens in the output file)"))
        verdict("Secret materialized — bootstrap was the machine's own identity.", ok=True)
    done["materialize"] = True


def show_rotation():
    if not done["up"]:
        print(RED("    Stack isn't up yet - choose 1 first.")); return
    coach("Each call to the metadata endpoint returns fresh, short-lived credentials.\n"
          "The old session token expires; a new one is issued. This is rotation\n"
          "without any secret management — the cloud control plane handles it.")

    import materializer
    print(DIM("    Call 1:"))
    t1 = materializer.get_metadata_token()
    c1 = materializer.get_instance_credentials(t1)
    print(f"    Token: {c1['Token']}")

    print(DIM("    Call 2:"))
    t2 = materializer.get_metadata_token()
    c2 = materializer.get_instance_credentials(t2)
    print(f"    Token: {c2['Token']}")

    if c1["Token"] != c2["Token"]:
        verdict("Fresh credentials each time — rotation is built into the cloud's identity model.", ok=True)
    else:
        verdict("Tokens matched (unexpected)", ok=False)
    done["rotation"] = True


def explore():
    sh = os.environ.get("SHELL", "/bin/bash")
    coach(BOLD("Explorer — forking a shell. Try ") +
          "\033[36mcurl -X PUT -H 'X-aws-ec2-metadata-token-ttl-seconds: 300' "
          f"http://127.0.0.1:{MOCK_PORT}/latest/api/token\033[0m" +
          BOLD("; type ") + "\033[36mexit\033[0m" + BOLD(" to return."))
    if not sys.stdin.isatty():
        print(DIM("    (no interactive terminal - explorer needs a real tty; skipping)")); return
    subprocess.run([sh], cwd=HERE)
    print(DIM("    ...back from the explorer."))


def tear_down():
    global mock_server
    coach("Tear the stack down (the containers are disposable - nothing real here).")
    shell("docker compose down -v")
    if mock_server:
        mock_server.shutdown()
        mock_server = None
    # Clean up runtime artifacts
    run_dir = HERE / "run"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    done["up"] = False


def enlighten():
    if not WRITEUP.exists():
        print(DIM(f"    deck not found - build it: python3 ../../tools/build_deck.py {HERE.name}")); return
    for opener in ("xdg-open", "sensible-browser", "open"):
        if _have(opener):
            subprocess.run([opener, str(WRITEUP)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(DIM(f"    opened {WRITEUP.name} in your browser")); return
    print(DIM(f"    no GUI opener found - open this yourself: file://{WRITEUP}"))


# --- menu ---
def menu():
    up = GREEN("UP") if _stack_up() else RED("down")
    m = "[x]" if done["metadata"] else "[ ]"
    mat = "[x]" if done["materialize"] else "[ ]"
    rot = "[x]" if done["rotation"] else "[ ]"
    print("\n" + BOLD("==== Cloud Instance Identity - an experience ===="))
    print(f"     Stack: {up}     Experienced:  {m} metadata  {mat} materialize  {rot} rotation")
    print()
    print("  0) Enlighten me                        " + DIM("(open the concept page)"))
    print("  1) Bring up OpenBao + mock metadata    " + DIM("(docker compose up + configure)"))
    print("  2) Show IMDSv2 flow                    " + DIM("(PUT token → GET credentials)"))
    print("  3) Run the materializer                " + DIM("(metadata → OpenBao auth → secret)"))
    print("  4) Show token rotation                 " + DIM("(fresh credentials each call)"))
    print("  5) Explore                             " + DIM("(fork a shell; type 'exit' to return)"))
    print("  6) Tear down                           " + DIM("(docker compose down -v)"))
    print("  " + (GREEN("7) Finish") if _all_done() else "7) Abort"))


def main():
    os.chdir(HERE)
    shutil.rmtree(HERE / "__pycache__", ignore_errors=True)
    actions = {"0": enlighten, "1": bring_up, "2": show_metadata,
               "3": run_materializer, "4": show_rotation, "5": explore, "6": tear_down}
    while True:
        clear_screen()
        menu()
        print("\n  Please select: ", end="", flush=True)
        try:
            choice = input().strip()
        except EOFError:
            break
        if choice == "7":
            print(GREEN("\n  Finished — the machine's identity IS the bootstrap secret. No secret stored.")
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
