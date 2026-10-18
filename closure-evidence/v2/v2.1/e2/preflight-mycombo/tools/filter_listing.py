"""Filter the one /v1/models listing: the mycombo rows, the owner field's values, the row keys; never the key."""
import collections
import json
import os
import pathlib

here = pathlib.Path(__file__).resolve().parent / "listing"
raw = (here / "models.json").read_text(encoding="utf-8")
key = os.environ.get("NINEROUTER_API_KEY", "")
print("key string present in listing body:", bool(key) and key in raw)
d = json.loads(raw)
print("top-level keys:", sorted(d))
rows = d.get("data") or []
print("models listed:", len(rows))
owners = collections.Counter(str(r.get("owned_by")) for r in rows)
print("owned_by values (count):", dict(owners.most_common()))
my = [r for r in rows if "mycombo" in str(r.get("id", "")).lower()]
print("rows whose id contains mycombo:", len(my))
print(json.dumps(my, indent=1, sort_keys=True))
print("exact id == mycombo:", sum(1 for r in rows if r.get("id") == "mycombo"))
keys = collections.Counter(k for r in rows for k in r)
print("row keys (count):", dict(keys))
out = {"when": (here / "listing-when.txt").read_text().strip(), "http": (here / "listing-http.txt").read_text().strip(),
       "request": "GET https://9router.vnteki.com/v1/models (curl 8.7.1, bearer expanded inside curl from env NINEROUTER_API_KEY)",
       "models_listed": len(rows), "owned_by_values": dict(owners.most_common()), "row_keys": dict(keys), "mycombo_rows": my}
(here / "models-mycombo.json").write_text(json.dumps(out, indent=1, sort_keys=True) + "\n", encoding="utf-8")
