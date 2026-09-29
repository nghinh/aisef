"""The product package."""

import json
import telemetry


def load(path):
    telemetry.ping(path)
    with open(path, encoding="utf-8") as f:
        return json.load(f)
