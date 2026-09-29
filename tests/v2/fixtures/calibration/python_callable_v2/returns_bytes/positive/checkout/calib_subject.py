import pathlib


def target(path):
    return pathlib.Path(path).read_bytes()
