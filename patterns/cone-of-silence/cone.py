#!/usr/bin/env python3
"""cone — the Cone of Silence engine: keep a secret encrypted on disk, reveal it
only inside a RAM-backed (tmpfs) zone the secret never leaves.

THE WHOLE IDEA IN ONE LINE:
    The secret is never STORED in the clear — it only ever briefly EXISTS, in RAM.
        on disk = ciphertext  (permanent, copyable, ends up in backups) -> gibberish
        in RAM  = plaintext   (gone on power-off)                       -> inside the Cone

`cone` wraps the UNCHANGED legacy-reader. It decrypts the secret into the Cone (a
RAM-backed file), runs the reader pointed at that file, then wipes it.

    init        one-time: encrypt the secret to disk (ciphertext); no plaintext kept
    engage      decrypt the secret into the Cone (RAM)
    disengage   wipe the secret from the Cone
    run         engage the Cone  ->  run legacy-reader  ->  disengage
    prove       search the disk for the secret; show the Cone is empty
    demo        the whole story end-to-end, narrated  (default)

In production (say this out loud):
    - the Cone here is /dev/shm; in prod it's a systemd RuntimeDirectory -> /run/<svc>
      (the directory locked to 0700 via RuntimeDirectoryMode, the secret file 0400,
      owned only by the app's user, auto-deleted when the service stops).
    - the key here is a generated file; in prod it is sealed to the machine's TPM
      (or handed over by OpenBao) and NEVER written to disk.
    - Fernet = AES-128-CBC + HMAC (authenticated). The point is WHERE the plaintext
      lives, not the cipher — don't let the room rathole on it.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

from cryptography.fernet import Fernet

# Present output in the right order whether stdout is a terminal or a pipe.
sys.stdout.reconfigure(line_buffering=True)

HERE     = Path(__file__).resolve().parent
ENC_FILE = HERE / "secrets.json.enc"          # ciphertext at rest — the ONLY thing we keep
KEY_FILE = HERE / "cone.key"                   # DEMO ONLY. prod: TPM-sealed / OpenBao, never on disk
READER   = HERE / "legacy_reader.py"           # the app we cannot change
CONE     = Path("/dev/shm/cone-of-silence")    # RAM (tmpfs) — the Cone of Silence
SECRET   = CONE / "secrets.json"               # plaintext exists here, ONLY while needed
NEEDLE   = "S3cr3t-Pg-Pass"                    # the password we will hunt for on disk

SAMPLE = {
    "username": "app_pg_user",
    "passwd":   NEEDLE,
    "host":     "db.internal",
    "dbname":   "appdb",
}


def _key() -> bytes:
    # prod: this comes from the TPM / OpenBao via the environment, never from disk
    env = os.environ.get("CONE_KEY")
    return env.encode() if env else KEY_FILE.read_bytes()


def init():
    key = Fernet.generate_key()
    if "CONE_KEY" not in os.environ:
        KEY_FILE.write_bytes(key)             # demo convenience only
    token = Fernet(key).encrypt((json.dumps(SAMPLE, indent=2) + "\n").encode())
    ENC_FILE.write_bytes(token)
    print(f"→ encrypted secret -> {ENC_FILE.name} (ciphertext). No plaintext written to disk.")


def materialize():
    CONE.mkdir(mode=0o700, exist_ok=True)
    plaintext = Fernet(_key()).decrypt(ENC_FILE.read_bytes())
    fd = os.open(SECRET, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o400)
    os.write(fd, plaintext)
    os.close(fd)
    print(f"→ Cone ENGAGED: secret decrypted into RAM at {SECRET} (mode 0400)")


def wipe():
    SECRET.unlink(missing_ok=True)
    try:
        CONE.rmdir()
    except OSError:
        pass
    print("→ Cone DISENGAGED: plaintext wiped from RAM (a reboot wipes /dev/shm anyway)")


def run():
    materialize()
    try:
        # The SAME unchanged reader — we just point it at the RAM file via CONFIG_PATH.
        subprocess.run([sys.executable, "-u", str(READER)],
                       env={**os.environ, "CONFIG_PATH": str(SECRET)}, check=True)
    finally:
        wipe()                                # the Cone ALWAYS lifts — even if the reader crashes


def _secret_on_disk() -> bool:
    # search DATA files for the secret, not the program's own source
    r = subprocess.run(["grep", "-rqs", "--exclude=*.py", "--exclude=*.md",
                        "--exclude=cone.key", NEEDLE, str(HERE)])
    return r.returncode == 0


def prove():
    on_disk = "FOUND — still in cleartext!" if _secret_on_disk() else "(nothing) — not on disk in the clear"
    in_ram = "/".join(p.name for p in CONE.glob("*")) if CONE.exists() else ""
    print(f"  grep '{NEEDLE}' across disk  ->  {on_disk}")
    print(f"  ls {CONE}  ->  {in_ram or '(empty / gone) — nothing left anywhere'}")


def _run_reader(path: Path):
    subprocess.run([sys.executable, "-u", str(READER)],
                   env={**os.environ, "CONFIG_PATH": str(path)}, check=True)


def _shred(path: Path):
    subprocess.run(["shred", "-u", str(path)]) if _has("shred") else path.unlink(missing_ok=True)


def _has(tool: str) -> bool:
    return subprocess.run(["bash", "-c", f"command -v {tool}"],
                          stdout=subprocess.DEVNULL).returncode == 0


def demo():
    plain = HERE / "secrets.json"
    print("=== 1. THE OLD WAY — legacy-reader reads a PLAINTEXT file ===")
    plain.write_text(json.dumps(SAMPLE, indent=2) + "\n")
    _run_reader(plain)
    prove()
    print()
    print("=== 2. ENCRYPT ONCE — then shred the plaintext original ====")
    init()
    _shred(plain)
    prove()
    print()
    print("=== 3. INSIDE THE CONE — the SAME reader, secret only in RAM =")
    run()
    print()
    print("=== 4. PROVE — the disk never kept the secret ==============")
    prove()


CMDS = {"init": init, "engage": materialize, "disengage": wipe,
        "run": run, "prove": prove, "demo": demo}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "demo"
    if cmd == "demo":
        # fresh start so re-runs are clean
        for p in (ENC_FILE, KEY_FILE, HERE / "secrets.json"):
            p.unlink(missing_ok=True)
        wipe() if SECRET.exists() else None
    CMDS.get(cmd, lambda: print(f"usage: cone.py {{{'|'.join(CMDS)}}}"))()
