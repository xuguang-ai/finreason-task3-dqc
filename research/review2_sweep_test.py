#!/usr/bin/env python3
"""Test split (no gold, no upload): faithful partition and what the element-split variant
(9574 2026 + 10093 without the notes guard) adds.  Reads scratchpad/sweep2/raw_test.jsonl, built by
``review2_sweep.py --split test`` from in-memory hybrid queries (complete instance + released
linkbases).  Output: scratchpad/sweep2/test_split.json"""
import collections, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import review2_sweep_common as C
from review2_sweep_analyze import (load_raw, faithful_answers, classify, cands17, answers, N, faithful_keys, lk,
                                   draw_stats, R17)
T = C.test_index()
RT = load_raw("test")
qs = collections.defaultdict(set)
for cid, e in T.items():
    fr = RT[e["filing"]]
    qk = fr["qk"][cid]
    qs[e["filing"]].add(lk(qk["c17"], qk["p"]))
part = collections.Counter()
none = {}
changed = []
rebuilt = sum(1 for fr in RT.values() if fr.get("test_query_rebuilt"))
for cid, e in sorted(T.items()):
    fr = RT[e["filing"]]
    fa = faithful_answers(fr, cid, e)
    cls = classify(fa)
    part[cls] += 1
    qk = fr["qk"][cid]
    h = answers([(N(r["t"]), N(r["m"])) for r in cands17(fr, qk, "C", "split:9574=2026,10093=no_notes", "all")])
    b = answers([(N(r["t"]), N(r["m"])) for r in cands17(fr, qk, "C", "2026", "all")])
    if cls == "none":
        none[cid] = {"filing": e["filing"], "concept": e["concept"], "period": e["period"],
                     "faithful_10093": [list(map(str, a)) for a in b], "split_candidates": [list(map(str, a)) for a in h]}
    elif set(h) != set(b):
        changed.append(cid)
draw = draw_stats(RT, qs, R17, lambda fr: {lk(r["c"], r["p"]) for r in fr["f17c"]["split:9574=2026,10093=no_notes"]})
draw9574 = draw_stats(RT, qs, R17, lambda fr: {lk(r["c"], r["p"]) for r in fr["f17c"]["split:9574=no_notes,10093=2026"]})
pool = sum(len(set().union(*faithful_keys(fr).values())) for fr in RT.values())
drawn = sum(len(set().union(*faithful_keys(fr).values()) & qs[f]) for f, fr in RT.items())
out = {"filings": len(RT), "queries_rebuilt": rebuilt, "partition": dict(part), "none": none,
       "non_none_cases_changed_by_split": changed, "faithful_pool": [pool, drawn],
       "draw_split_10093_no_notes": draw, "draw_split_9574_no_notes": draw9574}
(C.SWEEP_OUT / "test_split.json").write_text(json.dumps(out, indent=1))
print({k: v for k, v in out.items() if k != "none"})
for cid, v in none.items():
    print(cid, v)
