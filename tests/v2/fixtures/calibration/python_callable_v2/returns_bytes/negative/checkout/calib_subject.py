import pathlib


def target(path):
    return pathlib.Path(path).read_text(encoding='utf-8')
