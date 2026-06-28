#!/usr/bin/env python3
"""demonstrate.py — an INTERACTIVE experience of the Cone of Silence: a low-effort,
RAM-only zone your secret never leaves.

YOU drive it: engage and disengage the Cone yourself, try to read the secret,
hunt the disk for cleartext, or fork a shell and explore — and FEEL the
difference between the two states.

    ./demonstrate.py

This is the control plane. The moving parts live in:
    cone.py            the Cone engine (encrypt at rest, decrypt into RAM)
    legacy_reader.py   the app we cannot change (reads a file, uses the secret)
"""
import getpass
import os
import shutil
import socket
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ — keeps the demo dir clean AND un-greppable

import cone  # the engine: ENC_FILE, KEY_FILE, SECRET, CONE, NEEDLE, init/materialize/wipe

HERE       = Path(__file__).resolve().parent
READER     = "./legacy_reader.py"                  # run relative once we chdir(HERE)
HARDCODED  = HERE / "legacy-etc" / "secrets.json"  # an app's baked-in path (we can't change it)
WRITEUP    = HERE / "enlighten.html"
CONE_VIDEO = "https://youtu.be/trNgQoJ5f_I"

# --- pretty -----------------------------------------------------------------
# Visual grammar: narration is DIM and INDENTED ("us" coaching); the terminal
# block — prompt + command output — is flush-left and in default color ("the
# machine"). The two never look alike.
TTY = sys.stdout.isatty()
def _c(code, s): return f"\033[{code}m{s}\033[0m" if TTY else s
def GREEN(s): return _c("1;32", s)
def RED(s):   return _c("1;31", s)
def DIM(s):   return _c("2", s)
def BOLD(s):  return _c("1", s)

CURSOR = "\033[7m \033[0m" if TTY else ""   # a reverse-video block — the "cursor at the end"

def clear_screen():
    # cls/clear for an uncluttered menu — only on a real terminal (no escapes into a pipe)
    if TTY:
        print("\033[H\033[2J\033[3J", end="", flush=True)

_PROMPT = None
def prompt_string() -> str:
    """Show commands at the USER'S OWN shell prompt. bash's ${PS1@P} expands the
    prompt escapes (\\u \\h \\w, colors) to the literal string the shell would draw."""
    global _PROMPT
    if _PROMPT is not None:
        return _PROMPT
    sentinel = "@@PS1@@"
    try:
        r = subprocess.run(["bash", "-ic", f'printf "%s" "{sentinel}${{PS1@P}}"'],
                           capture_output=True, text=True, timeout=5)
        out = r.stdout
        if sentinel in out:                      # drop any .bashrc stdout noise before our marker
            out = out.split(sentinel, 1)[1]
        out = out.replace("\x01", "").replace("\x02", "").rstrip("\n")  # strip readline markers
        if out.strip():
            _PROMPT = out if out.endswith(" ") else out + " "
            return _PROMPT
    except Exception:
        pass
    user = getpass.getuser()                     # fallback: synthesize a typical prompt
    host = socket.gethostname().split(".")[0]
    cwd = Path.cwd()
    where = "~" if cwd == Path.home() else cwd.name
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
    # narration: dim + indented, set apart from the terminal block
    print("\n    " + DIM(text.replace("\n", "\n    ")))

def verdict(text, ok=True):
    # the punchy success/failure line that caps a walkthrough
    print("\n    " + (GREEN if ok else RED)(text))

def shell(cmd, run=None):
    """Type the command at the user's real prompt (flush-left), leave a cursor, run it on Enter.
    A blank line above the prompt sets the block off; the blank below is supplied by the next
    narration/verdict/pause line. `run` lets us display a clean command but execute a
    color-enabled variant."""
    print()                                                       # blank line above
    print(prompt_string() + cmd + CURSOR, end="", flush=True)     # flush-left prompt
    _enter()
    if not TTY:
        print()                                                   # separate output from prompt in a pipe
    subprocess.run(run or cmd, shell=True)

