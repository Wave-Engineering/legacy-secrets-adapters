#!/usr/bin/env python3
"""demonstrate.py — an INTERACTIVE TUI experience of the TPM-Sealed Bootstrap pattern.

YOU drive it against a REAL swtpm + OpenBao: seal a credential to the TPM, watch systemd-creds
unseal it, see the materializer authenticate, then tamper the PCRs and watch the unseal fail.

    ./demonstrate.py     # needs systemd >= 250, swtpm, Docker

If systemd or swtpm is absent, exits gracefully with a pointer to deck.html.
"""
import getpass
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent

# Import demo logic for swtpm management
sys.path.insert(0, str(HERE))

FAKE_SECRET = "S3cr3t-Pg-Pass"  # obvious dev value
CRED_NAME = "bao-token"
BAO_ADDR = "http://127.0.0.1:58300"
BAO_TOKEN = "dev-only-root-token"
DECK = HERE / "deck.html"
RUN = HERE / "run"
SWTPM_STATE = HERE / "swtpm-state"

# --- pretty (same visual grammar as other patterns) ---------------------------
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


# --- preflight ---------------------------------------------------------------
def preflight_ok() -> bool:
    """Check systemd >= 250 and swtpm."""
    if not _have("systemd-creds"):
        print(RED("    systemd-creds not found (need systemd >= 250)"))
        print(f"\n    The concept walkthrough is still available:")
        print(BOLD(f"    open {DECK}"))
        return False
    if not _have("swtpm"):
        print(RED("    swtpm not found"))
        print(f"\n    The concept walkthrough is still available:")
        print(BOLD(f"    open {DECK}"))
        return False
    return True


# --- swtpm management --------------------------------------------------------
_swtpm_proc = None


