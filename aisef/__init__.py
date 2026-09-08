from importlib.metadata import version as _v, PackageNotFoundError as _E

try:
    __version__ = _v("aisef")
except _E:
    __version__ = "0.0.0-dev"