# best-effort syntax coloring — no hard dependency
def _have(tool): return shutil.which(tool) is not None
def _ls(path="."):  return f"ls -la {path}".rstrip() + (" --color=always" if TTY else "")
def _grep_color(g): return g.replace("grep -rn ", "grep -rn --color=always ", 1) if TTY else g
def _cat(path):     return (f"bat -l json --style=plain --color=always {path}"
                            if TTY and _have("bat") else f"cat {path}")

# --- Cone state + progress --------------------------------------------------
# Per side, track which of {read, detect} the user has experienced:
#   [ ] untouched   ->   [~] in progress (visited, or one done)   ->   [✓] both done
progress = {"engaged": set(), "disengaged": set()}
visited  = {"engaged": False, "disengaged": False}

def engaged() -> bool:
    return cone.SECRET.exists()

def _side() -> str:
    return "engaged" if engaged() else "disengaged"

def _glyph(side: str) -> str:
    if progress[side] >= {"read", "detect"}: return "✓"
    if visited[side] or progress[side]:      return "~"
    return " "

def _all_done() -> bool:
    return progress["engaged"] >= {"read", "detect"} and progress["disengaged"] >= {"read", "detect"}

def _wipe():
    cone.SECRET.unlink(missing_ok=True)
    try:
        cone.CONE.rmdir()
    except OSError:
        pass
    if HARDCODED.is_symlink():
        HARDCODED.unlink()

def engage():
    if engaged():
        print(GREEN("    The Cone of Silence is already engaged."))
        return
    if not cone.ENC_FILE.exists():
        cone.init()
    cone.materialize()
    HARDCODED.parent.mkdir(parents=True, exist_ok=True)
    if HARDCODED.is_symlink() or HARDCODED.exists():
        HARDCODED.unlink()
    HARDCODED.symlink_to(cone.SECRET)
    visited["engaged"] = True
    print(GREEN("    Cone of Silence ENGAGED — the secret is live, in RAM only."))
    print(DIM(f"    (a softlink at the app's hard-coded path now points into the Cone:"
              f" legacy-etc/{HARDCODED.name})"))

def disengage():
    was = engaged()
    _wipe()
    visited["disengaged"] = True
    print(RED("    Cone of Silence DISENGAGED — the secret has evaporated from RAM.")
          if was else DIM("    The Cone of Silence was already disengaged."))

# --- walkthroughs (one per Cone state) --------------------------------------
def read_secret():
    if engaged():
        coach("The Cone of Silence is in place. Our legacy app reaches her secret the old\n"
              "cleartext way — with no knowledge or awareness of encryption.\n"
              "Only the ENCRYPTED file lives on disk; let's look:")
        shell("ls -la", run=_ls())
        coach("...yet a cleartext secret is readable. Where? A memory-only filesystem —\n"
              "the Cone of Silence. Here are the tmpfs (RAM) mounts:")
        shell("df -h -t tmpfs")
        coach("Our legacy_reader.py starts up exactly as she always has:")
        shell(f"{READER} --config {cone.SECRET}")
        coach("And via a softlink at her HARD-CODED path, she runs with NO arguments, too! —\n"
              "So apps with hard-coded filepaths are supported as well:")
        shell(f"{READER}")
        verdict("legacy_reader_py reads her secret. Nothing on disk changed.", ok=True)
    else:
        coach("The Cone of Silence is lifted. The secret has evaporated from RAM.\n"
              "Only ciphertext remains on disk:")
        shell("ls -la", run=_ls())
        coach("Watch the legacy app try to start with the Cone disengaged — no secret to be had:")
        shell(f"{READER} --config {cone.SECRET}")
        coach("It is the same at her hard-coded path — the softlink is gone, so she fails loudly:")
        shell(f"{READER}")
        verdict("No Cone, no service — loud, early failures make it easy to see what happened.", ok=False)
    progress[_side()].add("read")

