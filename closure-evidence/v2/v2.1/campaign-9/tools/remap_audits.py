"""remap_audits.py ROOT AUDITS_JSON OUT_JSON [--candidates sha,sha,...]: carry the positional survivor audits
(docs/v2.1/MUTATION-RUNNER-V2.md section 16; AUDITS_JSON is {"entries": [{target, index, mutant, source_sha256, ...}]})
to the module text of the tree at ROOT, by validation — the same description without its line number, the same
occurrence, the same changed line. ROOT is the tree whose module text is the new one; the runner
(ROOT/validation/v2/mutation.py) is imported read-only for `mutants`, `_enum_members`, `source_digest`, `V21_TARGETS`,
`V21_RETIRED`, and never run.

The rule, exactly: for each entry E whose source_sha256 != the digest of the module file at ROOT (the runner's
`source_digest`, CRLF-normalized sha256): (1) find the OLD module text: the blob of that path at one of the candidate
commits (`git show <sha>:<path>`) whose digest == E.source_sha256; if none, E is 'unmapped: old text not found'.
(2) enumerate the old mutant list for E.target on the old text and check old[E.index].description == E.mutant (else
'unmapped: entry does not match its own text' — a problem). (3) description without the line number = E.mutant with the
leading 'L<digits> ' removed (after the child-script name for SCRIPT/inner targets); the OCCURRENCE k = the ordinal of
E.index among old mutants with the same line-less description. (4) enumerate the new mutant list on the new text;
candidates = new mutants with the same line-less description; take the k-th (none: 'unmapped: occurrence k not in new
text'); require that the changed line's text is the same in old and new (the source line at the old mutant's line number
in the old text, stripped, equals the source line at the new mutant's line number in the new text, stripped — for a
SCRIPT/inner target the lines of the child script's constant); else 'unmapped: changed line differs' (the audit must
be re-derived by a human). (5) carried entry = E with index/mutant/source_sha256 of the new mutant, plus
remapped_from = {index, mutant, source_sha256} of E (if E already has remapped_from, the earliest origin is kept as
'origin' and the hops are recorded in 'chain'). Entries whose digest already equals the new file's are kept unchanged.
Entries of targets no longer in V21_TARGETS (V21_RETIRED) are listed as 'retired'. OUT_JSON (mode 'x', never
overwritten) = {record, rule, tree, in, mapped, unchanged, unmapped: [{target, index, mutant, why}], retired,
entries: [carried + unchanged]}; len(entries) == in - unmapped - retired, each (target, index) at most once."""
import argparse
import ast
import collections
import importlib.util
import json
import pathlib
import re
import subprocess
import sys

CANDIDATES = "289885e,a770fbb,853da4a,5df323a,c4c1720,f860e57,b5c2457"


def runner(root):
    spec = importlib.util.spec_from_file_location("mutation", root / "validation/v2/mutation.py")
    m = importlib.util.module_from_spec(spec)
    sys.modules["mutation"] = m
    spec.loader.exec_module(m)
    return m


def git(root, *args):
    return subprocess.run(["git", "-C", str(root), *args], capture_output=True)


def split(func, desc):
    """(line number, description without it) of a mutant description; SCRIPT/inner descriptions start with the script name."""
    prefix = func.partition("/")[0] + " " if "/" in func else ""
    mt = re.match(re.escape(prefix) + r"L(\d+) (.*)", desc, re.S)
    if not mt:
        raise SystemExit(f"{func}: description without a line number: {desc!r}")
    return int(mt.group(1)), prefix + mt.group(2)


