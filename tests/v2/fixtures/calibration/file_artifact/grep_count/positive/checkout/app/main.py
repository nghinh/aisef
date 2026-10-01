"""The product package."""

import json


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)
