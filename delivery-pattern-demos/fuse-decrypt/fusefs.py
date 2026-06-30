#!/usr/bin/env python3
"""fusefs.py — a FUSE filesystem that decrypts on read and encrypts on write.

Ciphertext lives on the real filesystem; the FUSE layer presents a plaintext view.
Uses AES-256-GCM via the `cryptography` library for authenticated encryption.

Architecture:
    real_dir/            <- ciphertext at rest (each file = nonce‖ciphertext‖tag)
    mount_point/         <- FUSE mount; reads decrypt, writes encrypt transparently

The legacy app opens files under mount_point/ and sees plaintext. On disk (real_dir/)
only ciphertext exists. Key is held in memory by the FUSE daemon — never on disk in
production (here: loaded from a demo keyfile or env var).

Requires: pyfuse3, cryptography, /dev/fuse + kernel FUSE module.
"""
import errno
import os
import stat
import sys
import time
from pathlib import Path

import pyfuse3
import trio

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

# --- Crypto helpers -----------------------------------------------------------

NONCE_SIZE = 12  # 96-bit nonce for AES-GCM


def encrypt_blob(key: bytes, plaintext: bytes) -> bytes:
    """Encrypt plaintext -> nonce || ciphertext+tag."""
    aesgcm = AESGCM(key)
    nonce = os.urandom(NONCE_SIZE)
    ct = aesgcm.encrypt(nonce, plaintext, None)
    return nonce + ct


def decrypt_blob(key: bytes, blob: bytes) -> bytes:
    """Decrypt nonce || ciphertext+tag -> plaintext."""
    if len(blob) < NONCE_SIZE + 16:  # nonce + minimum tag
        raise ValueError("blob too short to contain nonce + ciphertext")
    aesgcm = AESGCM(key)
    nonce = blob[:NONCE_SIZE]
    ct = blob[NONCE_SIZE:]
    return aesgcm.decrypt(nonce, ct, None)


# --- FUSE Operations ----------------------------------------------------------

