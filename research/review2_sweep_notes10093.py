#!/usr/bin/env python3
"""Which notes-cube facts block the 10093 findings of the unexplained dev cases (CLOSED module)?

For every 10093 finding that exists only without the notes guard in the five filings of
DEV3_000189/190/193/198/214/215, list the facts XULE l.219 [nonils @cube in $NOTES_CUBES
@$dim = s @Dim2 = *] would collect at the total's alignment, with the notes cubes (role,
hypercube, closed flag) that admit each fact and whether the same fact is also in the
statement role (bleed-through).  Output: scratchpad/sweep2/notes10093.json
"""
import json, sys
from dataclasses import replace
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import review2_sweep_common as C
D17 = C.D17
Dv = C.dev_index()
FILINGS = ["0001409171-titn-20251031", "0001423902-wes-20241231", "0001517302-apam-20260630",
           "0001974138-ncr-20251231", "0002051820-logan-20260331", "0000089089-sci-20251231"]
out = []
for filing in FILINGS:
    cid = sorted(c for c, e in Dv.items() if e["filing"] == filing)[0]
    e = Dv[cid]
    q = C.read_query(C.DEV_HYBRID, e)
    fl = D17.load_filing(q, e["fdir"])
    F, NN = D17.FAITHFUL, replace(D17.FAITHFUL, notes_guard=False, label="x")
    base = {(f["statement_role"], f["concept"], json.dumps(f["period"]), f["total"], f["member_sum"]) for f in D17._all_findings(fl, F, None)}
    for rv in D17.statement_roles(fl):
        for dim in rv.dims:
            if D17.local(dim) not in D17._TARGET_SET:
                continue
            for fd in D17._rule_10093(fl, rv, dim, NN, None):
                key = (fd["statement_role"], fd["concept"], json.dumps(fd["period"]), fd["total"], fd["member_sum"])
                if key in base:
                    continue
                per = fd["period"]
                A = None
                # rebuild the alignment and collect the blocking notes facts
                dim2 = fd["dim2"]
                s = fd["sub_member"]
                notes = D17._notes_pairs(fl, dim, dim2, NN)
                tot = [t for t in D17._role_facts(fl, rv, NN) if t.concept == fd["concept"] and t.dims == ((dim, s),)
                       and list(t.period) == [per["start"], per["end"], per["instant"]]]
                rows = []
                for t in tot:
                    for f in notes.get((s, t.a4), []):
                        cubes = [(c.role.rsplit("/", 1)[-1], D17.local(c.hypercube), c.closed) for c in fl.cubes
                                 if c.is_notes and fl.in_cube(f, c, NN)]
                        in_stmt = f in D17._role_facts(fl, rv, NN)
                        rows.append({"value": D17.fmt(f.value), "dims": [[D17.local(a), D17.local(b)] for a, b in f.dims],
                                     "notes_cubes": cubes[:6], "n_notes_cubes": len(cubes), "also_in_statement_role": in_stmt})
                out.append({"filing": filing, "role": rv.role.rsplit("/", 1)[-1], "concept": fd["concept"], "period": per,
                            "total": fd["total"], "member_sum": fd["member_sum"], "dim": D17.local(dim),
                            "sub_member": D17.local(s), "dim2": D17.local(dim2),
                            "is_dev_question": any(Dv[c]["concept"].split(":")[-1] == fd["concept"].split(":")[-1]
                                                   and Dv[c]["period"] == [per["start"], per["end"], per["instant"]]
                                                   for c in Dv if Dv[c]["filing"] == filing),
                            "blocking_notes_facts": rows})
(C.SWEEP_OUT / "notes10093.json").write_text(json.dumps(out, indent=1))
for r in out:
    print(r["filing"][11:], r["concept"].split(":")[1], r["period"]["start"], r["period"]["end"], r["period"]["instant"], r["sub_member"], "dim2", r["dim2"],
          r["total"], r["member_sum"], "Q" if r["is_dev_question"] else "-")
    for b in r["blocking_notes_facts"][:4]:
        print("      notes fact", b["value"], b["dims"], "cubes", b["n_notes_cubes"], b["notes_cubes"][:2], "in stmt role" if b["also_in_statement_role"] else "")
