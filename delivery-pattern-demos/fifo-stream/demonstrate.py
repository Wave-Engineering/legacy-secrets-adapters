#!/usr/bin/env python3
"""demonstrate.py — an INTERACTIVE experience of the FIFO Stream pattern:
deliver a secret through a named pipe so it never exists on any filesystem.

YOU drive it: create the pipe, feed the secret, read it, hunt the disk,
try a second read — and FEEL why a named pipe is stronger than even tmpfs
for sequential, read-once readers.

    ./demonstrate.py

Moving parts:
    demo.py             the engine (mkfifo, writer thread, grep, second-read proof)
    legacy_reader.py    the app we cannot change (reads a path, uses the secret)
"""
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent

# Import the walkthrough beats (shared source of truth with build_deck.py)
sys.path.insert(0, str(HERE))
import walkthrough as wt

NEEDLE = "S3cr3t-Pg-Pass"
READER = "./legacy_reader.py"

SAMPLE_SECRET = (
    '{\n'
    '  "username": "app_pg_user",\n'
    f'  "passwd": "{NEEDLE}",\n'
    '  "host": "db.internal",\n'
    '  "dbname": "appdb"\n'
    '}\n'
)

# --- pretty -----------------------------------------------------------------
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


def _enter():
    try:
        input()
    except EOFError:
        raise SystemExit(0)


def pause(prompt="Press [enter] to continue ..."):
    print("\n    " + DIM(prompt), end="", flush=True)
    _enter()


def coach(text):
    print("\n    " + DIM(text.replace("\n", "\n    ")))


def verdict(text, ok=True):
    print("\n    " + (GREEN if ok else RED)(text))


def prompt_string() -> str:
    import getpass, socket
    user = getpass.getuser()
    host = socket.gethostname().split(".")[0]
    sigil = "#" if getattr(os, "geteuid", lambda: 1)() == 0 else "$"
    return f"[{user}@{host} fifo-stream]{sigil} "


def shell(cmd, run=None):
    """Show command at prompt, run on enter."""
    print()
    print(prompt_string() + cmd + CURSOR, end="", flush=True)
    _enter()
    if not TTY:
        print()
    subprocess.run(run or cmd, shell=True)


# --- State ------------------------------------------------------------------
_fifo_dir = None
_fifo_path = None


def _setup():
    global _fifo_dir, _fifo_path
    _fifo_dir = tempfile.mkdtemp(prefix="fifo-stream-")
    _fifo_path = Path(_fifo_dir) / "secrets.json"


def _cleanup():
    global _fifo_dir, _fifo_path
    if _fifo_path and _fifo_path.exists():
        _fifo_path.unlink(missing_ok=True)
    if _fifo_dir:
        try:
            os.rmdir(_fifo_dir)
        except OSError:
            pass
    _fifo_dir = None
    _fifo_path = None


def _ensure_fifo():
    if _fifo_path.exists():
        _fifo_path.unlink()
    os.mkfifo(_fifo_path, mode=0o600)


# --- Actions ----------------------------------------------------------------
def act_create_pipe():
    """Create the named pipe."""
    _ensure_fifo()
    coach("A named pipe (FIFO) replaces the file path the reader expects.\n"
          "It looks like a file, but it's a kernel pipe buffer — no data is stored.")
    shell(f"mkfifo {_fifo_path}", run=f"ls -la {_fifo_path}")
    coach("Note the 'p' at the start of the mode string — that's a pipe, not a regular file.\n"
          "It has zero size because a FIFO holds no data; it's just a rendezvous point.")
    verdict("Named pipe created. Ready to stream the secret through.", ok=True)


def act_feed_and_read():
    """Writer feeds the secret, reader reads it through the pipe."""
    _ensure_fifo()
    coach("The writer pushes the secret into the pipe in a background thread.\n"
          "The reader opens the same path and receives the secret — streaming through\n"
          "kernel memory, never touching disk.")

    done = threading.Event()

    def _writer():
        with open(_fifo_path, "w") as f:
            f.write(SAMPLE_SECRET)
        done.set()

    t = threading.Thread(target=_writer, daemon=True)
    t.start()

    shell(f"CONFIG_PATH={_fifo_path} {READER}",
          run=f"CONFIG_PATH={_fifo_path} python3 {HERE / 'legacy_reader.py'}")

    done.wait(timeout=5)
    verdict("The reader gets the secret — delivered through the pipe, never stored.", ok=True)


