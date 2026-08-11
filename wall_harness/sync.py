from __future__ import annotations

import io
import json
import os
import sqlite3
import tempfile
import zipfile
from contextlib import closing
from pathlib import Path, PurePosixPath

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

from .spec import parse_spec
from .web.workspace import WallWorkspace

MAGIC = b"WALLSYNC1"
SALT_SIZE = 16
NONCE_SIZE = 12
MAX_BUNDLE_SIZE = 100 * 1024 * 1024


def derive_key(passphrase: str, salt: bytes) -> bytes:
    return Scrypt(salt=salt, length=32, n=2**14, r=8, p=1).derive(passphrase.encode())


def export_bundle(
    workspace_path: Path,
    destination: Path,
    passphrase: str,
    *,
    state_path: Path | None = None,
    force: bool = False,
) -> None:
    if len(passphrase) < 12:
        raise ValueError("Sync passphrase must contain at least 12 characters")
    if destination.exists() and not force:
        raise FileExistsError("Sync destination exists; pass force=True to replace")
    workspace = WallWorkspace(workspace_path)
    records = workspace.records()
    state_path = state_path or workspace.root / ".wall" / "state.db"
    payload = io.BytesIO()
    spec_names = [record.path.name for record in records]
    with zipfile.ZipFile(payload, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "manifest.json",
            json.dumps({"version": 1, "specs": spec_names}, separators=(",", ":")),
        )
        for record in records:
            archive.writestr(f"specs/{record.path.name}", record.path.read_bytes())
        if state_path.exists():
            archive.writestr("state.db", sqlite_backup(state_path))

    plaintext = payload.getvalue()
    if len(plaintext) > MAX_BUNDLE_SIZE:
        raise ValueError("Sync bundle exceeds the 100 MB safety limit")
    salt, nonce = os.urandom(SALT_SIZE), os.urandom(NONCE_SIZE)
    ciphertext = AESGCM(derive_key(passphrase, salt)).encrypt(nonce, plaintext, MAGIC)
    atomic_write(destination, MAGIC + salt + nonce + ciphertext)


def import_bundle(
    source: Path,
    destination: Path,
    passphrase: str,
    *,
    force: bool = False,
) -> None:
    encrypted = source.read_bytes()
    header_size = len(MAGIC) + SALT_SIZE + NONCE_SIZE
    if len(encrypted) < header_size or not encrypted.startswith(MAGIC):
        raise ValueError("Not a Wall encrypted sync bundle")
    if len(encrypted) > MAX_BUNDLE_SIZE:
        raise ValueError("Encrypted sync bundle exceeds the 100 MB safety limit")
    salt_start = len(MAGIC)
    nonce_start = salt_start + SALT_SIZE
    ciphertext_start = nonce_start + NONCE_SIZE
    salt = encrypted[salt_start:nonce_start]
    nonce = encrypted[nonce_start:ciphertext_start]
    plaintext = AESGCM(derive_key(passphrase, salt)).decrypt(
        nonce, encrypted[ciphertext_start:], MAGIC
    )

    with zipfile.ZipFile(io.BytesIO(plaintext)) as archive:
        validate_archive(archive)
        manifest = json.loads(archive.read("manifest.json"))
        if manifest.get("version") != 1 or not isinstance(manifest.get("specs"), list):
            raise ValueError("Unsupported sync bundle manifest")
        specs: dict[str, bytes] = {}
        for name in manifest["specs"]:
            if not isinstance(name, str) or Path(name).name != name:
                raise ValueError("Invalid WallSpec filename in bundle")
            content = archive.read(f"specs/{name}")
            parse_spec(content.decode("utf-8"))
            specs[name] = content
        state = archive.read("state.db") if "state.db" in archive.namelist() else None

    existing = [*destination.glob("*.yaml"), *destination.glob("*.yml")]
    existing_state = destination / ".wall" / "state.db"
    if not force and (existing or existing_state.exists()):
        raise FileExistsError("Destination already contains Wall data; pass force=True to replace")
    destination.mkdir(parents=True, exist_ok=True)
    for name, content in specs.items():
        atomic_write(destination / name, content)
    if state is not None:
        atomic_write(existing_state, state)


def sqlite_backup(source: Path) -> bytes:
    with tempfile.TemporaryDirectory(prefix="wall-sync-") as temporary:
        backup_path = Path(temporary) / "state.db"
        with closing(sqlite3.connect(source)) as original, closing(
            sqlite3.connect(backup_path)
        ) as backup:
            original.backup(backup)
        return backup_path.read_bytes()


def validate_archive(archive: zipfile.ZipFile) -> None:
    total_size = 0
    for info in archive.infolist():
        path = PurePosixPath(info.filename)
        if path.is_absolute() or ".." in path.parts:
            raise ValueError("Unsafe path in sync bundle")
        total_size += info.file_size
    if total_size > MAX_BUNDLE_SIZE:
        raise ValueError("Expanded sync bundle exceeds the 100 MB safety limit")
    if "manifest.json" not in archive.namelist():
        raise ValueError("Sync bundle has no manifest")


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as temporary:
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
    finally:
        Path(temporary_name).unlink(missing_ok=True)
