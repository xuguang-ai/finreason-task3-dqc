"""Probe: does the gold agree with per-total guards (H1, module) or with
'first aligned factset drives iteration' (H2 lazy / H3 eager declaration order)?

For every finding the module produces (dimension-free totals, all concepts and
periods, era=auto options), classify:
  case1 = role holds multi-dimension facts carrying the axis (SubTotalExists aligned)
  notes_any / paren_any = some notes / parenthetical fact carries the axis anywhere
  notes_al / paren_al = such a fact is aligned with this total
H2 (lazy, condition order SubTotal -> notes -> paren) blocks a finding when
  not case1 and ((notes_any and not notes_al) or (not notes_any and paren_any and not paren_al)).
H3 (eager, declaration order paren(l.65) -> notes(l.71)) blocks when
  not case1 and ((paren_any and not paren_al) or (not paren_any and notes_any and not notes_al)).
(Aligned notes/paren facts are already handled by the module's guards.)
"""
import collections
import json
import sys
from pathlib import Path

ROOT = Path("/Users/xai/Desktop/FinReason")
sys.path.insert(0, str(ROOT / "claude-agent-sdk-benchmark"))
sys.path.insert(0, str(ROOT / "task3_source_data/dqc_rules"))
import validate_0117 as V  # noqa: E402
from claude_agent.dqc import dqc_0117 as D  # noqa: E402

cases = V.load_practice()
by_filing = collections.defaultdict(list)
for c in cases:
    by_filing[c["filing"]].append(c)

out = []
for filing, cs in sorted(by_filing.items()):
    g17 = [c for c in cs if c["rule"] == "DQC_US_0117"]
    if not g17:
        continue
    opts = D.options_for(cs[0]["query"], "auto")
    fl = D.load_filing(cs[0]["query"], cs[0]["fdir"])
    gk = {(c["concept"], c["period"], c["ge"], c["gc"]) for c in g17}
    for rv in D.statement_roles(fl):
        for dim in rv.dims:
            if D.local(dim) not in D._TARGET_SET:
                continue
            facts = D._role_facts(fl, rv, opts)
            multi = [f for f in facts if not f.nil and f.monetary and f.dim(dim) is not None and len(f.dims) > 1]
            paren, notes = D._other_cube_facts(fl, dim, D.Options())  # always collect, regardless of era
            for fd in D._rule_9574(fl, rv, dim, opts, None):
                if fd["total_dims"]:
                    continue
                per = (fd["period"]["start"], fd["period"]["end"], fd["period"]["instant"])
                key = (fd["concept"], per, V.num(fd["total"]), V.num(fd["member_sum"]))
                # alignment of the total without dim
                A = (fd["concept"], per)
                notes_al = any(k[0] == fd["concept"] and k[1] == per and (len(k) < 5 or not k[4]) for k in notes)  # keys are (concept, period, unit, entity) since the closed-factset rewrite
                paren_al = any(k[0] == fd["concept"] and k[1] == per and (len(k) < 5 or not k[4]) for k in paren)
                case1 = bool(multi)
                notes_any, paren_any = bool(notes), bool(paren)
                h2 = (not case1) and ((notes_any and not notes_al) or (not notes_any and paren_any and not paren_al))
                h3 = (not case1) and ((paren_any and not paren_al) or (not paren_any and notes_any and not notes_al))
                out.append({
                    "filing": filing, "year": cs[0]["year"], "role": rv.role.rsplit("/", 1)[-1], "dim": D.local(dim),
                    "concept": fd["concept"], "period": per, "total": fd["total"], "sum": fd["member_sum"],
                    "is_gold": key in gk, "case1": case1, "notes_any": notes_any, "notes_al": notes_al,
                    "paren_any": paren_any, "paren_al": paren_al, "H2_blocks": h2, "H3_blocks": h3,
                })

cnt = collections.Counter()
for r in out:
    era = "<=2022" if (r["year"] or 9999) <= 2022 else ">=2023"
    cnt[(era, "gold" if r["is_gold"] else "extra", "H2blocks" if r["H2_blocks"] else "-", "H3blocks" if r["H3_blocks"] else "-")] += 1
for k, v in sorted(cnt.items()):
    print(k, v)
print()
for r in out:
    if r["is_gold"] and (r["H2_blocks"] or r["H3_blocks"]):
        print("GOLD BLOCKED:", r)
json.dump(out, open(Path(__file__).with_suffix(".json"), "w"), indent=1, default=str)