def lines(m, src, func):
    """The text the mutant list was enumerated over: the module, or the child script's constant for SCRIPT/inner."""
    script, _, inner = func.partition("/")
    return (m._script(ast.parse(src), script).value if inner else src).splitlines()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root"), ap.add_argument("audits"), ap.add_argument("out"), ap.add_argument("--candidates", default=CANDIDATES)
    a = ap.parse_args()
    root = pathlib.Path(a.root).resolve()
    fh = open(a.out, "x", encoding="utf-8")  # refuse to overwrite, before any work
    m = runner(root)
    doc = json.loads(pathlib.Path(a.audits).read_text(encoding="utf-8"))
    cands = [c for c in a.candidates.split(",") if c]
    texts, lists = {}, {}

    def old_of(rel, digest):  # (sha, text) of the candidate blob with this digest, or None
        if (rel, digest) not in texts:
            texts[(rel, digest)] = None
            for sha in cands:
                p = git(root, "show", f"{sha}:{rel}")
                if p.returncode == 0 and m.source_digest(p.stdout.decode("utf-8")) == digest:
                    texts[(rel, digest)] = (sha, p.stdout.decode("utf-8"))
                    break
        return texts[(rel, digest)]

    def descs(src, target):  # the mutant descriptions of `target` enumerated on `src`, in the runner's order
        rel, func = target.split("::")
        key = (m.source_digest(src), target)
        if key not in lists:
            lists[key] = [d for d, _ in m.mutants(src, func, m._enum_members(src, root))]
        return lists[key]

    rev = {k: git(root, "rev-parse", v).stdout.decode().strip() for k, v in (("head", "HEAD"), ("aisef2", "HEAD:aisef2"))}
    out = {"record": doc["record"], "rule": doc["rule"], "tree": rev, "in": len(doc["entries"]), "mapped": 0,
           "unchanged": 0, "unmapped": [], "retired": [], "entries": []}
    for e in doc["entries"]:
        target, pos = e["target"], {k: e[k] for k in ("target", "index", "mutant")}
        rel, func = target.split("::")
        if target not in m.V21_TARGETS:
            out["retired"].append(dict(pos, why="V21_RETIRED" if target in m.V21_RETIRED else "not in V21_TARGETS"))
            continue
        new_src = (root / rel).read_text(encoding="utf-8")
        new_digest = m.source_digest(new_src)
        if e["source_sha256"] == new_digest:
            out["unchanged"] += 1
            out["entries"].append(e)
            continue
        found = old_of(rel, e["source_sha256"])
        if found is None:
            out["unmapped"].append(dict(pos, why="unmapped: old text not found"))
            continue
        old = descs(found[1], target)
        if e["index"] >= len(old) or old[e["index"]] != e["mutant"]:
            out["unmapped"].append(dict(pos, why="unmapped: entry does not match its own text"))
            continue
        line, key = split(func, e["mutant"])
        k = [i for i, d in enumerate(old) if split(func, d)[1] == key].index(e["index"])
        new = descs(new_src, target)
        news = [i for i, d in enumerate(new) if split(func, d)[1] == key]
        if k >= len(news):
            out["unmapped"].append(dict(pos, why=f"unmapped: occurrence {k} not in new text ({len(news)} there)"))
            continue
        ni = news[k]
        nline = split(func, new[ni])[0]
        if lines(m, found[1], func)[line - 1].strip() != lines(m, new_src, func)[nline - 1].strip():
            out["unmapped"].append(dict(pos, why="unmapped: changed line differs"))
            continue
        hop = {"index": e["index"], "mutant": e["mutant"], "source_sha256": e["source_sha256"]}
        rf, prev = dict(hop), e.get("remapped_from")
        if prev:
            chain = prev.get("chain") or [{k2: v for k2, v in prev.items() if k2 not in ("origin", "chain")}]
            rf["origin"], rf["chain"] = chain[0], chain + [hop]
        out["entries"].append(dict(e, index=ni, mutant=new[ni], source_sha256=new_digest, remapped_from=rf))
        out["mapped"] += 1
    seen = [(x["target"], x["index"]) for x in out["entries"]]
    if len(seen) != len(set(seen)):
        raise SystemExit(f"a (target, index) twice: {[s for s, n in collections.Counter(seen).items() if n > 1]}")
    assert len(out["entries"]) == out["in"] - len(out["unmapped"]) - len(out["retired"])
    json.dump(out, fh, indent=1, ensure_ascii=False)
    fh.write("\n")
    fh.close()
    why = collections.Counter(u["why"] for u in out["unmapped"])
    print(f"in {out['in']}: mapped {out['mapped']}, unchanged {out['unchanged']}, unmapped {len(out['unmapped'])}"
          f"{' (' + ', '.join(f'{n} {w}' for w, n in sorted(why.items())) + ')' if why else ''}, retired {len(out['retired'])}; "
          f"entries {len(out['entries'])}; tree {rev['head'][:7]} aisef2 {rev['aisef2'][:7]}; candidates {','.join(cands)} -> {a.out}")
    for u in out["unmapped"] + out["retired"]:
        print(f"  {u['target']} [{u['index']}] {u['mutant']!r}: {u['why']}")


if __name__ == "__main__":
    main()
