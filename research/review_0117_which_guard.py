"""For 0117 practice cases the 2026 rule misses: which single guard removal recovers gold?"""
import sys
from dataclasses import replace
from pathlib import Path

ROOT = Path("/Users/xai/Desktop/FinReason")
sys.path.insert(0, str(ROOT / "claude-agent-sdk-benchmark"))
sys.path.insert(0, str(ROOT / "task3_source_data/dqc_rules"))
import validate_0117 as V  # noqa: E402
from claude_agent.dqc import dqc_0117 as D  # noqa: E402

base = D.FAITHFUL
variants = {
    "no_notes": replace(base, notes_guard=False),
    "no_paren": replace(base, parenthetical_guard=False),
    "no_rev": replace(base, revenue_exceptions=False),
    "no_period": replace(base, period_filter=False),
    "notes+paren": replace(base, notes_guard=False, parenthetical_guard=False),
    "notes+rev": replace(base, notes_guard=False, revenue_exceptions=False),
    "legacy": D.LEGACY,
    "legacy_noperiod": replace(D.LEGACY, period_filter=False),
}
for c in V.load_practice():
    if c["rule"] != "DQC_US_0117":
        continue
    gold = (c["ge"], c["gc"])
    def pairs(o):
        fs = D.findings_0117(c["query"], c["fdir"], o)
        return {(V.num(f["total"]), V.num(f["member_sum"])) for f in fs}
    p0 = pairs(base)
    if p0 == {gold}:
        continue
    rec = [k for k, o in variants.items() if gold in pairs(o)]
    print(c["id"], c["filing"], c["concept"].split(":")[1], c["period"], "gold", gold[0], gold[1],
          "| 2026:", sorted(map(str, p0)) or "-", "| recovered by:", rec)
