#!/usr/bin/env python3
"""Regenerate claude_agent/dqc/dqc_0015_items.json from the published DQC_0015 element list.

Why a generated file: the 2026 rule builds ``$NON_NEG_ITEMS`` from four CSVs fetched
at run time from GitHub (``dqc_15_usgaap_2026_concepts.csv``, ``..._srt_...``,
``..._dei_...``, ``..._ebp_...``; lib_2026_resources.xule lines 31-34). Those CSVs
are not in the local material. The published spreadsheet
``DQC_US_0015__DQC_0015_ListOfElements.xlsx`` is the human-maintained master of the
same list (rule element id, element, add release, removal release, status), so it
is the faithful local source. Keeping every row with its add/remove versions lets
the rule module rebuild the list as it stood at any DQC release.

Columns used (sheet "DQC_0015 NonNeg", header on row 2):
  C  originalReleaseVersion  -> version in which the element was added
  E  effectiveDate           -> kept for reference only (see dqc_0015 docstring)
  F  ruleElementID           -> the rule suffix, DQC.US.0015.<id>
  H  RuleStatus 1/0          -> 1 = active in the current list
  I  removalRelease          -> version in which the element was removed
  O  (headed "Deprecated")   -> the QUALIFIED element name, e.g. ``srt:LifeInsuranceInForceNet``;
                                 an unprefixed name means us-gaap. Column J ("namespace")
                                 was rewritten to ``srt`` for 46 us-gaap elements that
                                 moved to SRT in 2018, so J is not used for the namespace.
  P / Q                      -> taxonomy year added / deprecated

Usage::

    python3 build_0015_items.py            # writes the JSON next to dqc_0015.py
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
XLSX = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / "dqc_sources" / "DQC_0015_ListOfElements.xlsx"
OUT = Path(__file__).resolve().parent.parent / "finreason_task3" / "dqc" / "dqc_0015_items.json"


def _date(v):
    if isinstance(v, _dt.datetime):
        return v.date().isoformat()
    return None if v in (None, "") else str(v)


def main() -> int:
    wb = openpyxl.load_workbook(XLSX, read_only=True, data_only=True)
    ws = wb["DQC_0015 NonNeg"]
    rows = list(ws.iter_rows(values_only=True))
    header = rows[1]
    assert header[2] == "originalReleaseVersion" and header[5] == "ruleElementID", header
    assert header[7].startswith("RuleStatus") and header[8] == "removalRelease", header
    items: dict[str, list] = {}
    n_rows = n_active = 0
    for r in rows[2:]:
        if r[5] is None or r[10] is None:
            continue
        n_rows += 1
        qualified = (r[14] or r[10]).strip()
        prefix, local = (qualified.split(":", 1) if ":" in qualified else ("us-gaap", qualified))
        if local != r[10].strip():
            raise SystemExit(f"name mismatch on id {r[5]}: {qualified!r} vs {r[10]!r}")
        status = int(r[7])
        added = int(r[2])
        removed = None if r[8] in (None, "") else int(r[8])
        if status == 1 and removed is not None:
            raise SystemExit(f"active row {r[5]} carries a removal release")
        if status == 0 and removed is None:
            raise SystemExit(f"inactive row {r[5]} has no removal release")
        n_active += status
        items.setdefault(f"{prefix}:{local}", []).append(
            [int(r[5]), added, removed, _date(r[4]), r[0], r[15], r[16]]
        )
    payload = {
        "source": XLSX.name,
        "source_sha256": hashlib.sha256(XLSX.read_bytes()).hexdigest(),
        "columns": ["rule_element_id", "added_version", "removed_version", "effective_date",
                    "month_year_release", "taxonomy_year_added", "taxonomy_year_deprecated"],
        "n_rows": n_rows,
        "n_active_rows": n_active,
        "items": dict(sorted(items.items())),
    }
    OUT.write_text(json.dumps(payload, separators=(",", ":")) + "\n")
    print(f"wrote {OUT} : {n_rows} rows, {n_active} active, {len(items)} distinct qualified names")
    return 0


if __name__ == "__main__":
    sys.exit(main())
