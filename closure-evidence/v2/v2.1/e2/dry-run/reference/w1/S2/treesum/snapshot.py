"""Reference implementation for the E2 dry run only (never given to any real arm). §2 of docs/requirements.md:
story S2's slice of the W1-a reference (`build` only; S3 adds dumps/loads/compare)."""
import os

from treesum.digest import file_sha256


def build(root):
    if not os.path.isdir(root):
        raise NotADirectoryError(str(root))
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.isfile(full):
                out[os.path.relpath(full, root).replace(os.sep, "/")] = file_sha256(full)
    return dict(sorted(out.items()))
