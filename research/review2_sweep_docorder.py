#!/usr/bin/env python3
"""Document order of the candidate total facts of the multi-candidate focus cases (110, 189, 190, 214).

Output: scratchpad/sweep2/docorder.json.  Positions are character offsets of the fact in the
instance as parsed by claude_agent.task3_xbrl (the modules' ``pos``)."""
import json, sys
from dataclasses import replace
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import review2_sweep_common as C
D17, D15 = C.D17, C.D15
Dv = C.dev_index()
out = {}
for cid in ("DEV3_000189", "DEV3_000190", "DEV3_000214", "DEV3_000193", "DEV3_000198", "DEV3_000215", "DEV3_000162"):
    e = Dv[cid]
    q = C.read_query(C.DEV_HYBRID, e)
    fl = D17.load_filing(q, e["fdir"])
    want = D17._question_key(q, fl)
    NN = replace(D17.FAITHFUL, notes_guard=False, label="x")
    rows = []
    for f in D17._all_findings(fl, NN, want):
        tot = [t for t in fl.facts if t.concept == f["concept"] and [list(x) for x in t.dims] == f["total_dims"]
               and list(t.period) == [f["period"]["start"], f["period"]["end"], f["period"]["instant"]]]
        rows.append({"rule_element": f["rule_element"], "total": f["total"], "member_sum": f["member_sum"],
                     "total_dims": [[D17.local(a), D17.local(b)] for a, b in f["total_dims"]],
                     "role": f["statement_role"].rsplit("/", 1)[-1], "total_pos": min((t.pos for t in tot), default=None)})
    rows.sort(key=lambda r: (r["total_pos"] is None, r["total_pos"]))
    out[cid] = rows
e = Dv["DEV3_000110"]
q = C.read_query(C.DEV_HYBRID, e)
fs = D15.findings_0015(q, e["fdir"], order="document")
out["DEV3_000110"] = [{"extracted": f["extracted"], "pos": f["pos"], "dims": [[a.split(":")[-1], m.split(":")[-1]] for a, m in f["dims"]],
                       "in_released_linkbase": f["in_released_linkbase"], "tiebreak_rank": f["tiebreak_rank"]} for f in fs]
(C.SWEEP_OUT / "docorder.json").write_text(json.dumps(out, indent=1))
for cid, rows in out.items():
    print(cid)
    for r in rows:
        print("   ", r)
