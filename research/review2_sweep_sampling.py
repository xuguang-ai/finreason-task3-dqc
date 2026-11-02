#!/usr/bin/env python3
"""Sampling-rate check for the ranked dev generator (reads scratchpad/sweep2/raw_dev.jsonl).

For each dev filing, the pool of question keys (concept, period) a hypothesis generator could
draw from, and how many of them are dev questions.  If a variant's extra keys belonged to the
generator's pool, they would be drawn at about the rate of the faithful keys of the same filings.
"""
import collections, json, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import review2_sweep_common as C
from review2_sweep_analyze import load_raw, flagged15

Dv = C.dev_index()
RD = load_raw("dev")
qs = collections.defaultdict(set)
for cid, e in Dv.items():
    fr = RD[e["filing"]]
    qk = fr["qk"][cid]
    qs[e["filing"]].add((qk["c17"].split(":")[-1], tuple(qk["p"])))

def k(c, p):
    return (c.split(":")[-1], tuple(p))

def pool_faithful(fr):
    s = {k(r["c"], r["p"]) for r in fr["f17c"]["2026"] if r["re"] == "9574"}
    s |= {k(r["c"], r["p"]) for r in fr["f26"] if r["fires"].get("faithful")}
    s |= {(r["key"][1], tuple(r["p"])) for r in fr["f15"] if flagged15(r, "v29")}
    return s

def keys17(fr, reading, v, elements):
    recs = fr["f17c" if reading == "C" else "f17o"][v]
    return {k(r["c"], r["p"]) for r in recs if r["re"] in elements}

out = {}
base = collections.Counter()
for f, fr in RD.items():
    P = pool_faithful(fr)
    base["keys"] += len(P)
    base["drawn"] += len(P & qs[f])
out["faithful_pool"] = dict(base)
for name, reading, v, el in [("10093 CLOSED 2026", "C", "2026", {"10093"}),
                             ("9574 CLOSED no_notes", "C", "no_notes", {"9574"}),
                             ("10093 CLOSED no_notes", "C", "no_notes", {"10093"}),
                             ("9574+10093 CLOSED no_notes", "C", "no_notes", {"9574", "10093"}),
                             ("9574+10093 CLOSED legacy", "C", "legacy", {"9574", "10093"}),
                             ("9574 OPEN 2026 (dim totals incl.)", "O", "2026", {"9574"}),
                             ("10093 OPEN literal", "O", "literal_10093", {"10093"})]:
    st = collections.Counter()
    hits = []
    for f, fr in RD.items():
        P = pool_faithful(fr)
        new = keys17(fr, reading, v, el) - P
        if reading == "C" and v != "2026":
            new -= keys17(fr, "C", "2026", {"9574", "10093"})
        st["filings_with_new_keys"] += bool(new)
        st["new_keys"] += len(new)
        d = new & qs[f]
        st["new_keys_that_are_dev_questions"] += len(d)
        if d:
            hits.append([f, sorted(map(str, d))])
    out[name] = {"stats": dict(st), "hits": hits}
json.dump(out, open(C.SWEEP_OUT / "sampling.json", "w"), indent=1)
for k2, v2 in out.items():
    print(k2, v2 if k2 == "faithful_pool" else v2["stats"], "" if k2 == "faithful_pool" else v2["hits"])
