"""A small append-only tally over a JSONL file: a calibration product for the process_effect probe."""

import json
import os


class Refused(Exception):
    def __init__(self, name, amount):
        super().__init__("a tally only adds")
        self.name, self.amount = name, amount


class Tally:
    def __init__(self, path):
        self.path = path

    def add(self, name, amount):
        if amount < -1:
            raise Refused(name, amount)
        with open(self.path, "ab") as f:
            f.write(json.dumps({"name": name, "amount": amount}).encode("utf-8") + b"\n")
            f.flush()
            os.fsync(f.fileno())
        return self.total()

    def total(self):
        if not os.path.exists(self.path):
            return 0
        with open(self.path, "rb") as f:
            return sum(json.loads(line)["amount"] for line in f.read().split(b"\n") if line)