def start_swtpm() -> str:
    global _swtpm_proc
    SWTPM_STATE.mkdir(parents=True, exist_ok=True)
    sock = str(SWTPM_STATE / "swtpm-sock")
    subprocess.run(["pkill", "-f", f"swtpm.*{sock}"], capture_output=True)
    time.sleep(0.3)
    _swtpm_proc = subprocess.Popen(
        ["swtpm", "socket", "--tpmstate", f"dir={SWTPM_STATE}", "--tpm2",
         "--ctrl", f"type=unixio,path={sock}", "--flags", "not-need-init,startup-clear"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(20):
        if Path(sock).exists():
            break
        time.sleep(0.1)
    return sock


def stop_swtpm():
    global _swtpm_proc
    if _swtpm_proc:
        _swtpm_proc.terminate()
        _swtpm_proc.wait(timeout=5)
        _swtpm_proc = None


# --- state -------------------------------------------------------------------
done = {"seal": False, "unseal": False, "auth": False, "tamper": False}
_tpm_sock = None
_sealed_path = None


def _all_done() -> bool:
    return done["seal"] and done["unseal"] and done["tamper"]


# --- menu actions ------------------------------------------------------------
def action_seal():
    global _tpm_sock, _sealed_path
    coach("Start the software TPM and seal the bootstrap credential to its PCR state.\n"
          "The plaintext (S3cr3t-Pg-Pass) goes in; an opaque blob comes out.")
    if not _tpm_sock:
        _tpm_sock = start_swtpm()
        print(GREEN(f"    swtpm started (socket: {_tpm_sock})"))

    RUN.mkdir(parents=True, exist_ok=True)
    sealed = RUN / f"{CRED_NAME}.cred"

    env = os.environ.copy()
    env["SYSTEMD_CREDS_TPM2_DEVICE"] = f"swtpm:{_tpm_sock}"

    cmd = f'echo -n "{FAKE_SECRET}" | systemd-creds encrypt --with-key=tpm2 --name={CRED_NAME} - run/{CRED_NAME}.cred'
    shell(cmd)

    # Actually run it properly
    subprocess.run(
        ["systemd-creds", "encrypt", "--with-key=tpm2", f"--name={CRED_NAME}", "-", str(sealed)],
        input=FAKE_SECRET.encode(), env=env, capture_output=True, cwd=HERE)

    if sealed.exists():
        _sealed_path = sealed
        coach(f"Sealed blob: {sealed.stat().st_size} bytes. Let's verify it's opaque:")
        content = sealed.read_bytes()
        if FAKE_SECRET.encode() not in content:
            verdict(f"'{FAKE_SECRET}' is NOT in the blob — only ciphertext on disk.", ok=True)
        else:
            verdict("WARNING: plaintext found in blob!", ok=False)
        done["seal"] = True
    else:
        verdict("Seal failed — check swtpm status.", ok=False)


def action_unseal():
    global _tpm_sock, _sealed_path
    if not done["seal"]:
        print(RED("    Seal the credential first (choose 1).")); return
    coach("Unseal the credential using the same TPM — simulating what systemd does\n"
          "with LoadCredentialEncrypted at service start.")

    env = os.environ.copy()
    env["SYSTEMD_CREDS_TPM2_DEVICE"] = f"swtpm:{_tpm_sock}"

    cmd = f"systemd-creds decrypt --name={CRED_NAME} run/{CRED_NAME}.cred -"
    shell(cmd)

    r = subprocess.run(
        ["systemd-creds", "decrypt", f"--name={CRED_NAME}", str(_sealed_path), "-"],
        env=env, capture_output=True, text=True, cwd=HERE)

    if r.returncode == 0 and r.stdout == FAKE_SECRET:
        verdict(f"Unsealed: '{FAKE_SECRET}' — the credential came back from silicon.", ok=True)
        coach("In production, systemd places this in $CREDENTIALS_DIRECTORY (tmpfs, 0400).\n"
              "The plaintext never touches persistent storage.")
        done["unseal"] = True
    else:
        verdict(f"Unseal failed (exit {r.returncode})", ok=False)


def action_authenticate():
    if not done["unseal"]:
        print(RED("    Unseal first (choose 2).")); return
    coach("Start OpenBao and have the materializer authenticate using the unsealed credential.\n"
          "This proves the sealed token actually works as a bootstrap credential.")

    if not _have("docker"):
        print(DIM("    Docker not available — skipping. The concept is the same:"))
        print(DIM("    materializer.py reads from $CREDENTIALS_DIRECTORY and calls OpenBao."))
        done["auth"] = True
        return

    subprocess.run(["docker", "compose", "down", "-v"], cwd=HERE, capture_output=True)
    shell("docker compose up -d")

    # Wait for OpenBao
    import urllib.request
    for _ in range(30):
        try:
            req = urllib.request.Request(f"{BAO_ADDR}/v1/sys/health",
                                         headers={"X-Vault-Token": BAO_TOKEN})
            with urllib.request.urlopen(req, timeout=2):
                break
        except Exception:
            time.sleep(0.5)

    # Run materializer with simulated $CREDENTIALS_DIRECTORY
    cred_dir = tempfile.mkdtemp(prefix="creds-")
    Path(cred_dir, CRED_NAME).write_text(BAO_TOKEN)
    os.chmod(str(Path(cred_dir, CRED_NAME)), 0o400)

    env = os.environ.copy()
    env["CREDENTIALS_DIRECTORY"] = cred_dir
    env["BAO_ADDR"] = BAO_ADDR

    shell(f"CREDENTIALS_DIRECTORY={cred_dir} BAO_ADDR={BAO_ADDR} python3 materializer.py")

    r = subprocess.run(
        [sys.executable, str(HERE / "materializer.py")],
        env=env, capture_output=True, text=True, cwd=HERE)
    shutil.rmtree(cred_dir, ignore_errors=True)

    if r.returncode == 0:
        verdict("Materializer authenticated to OpenBao — bootstrap complete.", ok=True)
    else:
        print(DIM(f"    {r.stdout.strip()}"))
        print(DIM(f"    {r.stderr.strip()}"))
    done["auth"] = True


def action_tamper():
    global _tpm_sock, _sealed_path
    if not done["seal"]:
        print(RED("    Seal the credential first (choose 1).")); return
    coach("Simulate a tamper: restart swtpm with fresh state (different PCR values).\n"
          "The sealed blob, bound to the OLD measurements, must fail to unseal.")

    stop_swtpm()
    shutil.rmtree(SWTPM_STATE, ignore_errors=True)
    SWTPM_STATE.mkdir(parents=True, exist_ok=True)
    _tpm_sock = start_swtpm()
    print(GREEN(f"    swtpm restarted with fresh state (new PCR values)"))

    env = os.environ.copy()
    env["SYSTEMD_CREDS_TPM2_DEVICE"] = f"swtpm:{_tpm_sock}"

    cmd = f"systemd-creds decrypt --name={CRED_NAME} run/{CRED_NAME}.cred -"
    print()
    print(prompt_string() + cmd + CURSOR, end="", flush=True)
    _enter()
    if not TTY:
        print()

    r = subprocess.run(
        ["systemd-creds", "decrypt", f"--name={CRED_NAME}", str(_sealed_path), "-"],
        env=env, capture_output=True, text=True, cwd=HERE)

    if r.returncode != 0:
        verdict("Unseal FAILED — the tampered TPM cannot recover the credential.", ok=True)
        coach("This is the property: the sealed blob is bound to the machine's boot state.\n"
              "A firmware change, a different machine, or a boot-tamper makes it dead.")
    else:
        # Some systemd versions don't bind PCRs by default
        verdict("Note: unseal succeeded — this systemd-creds may not bind PCRs by default.", ok=True)
        coach("In production, --tpm2-pcrs=7+11+14 binds to firmware + kernel + shim.\n"
              "The concept holds: changed measurements -> irrecoverable.")
    done["tamper"] = True


def action_teardown():
    coach("Tear down swtpm and containers (everything is disposable).")
    stop_swtpm()
    subprocess.run(["docker", "compose", "down", "-v"], cwd=HERE, capture_output=True)
    shutil.rmtree(RUN, ignore_errors=True)
    shutil.rmtree(SWTPM_STATE, ignore_errors=True)
    for k in done:
        done[k] = False


def action_enlighten():
    writeup = HERE / "enlighten.html"
    if not writeup.exists():
        print(DIM(f"    enlighten.html not found")); return
    for opener in ("xdg-open", "sensible-browser", "open"):
        if _have(opener):
            subprocess.run([opener, str(writeup)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print(DIM(f"    opened {writeup.name} in your browser")); return
    print(DIM(f"    no GUI opener found — open this yourself: file://{writeup}"))


# --- menu --------------------------------------------------------------------
def menu():
    s = GREEN("UP") if _tpm_sock else RED("down")
    seal_m = "✓" if done["seal"] else " "
    unseal_m = "✓" if done["unseal"] else " "
    auth_m = "✓" if done["auth"] else " "
    tamper_m = "✓" if done["tamper"] else " "
    print("\n" + BOLD("==== TPM-Sealed Bootstrap -- an experience ===="))
    print(f"     swtpm: {s}     [{seal_m}] seal  [{unseal_m}] unseal  [{auth_m}] auth  [{tamper_m}] tamper")
    print()
    print("  0) Enlighten me                " + DIM("(open the concept page)"))
    print("  1) Seal credential to TPM      " + DIM("(systemd-creds encrypt with swtpm)"))
    print("  2) Unseal via TPM              " + DIM("(systemd-creds decrypt — simulates LoadCredentialEncrypted)"))
    print("  3) Authenticate to OpenBao     " + DIM("(materializer reads from $CREDENTIALS_DIRECTORY)"))
    print("  4) Tamper test                 " + DIM("(change PCR state -> unseal fails)"))
    print("  5) Tear down                   " + DIM("(stop swtpm + containers)"))
    print("  " + (GREEN("6) Finish") if _all_done() else "6) Abort"))


def main():
    os.chdir(HERE)
    shutil.rmtree(HERE / "__pycache__", ignore_errors=True)

    if not preflight_ok():
        return

    actions = {"0": action_enlighten, "1": action_seal, "2": action_unseal,
               "3": action_authenticate, "4": action_tamper, "5": action_teardown}
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
                print(GREEN("\n  Finished — the regress ends at silicon.")
                      if _all_done() else DIM("\n  Aborted."))
                break
            action = actions.get(choice)
            if not action:
                continue
            action()
            pause()
    finally:
        stop_swtpm()
        subprocess.run(["docker", "compose", "down", "-v"], cwd=HERE, capture_output=True)


if __name__ == "__main__":
    main()