def detect():
    grep = (f"grep -rn '{cone.NEEDLE}' . "
            f"--exclude='*.py' --exclude='*.pyc' --exclude='*.html' --exclude='*.md' "
            f"--exclude-dir='__pycache__' || echo '    (nothing found on disk)'")
    if engaged():
        coach("The app just read the secret. So it must be on disk somewhere, right?\n"
              "Lets hunt through the whole directory for the password:")
        shell(grep, run=_grep_color(grep))
        coach("Nothing on disk. The cleartext lives ONLY inside the Cone (RAM). Proof:")
        shell(f"cat {cone.SECRET}", run=_cat(cone.SECRET))
        shell(f"df -h {cone.SECRET}")
        verdict("Readable by the app, invisible to the disk. That is the whole trick.", ok=True)
    else:
        coach("The Cone is lifted. Hunt the disk for the password once more:")
        shell(grep, run=_grep_color(grep))
        coach("And the Cone itself is empty:")
        shell(f"ls -la {cone.CONE} 2>/dev/null || echo '    (the Cone is gone)'")
        coach("Nothing, anywhere. On disk: only ciphertext. In RAM: nothing.")
    progress[_side()].add("detect")

def explore():
    sh = os.environ.get("SHELL", "/bin/bash")
    state = GREEN("ENGAGED") if engaged() else RED("DISENGAGED")
    coach(BOLD("Explorer — forking a shell. Look around all you like; type ")
          + "\033[36mexit\033[0m" + BOLD(" to come back."))
    print(f"    Cone of Silence is currently {state}.  (you're in {HERE})")
    if not sys.stdin.isatty():
        print(DIM("    (no interactive terminal — the explorer needs a real tty; skipping)"))
        return
    subprocess.run([sh], cwd=HERE)
    print(DIM("    ...back from the explorer."))

def enlighten():
    if not WRITEUP.exists():
        print(DIM(f"    write-up not found at {WRITEUP}"))
        return
    for opener in ("xdg-open", "sensible-browser", "open"):
        if _have(opener):
            subprocess.run([opener, str(WRITEUP)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(DIM(f"    opened {WRITEUP.name} in your browser"))
            return
    print(DIM(f"    no GUI opener found — open this yourself: file://{WRITEUP}"))

# --- menu -------------------------------------------------------------------
def menu():
    state = GREEN("ENGAGED ✓") if engaged() else RED("DISENGAGED")
    print("\n" + BOLD("════ The Cone of Silence — an experience ════"))
    print(f"     Cone of Silence: {state}")
    print(f"     Experienced:  [{_glyph('engaged')}] engaged   [{_glyph('disengaged')}] disengaged")
    print()
    print("  0) Enlighten me                  " + DIM("(open the write-up in your browser)"))
    print("  1) Engage the Cone of Silence    " + DIM("(decrypt the secret into RAM)"))
    print("  2) Disengage the Cone of Silence " + DIM("(wipe the secret from RAM)"))
    print("  3) Read the secret               " + DIM("(run the legacy app)"))
    print("  4) Detect cleartext secrets      " + DIM("(hunt the disk for the password)"))
    print("  5) Explore                       " + DIM("(fork a shell; type 'exit' to return)"))
    print("  " + (GREEN("6) Finish") if _all_done() else "6) Abort"))
    print(DIM(f"     what is the Cone of Silence?  {CONE_VIDEO}"))

def main():
    os.chdir(HERE)
    shutil.rmtree(HERE / "__pycache__", ignore_errors=True)  # wipe any stale bytecode
    os.chmod(HERE / "legacy_reader.py", 0o755)
    if not cone.ENC_FILE.exists():
        cone.init()
    _wipe()  # always begin DISENGAGED

    actions = {"0": enlighten, "1": engage, "2": disengage,
               "3": read_secret, "4": detect, "5": explore}
    try:
        while True:
            clear_screen()
            menu()
            print("\n  Please select: ", end="", flush=True)
            try:
                choice = input().strip()
            except EOFError:
                break
            if choice == "6":
                if _all_done():
                    print(GREEN("\n  Finished — you've felt both sides of the Cone. \U0001f44b"))
                else:
                    print(DIM("\n  Aborted."))
                break
            action = actions.get(choice)
            if not action:
                continue  # invalid choice -> just redraw a fresh menu
            action()
            pause()
    finally:
        _wipe()  # never leave a plaintext secret behind

if __name__ == "__main__":
    main()
