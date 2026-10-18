"""Reference implementation for the W1-a dry check only (never given to any arm). §1 of docs/requirements.md."""
import hashlib


def file_sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()
