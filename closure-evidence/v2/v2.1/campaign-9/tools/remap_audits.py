"""remap_audits.py ROOT AUDITS_JSON OUT_JSON [--candidates sha,sha,...]: carry the positional survivor audits
(docs/v2.1/MUTATION-RUNNER-V2.md section 16; AUDITS_JSON is {"entries": [{target, index, mutant, source_sha256, ...}]})
to the module text of the tree at ROOT, by validation — the same description without its line number, the same
site set, the same occurrence, the same statement. ROOT is the tree whose module text is the new one; the runner
(ROOT/validation/v2/mutation.py) is imported read-only for `mutants`, `_enum_members`, `_script`, `source_digest`,
`V21_TARGETS`, `V21_RETIRED`, and never run. ROOT's aisef2/ and the runner must be clean (`git status --porcelain`
empty, else exit 2) so that tree.head describes the text used.

The rule, exactly: for each entry E whose source_sha256 != the digest of the module file at ROOT (the runner's
`source_digest`, CRLF-normalized sha256): (1) find the OLD module text: the blob of that path at one of the candidate
commits (`git show <sha>:<path>`) whose digest == E.source_sha256; if none, E is 'unmapped: old text not found'.
(2) enumerate the old mutant list for E.target on the old text and check old[E.index].description == E.mutant (else
'unmapped: entry does not match its own text' — a problem). (3) description without the line number = E.mutant with the
leading 'L<digits> ' removed (after the child-script name for SCRIPT/inner targets); the SITES of a text = its mutants
with that line-less description, in the runner's order; the OCCURRENCE k = the ordinal of E.index among the old sites.
(4) enumerate the new mutant list on the new text; if the old and the new text do not have the same NUMBER of sites, E
is 'unmapped: site set changed (old n, new m)' even when the k-th new site's statement matches — stricter than the
rule campaigns 4/5/6 applied (the k-th site whenever it existed), never looser: a changed site set is re-derived by a
human. (5) the candidate is the k-th new site; require the same STATEMENT: the smallest ast statement of the text (the
module, or the child script's constant parsed as its own module for SCRIPT/inner) whose lineno <= L <= end_lineno, L
the mutant's line number; its lines lineno..end_lineno, stripped, must be equal old vs new, AND the mutant's offset
inside the statement (L - lineno) must be the same (so a multi-line statement whose continuation line changed is
caught, and two equal-text sites inside one statement are not interchangeable; the earlier rounds compared the one
line L); else 'unmapped: statement differs' with 'identical_statement_at_other_sites' = the new site indices whose statement equals the old one (an
ordinal shift the operator can see; never mapped to). (6) carried entry = E with index/mutant/source_sha256 of the new
mutant, plus remapped_from = {index, mutant, source_sha256, base} of E, base the full commit the old text was found
at (if E already has remapped_from, the earliest origin is kept as 'origin' and the hops are recorded in 'chain'; the
hops of the earlier rounds are {index, mutant, base}). Entries whose digest already equals the new file's are kept
unchanged. Entries of targets no longer in V21_TARGETS (V21_RETIRED) are listed as 'retired'. `_enum_members` is
evaluated against ROOT's tree for the old text too (the Enum classes a module imports are read from ROOT/aisef2):
acceptable while no imported Enum changed — all 35 Enum classes were measured identical across the 7 candidates and
HEAD. OUT_JSON = {record, rule, tree, in, mapped, unchanged, unmapped: [{target, index, mutant, why, ...}], retired,
entries: [carried + unchanged]}; in == mapped + unchanged + unmapped + retired, each (target, index) at most once; it
is computed in full and checked first, then written whole to OUT.part beside OUT and hard-linked to OUT (never
overwritten: the link fails if OUT exists; a partial file never bears OUT's name)."""
import argparse
import ast
import collections
import importlib.util
import json
import os
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


def text_of(m, src, func):
    """The text the mutant list was enumerated over: the module, or the child script's constant for SCRIPT/inner."""
    script, _, inner = func.partition("/")
    return m._script(ast.parse(src), script).value if inner else src


