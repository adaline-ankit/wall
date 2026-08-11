# Encrypted sync format

Wall sync is an encrypted portable bundle rather than a cloud account. It is intended for moving a
workspace between machines or storing a private backup in a file-sync service.

## Cryptographic construction

- Magic/version marker: `WALLSYNC1`
- KDF: scrypt, random 16-byte salt, `N=16384`, `r=8`, `p=1`, 32-byte output
- Cipher: AES-256-GCM with a random 12-byte nonce
- Associated authenticated data: the magic/version marker
- Payload: ZIP containing a versioned manifest, validated WallSpecs, and a SQLite online backup

AES-GCM authenticates the entire ciphertext. A wrong passphrase or modified archive fails before
any file is written. The importer caps encrypted and expanded data at 100 MB, rejects absolute or
parent-relative archive paths, validates all YAML, writes atomically, and defaults to no overwrite.

Wall cannot recover a lost passphrase. Do not pass a passphrase on the command line; use the hidden
prompt or `WALL_SYNC_PASSPHRASE` in a secure process environment.
