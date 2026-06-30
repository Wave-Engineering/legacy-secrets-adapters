#!/usr/bin/env python3
"""demonstrate.py — an INTERACTIVE experience of the Dynamic Credential Shim.

YOU drive it against a REAL OpenBao + Postgres (Docker): bring up the stack, watch the
unchanged legacy reader connect with an OpenBao-managed credential, then rotate the static
role and watch a leaked copy of the old password self-expire — while the app keeps working.

    ./demonstrate.py     # needs Docker; brings the stack up/down for you

Bootstrap secrets (the OpenBao dev token, the PG superuser password) are obvious dev values,
out of scope — see README "Bootstrap secret — out of scope".
"""
import getpass
import json
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Hard safety pin: this demo NEVER inherits an ambient BAO_ADDR/BAO_TOKEN (which could point at a
# real server). Every child bao/psql call sees only the local container.
os.environ["BAO_ADDR"] = "http://127.0.0.1:58200"
os.environ["BAO_TOKEN"] = "dev-only-root-token"   # BOOTSTRAP SECRET (obvious dev value)

ROLE = "app-static"
WRITEUP = HERE / "enlighten.html"
RUN_CFG = HERE / "run" / "secrets.json"

# --- pretty (same visual grammar as cone-of-silence) ------------------------
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

# --- state ------------------------------------------------------------------
done = {"up": False, "read": False, "rotate": False}

def _stack_up() -> bool:
    r = subprocess.run(["docker", "compose", "ps", "--status=running", "-q"],
                       cwd=HERE, capture_output=True, text=True)
    return bool(r.stdout.strip())

def _all_done() -> bool:
    return done["read"] and done["rotate"]

# --- menu actions -----------------------------------------------------------
def bring_up():
    coach("Bring up REAL OpenBao (dev mode) + Postgres, then configure the database secrets\n"
          "engine and a STATIC role — OpenBao now owns and rotates app_pg_user's password.")
    subprocess.run(["docker", "compose", "down", "-v"], cwd=HERE,
                   capture_output=True)  # fresh stack each time (setup's rotate-root isn't idempotent)
    shell("docker compose up -d")
    shell("./setup.sh")
    done["up"] = True

def read_secret():
    if not _stack_up():
        print(RED("    Stack isn't up yet — choose 1 first.")); return
    coach("The shim fetches the OpenBao-managed credential and writes the reader's file.\n"
          "The unchanged legacy reader then connects — unaware the password is managed:")
    shell("./shim.py")
    shell("./legacy_reader.py")
    verdict("Connected with a credential no human chose and no human stored.", ok=True)
    done["read"] = True

def rotate_and_leak():
    if not _stack_up():
        print(RED("    Stack isn't up yet — choose 1 first.")); return
    coach("Suppose an attacker exfiltrates a copy of the current password ...")
    cur = subprocess.run(["bao", "read", "-format=json", f"database/static-creds/{ROLE}"],
                         capture_output=True, text=True, cwd=HERE)
    pw = json.loads(cur.stdout)["data"]["password"] if cur.returncode == 0 else ""
    print(DIM(f"    captured: app_pg_user / {pw[:6]}…(redacted)"))
    coach("Now OpenBao rotates the static role (forced here; a schedule in production):")
    shell(f"bao write -f database/rotate-role/{ROLE}")
    coach("The exfiltrated copy no longer authenticates — the leak self-expired:")
    # Show the command with the password MASKED; run it with the real (now-stale) password.
    masked = ("psql 'postgresql://app_pg_user:<exfiltrated>@127.0.0.1:55432/appdb"
              "?sslmode=disable&gssencmode=disable' -tAc 'select 1'")
    print()
    print(prompt_string() + masked + CURSOR, end="", flush=True)
    _enter()
    if not TTY:
        print()
    real_dsn = f"postgresql://app_pg_user:{pw}@127.0.0.1:55432/appdb?sslmode=disable&gssencmode=disable"
    subprocess.run(["psql", real_dsn, "-tAc", "select 1"], cwd=HERE)
    verdict("A stolen credential is dead within one rotation window.", ok=True)
    coach("And the shim re-materializes the new password; the reader (unchanged) reconnects:")
    shell("./shim.py")
    shell("./legacy_reader.py")
    done["rotate"] = True

def grep_disk():
    if not RUN_CFG.exists():
        print(DIM("    (no rendered file yet — choose 2 first)")); return
    coach("The shim wrote the credential to a regular file. Can we find it on disk?")
    print(DIM(f"    grep 'password' {RUN_CFG.relative_to(HERE)}"))
    content = RUN_CFG.read_text()
    for line in content.splitlines():
        if "password" in line.lower():
            print(RED(f"    {line.strip()}"))
        else:
            print(DIM(f"    {line.strip()}"))
    verdict(
        "The credential is plaintext on disk RIGHT NOW.\n"
        "    The shim's protection is temporal, not spatial: this password\n"
        "    will be dead after the next rotation window. A stolen copy\n"
        "    has a shelf life — but it IS readable until then.", ok=False)
    coach("Defence in Depth: couple with cone-of-silence (write to a tmpfs\n"
          "RAM path instead of a regular file) for temporal + spatial protection.\n"
          "Rotation kills leaked copies; the Cone ensures there's nothing to leak\n"
          "from disk in the first place.")


def explore():
    sh = os.environ.get("SHELL", "/bin/bash")
    coach(BOLD("Explorer — forking a shell. Try ") + "\033[36mbao read database/static-creds/" + ROLE
          + "\033[0m" + BOLD(" or ") + "\033[36mdocker compose ps\033[0m" + BOLD("; type ")
          + "\033[36mexit\033[0m" + BOLD(" to return."))
    if not sys.stdin.isatty():
        print(DIM("    (no interactive terminal — explorer needs a real tty; skipping)")); return
    subprocess.run([sh], cwd=HERE)
    print(DIM("    ...back from the explorer."))

def tear_down():
    coach("Tear the stack down (the containers are disposable — nothing real here).")
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
    up = GREEN("UP ✓") if _stack_up() else RED("down")
    r = "✓" if done["read"] else " "
    rot = "✓" if done["rotate"] else " "
    print("\n" + BOLD("════ The Dynamic Credential Shim — an experience ════"))
    print(f"     Stack: {up}     Experienced:  [{r}] managed-read   [{rot}] rotation")
    print()
    print("  0) Enlighten me                  " + DIM("(open the concept page)"))
    print("  1) Bring up OpenBao + Postgres   " + DIM("(docker compose up + configure the static role)"))
    print("  2) Read the secret               " + DIM("(shim fetches → unchanged reader connects)"))
    print("  3) Rotate & watch the leak die   " + DIM("(exfiltrate → rotate → old credential fails)"))
    print("  4) Grep the disk                 " + DIM("(find the secret on disk — the honest tradeoff)"))
    print("  5) Explore                       " + DIM("(fork a shell; type 'exit' to return)"))
    print("  6) Tear down                     " + DIM("(docker compose down -v)"))
    print("  " + (GREEN("7) Finish") if _all_done() else "7) Abort"))

def main():
    os.chdir(HERE)
    shutil.rmtree(HERE / "__pycache__", ignore_errors=True)
    actions = {"0": enlighten, "1": bring_up, "2": read_secret,
               "3": rotate_and_leak, "4": grep_disk, "5": explore, "6": tear_down}
    while True:
        clear_screen()
        menu()
        print("\n  Please select: ", end="", flush=True)
        try:
            choice = input().strip()
        except EOFError:
            break
        if choice == "7":
            print(GREEN("\n  Finished — a leaked credential now has a shelf life. \U0001f44b")
                  if _all_done() else DIM("\n  Aborted."))
            break
        action = actions.get(choice)
        if not action:
            continue
        action()
        pause()

    if _stack_up():
        tear_down()

if __name__ == "__main__":
    main()
