"""Đo hai cách chấm điểm truy hồi trên cùng một tập bản ghi và truy vấn.

Không gọi model, không mạng, không tốn tiền: chỉ là hai hàm chấm điểm chạy trên
dữ liệu cố định. Kết quả in ra Markdown để dán thẳng vào báo cáo.
"""

from __future__ import annotations

import math
import re
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from framework.bench.memory_rank.dataset import (  # noqa: E402
    QUERIES, QUERIES_RARE, RECORDS, RECORDS_RARE)


def tokens(text: str) -> list[str]:
    return re.findall(r"\w+", text.lower())


# ── cách chấm hiện tại: đếm từ trùng ────────────────────────────────
def score_overlap(query: str, record: str) -> float:
    """Bản sao của `aisef.memory._recall`: `len(overlap) * 10` (bỏ phần trust,
    vì mọi bản ghi ở đây cùng một mức tin cậy)."""
    return len(set(tokens(query)) & set(tokens(record))) * 10.0


# ── ứng viên: BM25 ──────────────────────────────────────────────────
def bm25_scorer(corpus: list[str], *, k1: float = 1.5, b: float = 0.75):
    docs = [tokens(d) for d in corpus]
    n = len(docs)
    avgdl = sum(len(d) for d in docs) / n if n else 0.0
    df: Counter[str] = Counter()
    for d in docs:
        df.update(set(d))

    def score(query: str, record: str) -> float:
        q = tokens(query)
        d = tokens(record)
        if not d:
            return 0.0
        tf = Counter(d)
        dl = len(d)
        total = 0.0
        for term in q:
            if term not in tf:
                continue
            # IDF kiểu BM25+ (không âm): một từ có mặt ở mọi bản ghi đóng góp ~0,
            # một từ hiếm đóng góp nhiều — đây là điều đếm từ trùng không làm.
            idf = math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
            freq = tf[term]
            total += idf * (freq * (k1 + 1)) / (freq + k1 * (1 - b + b * dl / avgdl))
        return total

    return score


# ── ứng viên thứ ba: trùng từ **riêng biệt**, có trọng số IDF ────────
def idf_overlap_scorer(corpus: list[str]):
    """Mỗi từ của truy vấn tính **một lần**, nhân trọng số hiếm.

    Lấy điểm mạnh của cả hai: không thưởng tần suất (nên một bản ghi nhồi từ
    khoá không leo hạng — đây là mô hình đe doạ thật với bộ nhớ), nhưng vẫn
    biết "flock" hiếm hơn "tệp" (thứ mà đếm từ trùng mù hoàn toàn).
    """
    docs = [set(tokens(d)) for d in corpus]
    n = len(docs) or 1
    df: Counter[str] = Counter()
    for d in docs:
        df.update(d)

    def score(query: str, record: str) -> float:
        d = set(tokens(record))
        total = 0.0
        for term in set(tokens(query)):
            if term in d:
                total += math.log(1 + (n - df[term] + 0.5) / (df[term] + 0.5))
        return total

    return score


def rank(scorer, query: str, records: list[str]) -> list[int]:
    scored = [(scorer(query, r), i) for i, r in enumerate(records)]
    return [i for _, i in sorted(scored, key=lambda v: (-v[0], v[1]))]


def evaluate(scorer, *, k: int, queries=None, records=None) -> dict:
    queries = QUERIES if queries is None else queries
    records = RECORDS if records is None else records
    dung_k = 0
    nghich_dao = 0.0
    for q in queries:
        thu_tu = rank(scorer, q["query"], records)
        vi_tri = thu_tu.index(q["answer"])
        if vi_tri < k:
            dung_k += 1
        nghich_dao += 1.0 / (vi_tri + 1)
    return {
        "precision@k": dung_k / len(queries),
        "mrr": nghich_dao / len(queries),
        "dung": dung_k,
        "tong": len(queries),
    }


def _bang(ten_bo: str, records, queries, k: int) -> None:
    cach = [
        ("đếm từ trùng (hiện tại)", score_overlap),
        ("BM25", bm25_scorer(records)),
        ("trùng từ riêng biệt × IDF", idf_overlap_scorer(records)),
    ]
    print(f"## {ten_bo} — {len(records)} bản ghi, {len(queries)} truy vấn\n")
    print("| cách chấm | đúng trong top-%d | precision@%d | MRR |" % (k, k))
    print("|---|---|---|---|")
    for ten, sc in cach:
        kq = evaluate(sc, k=k, queries=queries, records=records)
        print(f"| {ten} | {kq['dung']}/{kq['tong']} | {kq['precision@k']:.2f} | {kq['mrr']:.3f} |")
    print()
    for q in queries:
        hang = [rank(sc, q["query"], records).index(q["answer"]) + 1 for _, sc in cach]
        if len(set(hang)) > 1:
            print(f"- `{q['query']}` — " + " · ".join(
                f"{ten}: hạng {h}" for (ten, _), h in zip(cach, hang, strict=True)))
    print()


def main() -> int:
    print("# Xếp hạng truy hồi bộ nhớ\n")
    print("Bản ghi đúng phải lọt vào top 3 — ngân sách thật chỉ chứa được vài dòng.\n")
    _bang("Họ A — mồi nhiễu nhồi từ khoá", RECORDS, QUERIES, 3)
    _bang("Họ B — mồi nhiễu dài, đa dạng; bản ghi đúng chỉ chia sẻ một từ hiếm",
          RECORDS_RARE, QUERIES_RARE, 3)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
