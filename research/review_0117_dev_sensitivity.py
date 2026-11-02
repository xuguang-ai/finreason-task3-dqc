"""Dev sensitivity: for each option variant, the distinct (total, sum) findings for the
questioned concept/period.  No gold is read (there is none)."""
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path("/Users/xai/Desktop/FinReason")
sys.path.insert(0, str(ROOT / "claude-agent-sdk-benchmark"))
from claude_agent.dqc import dqc_0117 as D  # noqa: E402

DEV = ROOT / "task3_source_data/ranked/development_inputs_hybrid_v0928.jsonl"
FIL = ROOT / "task3_source_data/ranked/raw_filings_ranked"
F = D.FAITHFUL
variants = {
    "faithful": F,
    "sub_off": replace(F, subtotal_guard="off"),
    "sub_strict": replace(F, subtotal_guard="strict"),
    "no_notes": replace(F, notes_guard=False),
    "no_paren": replace(F, parenthetical_guard=False),
    "no_rev": replace(F, revenue_exceptions=False),
    "no_validity": replace(F, member_validity=False),
    "no_period": replace(F, period_filter=False),
    "legacy": D.LEGACY,
}
out = {}
t0 = time.time()
with DEV.open() as fh:
    for line in fh:
        r = json.loads(line)
        fdir = D.locate_filing_dir(r["query"], [FIL])
        row = {"fdir": str(fdir) if fdir else None}
        for name, o in variants.items():
            fs = D.findings_0117(r["query"], fdir, o)
            pairs = []
            for f in fs:
                p = (f["total"], f["member_sum"], f["statement_role"].rsplit("/", 1)[-1], D.local(f["axis"]),
                     f["in_released_role"], f["exception"])
                pairs.append(p)
            row[name] = pairs
        out[r["id"]] = row
print("seconds", round(time.time() - t0, 1))
json.dump(out, open(Path(__file__).with_suffix(".json"), "w"), indent=0)