class DecryptFS(pyfuse3.Operations):
    """A FUSE filesystem that transparently decrypts/encrypts files.

    Maps each file in `source_dir` (ciphertext) to a plaintext view at the
    mountpoint. Directories are passed through; only regular file content
    is transformed.
    """

    def __init__(self, source_dir: Path, key: bytes):
        super().__init__()
        self.source_dir = source_dir.resolve()
        self.key = key
        # inode tracking: inode -> real path
        self._inode_to_path: dict[int, Path] = {}
        self._path_to_inode: dict[Path, int] = {}
        self._next_inode = pyfuse3.ROOT_INODE + 1
        # File handles: fh -> (inode, plaintext_buffer, dirty)
        self._fh_map: dict[int, dict] = {}
        self._next_fh = 1
        # Register root
        self._inode_to_path[pyfuse3.ROOT_INODE] = self.source_dir
        self._path_to_inode[self.source_dir] = pyfuse3.ROOT_INODE

    def _real_path(self, inode: int) -> Path:
        return self._inode_to_path[inode]

    def _get_inode(self, path: Path) -> int:
        path = path.resolve()
        if path in self._path_to_inode:
            return self._path_to_inode[path]
        ino = self._next_inode
        self._next_inode += 1
        self._inode_to_path[ino] = path
        self._path_to_inode[path] = ino
        return ino

    def _getattr(self, path: Path) -> pyfuse3.EntryAttributes:
        """Build EntryAttributes from a real path, adjusting size for plaintext."""
        st = path.lstat()
        entry = pyfuse3.EntryAttributes()
        entry.st_ino = self._get_inode(path)
        entry.st_mode = st.st_mode
        entry.st_nlink = st.st_nlink
        entry.st_uid = st.st_uid
        entry.st_gid = st.st_gid
        entry.st_rdev = st.st_rdev
        entry.st_atime_ns = st.st_atime_ns
        entry.st_mtime_ns = st.st_mtime_ns
        entry.st_ctime_ns = st.st_ctime_ns
        entry.generation = 0
        entry.attr_timeout = 1
        entry.entry_timeout = 1

        if stat.S_ISREG(st.st_mode) and st.st_size > 0:
            # Report plaintext size (decrypt to measure)
            try:
                blob = path.read_bytes()
                pt = decrypt_blob(self.key, blob)
                entry.st_size = len(pt)
            except Exception:
                entry.st_size = 0
        else:
            entry.st_size = st.st_size
        entry.st_blksize = 512
        entry.st_blocks = (entry.st_size + 511) // 512
        return entry

    async def getattr(self, inode, ctx=None):
        path = self._real_path(inode)
        return self._getattr(path)

    async def lookup(self, parent_inode, name, ctx=None):
        name = os.fsdecode(name)
        parent_path = self._real_path(parent_inode)
        child_path = parent_path / name
        if not child_path.exists():
            raise pyfuse3.FUSEError(errno.ENOENT)
        return self._getattr(child_path)

    async def opendir(self, inode, ctx):
        return inode

    async def readdir(self, fh, start_id, token):
        path = self._real_path(fh)
        entries = sorted(path.iterdir(), key=lambda p: p.name)
        for idx, child in enumerate(entries, start=1):
            if idx <= start_id:
                continue
            child_ino = self._get_inode(child)
            st = child.lstat()
            if not pyfuse3.readdir_reply(token, os.fsencode(child.name),
                                          self._getattr(child), idx):
                break

    async def open(self, inode, flags, ctx):
        path = self._real_path(inode)
        # Decrypt file content into memory buffer
        if path.exists() and path.stat().st_size > 0:
            blob = path.read_bytes()
            try:
                plaintext = decrypt_blob(self.key, blob)
            except Exception:
                plaintext = b""
        else:
            plaintext = b""

        fh = self._next_fh
        self._next_fh += 1
        self._fh_map[fh] = {"inode": inode, "buf": bytearray(plaintext), "dirty": False}
        return pyfuse3.FileInfo(fh=fh)

    async def read(self, fh, offset, length):
        info = self._fh_map[fh]
        buf = info["buf"]
        return bytes(buf[offset:offset + length])

    async def write(self, fh, offset, data):
        info = self._fh_map[fh]
        buf = info["buf"]
        end = offset + len(data)
        if end > len(buf):
            buf.extend(b'\x00' * (end - len(buf)))
        buf[offset:end] = data
        info["dirty"] = True
        return len(data)

    async def release(self, fh):
        info = self._fh_map.pop(fh, None)
        if info and info["dirty"]:
            # Flush: encrypt and write back to source
            path = self._real_path(info["inode"])
            ct = encrypt_blob(self.key, bytes(info["buf"]))
            path.write_bytes(ct)

    async def create(self, parent_inode, name, mode, flags, ctx):
        name = os.fsdecode(name)
        parent_path = self._real_path(parent_inode)
        child_path = parent_path / name
        # Create an empty ciphertext file
        ct = encrypt_blob(self.key, b"")
        child_path.write_bytes(ct)
        os.chmod(child_path, mode)

        ino = self._get_inode(child_path)
        fh = self._next_fh
        self._next_fh += 1
        self._fh_map[fh] = {"inode": ino, "buf": bytearray(), "dirty": False}
        return (pyfuse3.FileInfo(fh=fh), self._getattr(child_path))

    async def setattr(self, inode, attr, fields, fh, ctx):
        # Minimal setattr — just return current attrs
        path = self._real_path(inode)
        return self._getattr(path)

    async def unlink(self, parent_inode, name, ctx):
        name = os.fsdecode(name)
        parent_path = self._real_path(parent_inode)
        child_path = parent_path / name
        child_path.unlink()

    async def statfs(self, ctx):
        sfs = pyfuse3.StatvfsData()
        st = os.statvfs(str(self.source_dir))
        sfs.f_bsize = st.f_bsize
        sfs.f_frsize = st.f_frsize
        sfs.f_blocks = st.f_blocks
        sfs.f_bfree = st.f_bfree
        sfs.f_bavail = st.f_bavail
        sfs.f_files = st.f_files
        sfs.f_ffree = st.f_ffree
        sfs.f_favail = st.f_favail
        sfs.f_namemax = 255
        return sfs


def load_key(key_path: Path | None = None) -> bytes:
    """Load AES-256 key from env or file. DEMO ONLY — prod: from TPM/OpenBao."""
    env_key = os.environ.get("FUSE_DECRYPT_KEY")
    if env_key:
        return bytes.fromhex(env_key)
    if key_path and key_path.exists():
        return bytes.fromhex(key_path.read_text().strip())
    raise RuntimeError("No key: set FUSE_DECRYPT_KEY env or provide a keyfile")


def generate_key() -> bytes:
    """Generate a fresh AES-256 key (32 bytes)."""
    return os.urandom(32)


def mount_fs(source_dir: Path, mount_point: Path, key: bytes):
    """Mount the decrypt filesystem (blocking — runs the FUSE event loop)."""
    mount_point.mkdir(parents=True, exist_ok=True)
    ops = DecryptFS(source_dir, key)
    fuse_options = set(pyfuse3.default_options)
    fuse_options.add("fsname=fuse-decrypt")
    fuse_options.discard("default_permissions")
    pyfuse3.init(ops, str(mount_point), fuse_options)
    try:
        trio.run(pyfuse3.main)
    finally:
        pyfuse3.close(unmount=True)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(f"usage: {sys.argv[0]} <source_dir> <mount_point> [keyfile]")
        sys.exit(1)
    source = Path(sys.argv[1])
    mount = Path(sys.argv[2])
    kf = Path(sys.argv[3]) if len(sys.argv) > 3 else None
    key = load_key(kf)
    print(f"mounting {source} -> {mount} (AES-256-GCM, decrypt-on-read)")
    mount_fs(source, mount, key)