def statement(text, line):
    """(offset of `line` inside, stripped lines of) the smallest statement of `text` (parsed as a module) spanning
    `line`; the line alone if none. The offset pins WHERE in the statement the mutant sits: two sites of one
    multi-line statement with equal text would otherwise be interchangeable (the second review's latent gap)."""
    spans = [(n.end_lineno - n.lineno, n.lineno, n.end_lineno) for n in ast.walk(ast.parse(text))
             if isinstance(n, ast.stmt) and n.lineno <= line <= n.end_lineno]
    _, lo, hi = min(spans) if spans else (0, line, line)
    return line - lo, [s.strip() for s in text.splitlines()[lo - 1:hi]]


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("root"), ap.add_argument("audits"), ap.add_argument("out"), ap.add_argument("--candidates", default=CANDIDATES)
    a = ap.parse_args()
    root = pathlib.Path(a.root).resolve()
    if pathlib.Path(a.out).exists():
        raise SystemExit(f"{a.out} exists: never overwritten")
    dirty = git(root, "status", "--porcelain", "--", "aisef2", "validation/v2/mutation.py").stdout.decode()
    if dirty:
        print(f"{root}: aisef2/ or the runner is dirty; tree.head would not describe the text used:\n{dirty}", file=sys.stderr)
        sys.exit(2)
    m = runner(root)
    doc = json.loads(pathlib.Path(a.audits).read_text(encoding="utf-8"))
    cands = []
    for c in filter(None, a.candidates.split(",")):
        p = git(root, "rev-parse", "--verify", c + "^{commit}")
        if p.returncode:
            raise SystemExit(f"candidate {c}: {p.stderr.decode().strip()}")
        cands.append(p.stdout.decode().strip())
    texts, lists = {}, {}

    def old_of(rel, digest):  # (full sha, text) of the candidate blob with this digest, or None
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
        olds = [i for i, d in enumerate(old) if split(func, d)[1] == key]
        new = descs(new_src, target)
        news = [i for i, d in enumerate(new) if split(func, d)[1] == key]
        if len(olds) != len(news):
            out["unmapped"].append(dict(pos, why=f"unmapped: site set changed (old {len(olds)}, new {len(news)})"))
            continue
        ni = news[olds.index(e["index"])]
        new_text, stmt = text_of(m, new_src, func), statement(text_of(m, found[1], func), line)
        if statement(new_text, split(func, new[ni])[0]) != stmt:
            same = [i for i in news if statement(new_text, split(func, new[i])[0]) == stmt]
            out["unmapped"].append(dict(pos, why="unmapped: statement differs", identical_statement_at_other_sites=same))
            continue
        hop = {"index": e["index"], "mutant": e["mutant"], "source_sha256": e["source_sha256"], "base": found[0]}
        rf, prev = dict(hop), e.get("remapped_from")
        if prev:
            chain = prev.get("chain") or [{k2: v for k2, v in prev.items() if k2 not in ("origin", "chain")}]
            rf["origin"], rf["chain"] = chain[0], chain + [hop]
        out["entries"].append(dict(e, index=ni, mutant=new[ni], source_sha256=new_digest, remapped_from=rf))
        out["mapped"] += 1
    seen = [(x["target"], x["index"]) for x in out["entries"]]
    if len(seen) != len(set(seen)):
        raise SystemExit(f"a (target, index) twice: {[s for s, n in collections.Counter(seen).items() if n > 1]}")
    assert out["in"] == out["mapped"] + out["unchanged"] + len(out["unmapped"]) + len(out["retired"])
    assert len(out["entries"]) == out["mapped"] + out["unchanged"]
    body = json.dumps(out, indent=1, ensure_ascii=False) + "\n"  # everything computed and checked before OUT exists
    dst = pathlib.Path(a.out)
    part = dst.with_name(dst.name + ".part")  # written whole beside OUT, then linked: a partial file never bears OUT's name
    part.write_text(body, encoding="utf-8")
    try:
        os.link(part, dst)  # fails if OUT appeared meanwhile: never overwritten
    finally:
        part.unlink()
    why = collections.Counter(u["why"] for u in out["unmapped"])
    print(f"in {out['in']}: mapped {out['mapped']}, unchanged {out['unchanged']}, unmapped {len(out['unmapped'])}"
          f"{' (' + ', '.join(f'{n} {w}' for w, n in sorted(why.items())) + ')' if why else ''}, retired {len(out['retired'])}; "
          f"entries {len(out['entries'])}; tree {rev['head'][:7]} aisef2 {rev['aisef2'][:7]}; candidates {','.join(c[:7] for c in cands)} -> {a.out}")
    for u in out["unmapped"] + out["retired"]:
        same = u.get("identical_statement_at_other_sites")
        print(f"  {u['target']} [{u['index']}] {u['mutant']!r}: {u['why']}" + (f"; identical statement at new {same}" if same else ""))


if __name__ == "__main__":
    main()