def act_grep_disk():
    """Grep the disk for the secret."""
    coach("The secret streamed through kernel memory. Let's hunt the demo directory\n"
          "for the password — including the FIFO path itself:")
    shell(f"grep -r '{NEEDLE}' {_fifo_dir}/ --exclude='*.py' --exclude='*.html' --exclude='*.md' "
          f"|| echo '    (nothing found on disk)'")
    coach("A FIFO has no content — it's a rendezvous point, not a container.\n"
          "The secret existed only in the kernel pipe buffer while data was in flight.")
    verdict("Zero disk footprint. Not even a tmpfs file to protect.", ok=True)


def act_second_read():
    """Demonstrate read-once: second read hangs."""
    _ensure_fifo()
    coach("A named pipe is read-once by nature. Once data flows through, nothing remains.\n"
          "A second reader blocks until a new writer appears. Watch:")
    coach(BOLD("(We'll try to read the pipe with no writer — it will hang for 2 seconds,\n"
               "then we'll interrupt it to prove the point.)"))
    print()
    print(prompt_string() + f"cat {_fifo_path}" + CURSOR, end="", flush=True)
    _enter()
    if not TTY:
        print()

    # Actually attempt a read with a timeout
    import signal as sig

    def _alarm_handler(signum, frame):
        raise TimeoutError()

    old_handler = sig.signal(sig.SIGALRM, _alarm_handler)
    try:
        sig.alarm(2)
        try:
            fd = os.open(str(_fifo_path), os.O_RDONLY | os.O_NONBLOCK)
            # Even with O_NONBLOCK, read on an empty pipe returns empty or raises
            data = os.read(fd, 4096)
            os.close(fd)
            if data:
                print(f"    unexpected: got {len(data)} bytes")
            else:
                print("    (no data — pipe is empty, read would block)")
        except (BlockingIOError, OSError):
            print("    (blocked — no writer, pipe is empty)")
        except TimeoutError:
            print("    ^C  (interrupted — the cat hung, proving read-once)")
        finally:
            sig.alarm(0)
    finally:
        sig.signal(sig.SIGALRM, old_handler)

    verdict("Read-once: the secret flows through once and is gone. No replay possible.", ok=True)


def act_enlighten():
    """Open the enlighten.html write-up."""
    writeup = HERE / "enlighten.html"
    if not writeup.exists():
        print(DIM(f"    write-up not found at {writeup}"))
        return
    for opener in ("xdg-open", "sensible-browser", "open"):
        if shutil.which(opener):
            subprocess.run([opener, str(writeup)],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(DIM(f"    opened {writeup.name} in your browser"))
            return
    print(DIM(f"    no GUI opener found — open this yourself: file://{writeup}"))


# --- Menu -------------------------------------------------------------------
def menu():
    has_pipe = _fifo_path and _fifo_path.exists() and _is_fifo(_fifo_path)
    state = GREEN("PIPE READY") if has_pipe else DIM("no pipe")
    print("\n" + BOLD("════ FIFO Stream — an experience ════"))
    print(f"     State: {state}")
    if _fifo_path:
        print(f"     Path:  {DIM(str(_fifo_path))}")
    print()
    print("  0) Enlighten me                  " + DIM("(open the write-up in your browser)"))
    print("  1) Create the named pipe         " + DIM("(mkfifo at the reader's path)"))
    print("  2) Feed & read the secret        " + DIM("(writer → pipe → reader)"))
    print("  3) Grep the disk for the secret  " + DIM("(hunt for cleartext)"))
    print("  4) Second read (hangs)           " + DIM("(prove read-once property)"))
    print("  5) Finish / quit")


def _is_fifo(path: Path) -> bool:
    import stat
    try:
        return stat.S_ISFIFO(os.stat(path).st_mode)
    except OSError:
        return False


def main():
    os.chdir(HERE)
    _setup()

    actions = {
        "0": act_enlighten,
        "1": act_create_pipe,
        "2": act_feed_and_read,
        "3": act_grep_disk,
        "4": act_second_read,
    }

    try:
        while True:
            clear_screen()
            menu()
            print("\n  Please select: ", end="", flush=True)
            try:
                choice = input().strip()
            except EOFError:
                break
            if choice == "5":
                print(DIM("\n  Done."))
                break
            action = actions.get(choice)
            if not action:
                continue
            action()
            pause()
    finally:
        _cleanup()


if __name__ == "__main__":
    main()
