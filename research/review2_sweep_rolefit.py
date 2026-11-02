#!/usr/bin/env python3
"""Does the shipped (statement-scoped) linkbase fit the finding's rule-focus fact?

fit = the fact's concept is a locator of the shipped presentation section and every axis and
member of the fact is a locator of the shipped definition section (the R2 test of
dqc_build_variant2.py).  Measured on the faithful single-answer dev cases per rule, then applied
to every candidate of the unexplained cases.  Output: scratchpad/sweep2/rolefit.json"""
import collections, json, re, sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import review2_sweep_common as C
from review2_sweep_analyze import load_raw, faithful_answers, classify, cands15, cands17, cands26, R15, R17, R26, N
X = C.X
Dv = C.dev_index(); RD = load_raw("dev")

def shipped_names(q):
    sec = X.split_sections(q)
    nm = lambda t: {h.split("_", 1)[-1] for h in re.findall(r'xlink:href="[^"]*#([^"]+)"', t or "")}
    return nm(sec.get("presentation")), nm(sec.get("definition"))

def fit(concept, dims, pres, dfn):
    if concept.split(":")[-1] not in pres:
        return False
    return all(x.split(":")[-1] in dfn for a, m in dims for x in (a, m))

st = collections.Counter()
focus = {}
for cid, e in sorted(Dv.items()):
    fr = RD[e["filing"]]
    fa = faithful_answers(fr, cid, e)
    cls = classify(fa)
    if cls not in ("single", "none"):
        continue
    q = C.read_query(C.DEV_HYBRID, e)
    pres, dfn = shipped_names(q)
    qk = fr["qk"][cid]
    if cls == "single":
        rule = next(r for r, a in fa.items() if a)
        if rule == R15:
            ok = any(fit(r["c"], r["dims"], pres, dfn) for r in cands15(fr, qk, "v29"))
        elif rule == R17:
            ok = any(fit(r["c"], r["td"], pres, dfn) for r in cands17(fr, qk, "C", "2026"))
        else:
            ok = any(fit(r["c"], [], pres, dfn) for r in cands26(fr, e["concept"], qk, "faithful"))
        st[(rule[-4:], ok)] += 1
    else:
        rows = []
        for r in cands17(fr, qk, "C", "split:9574=2026,10093=no_notes", "all"):
            rows.append({"rule": "0117/" + r["re"], "extracted": r["t"], "calculated": r["m"], "total_dims": r["td"],
                         "role_shipped": r["role"] in set(e["shipped_roles"]), "total_fits_shipped_linkbase": fit(r["c"], r["td"], pres, dfn)})
        for r in [x for x in fr["f15"] if x["key"] == qk["k15"] and x["p"] == qk["p15"]]:
            rows.append({"rule": "0015-fact(not flagged)", "extracted": r["e"], "calculated": r["calc"], "dims": r["dims"],
                         "reasons": r["reasons"], "listed": r["listed"], "fits_shipped_linkbase": fit(r["c"], r["dims"], pres, dfn)})
        focus[cid] = rows
out = {"faithful_single_fit": {f"{k[0]}:{'fit' if k[1] else 'no-fit'}": v for k, v in sorted(st.items())}, "unexplained": focus}
(C.SWEEP_OUT / "rolefit.json").write_text(json.dumps(out, indent=1))
print(out["faithful_single_fit"])
for cid, rows in focus.items():
    print(cid)
    for r in rows:
        print("   ", r)
