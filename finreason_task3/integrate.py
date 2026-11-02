"""Run the three rule modules on one case and normalise their findings.

    findings = official_findings(query, filing_dir(query, data_dir / "filings"))
    -> [("DQC_US_0126", Decimal("-30014000"), Decimal("-51974000")), ...]

Every finding is reduced to the pair the task asks for: (extracted value,
calculated value).  Element 10093 of DQC_US_0117 is included (``all_alignments``),
so a case answered by a 10093 finding is not mistaken for a case with no finding.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import List, Optional, Tuple

from .dqc import dqc_0015, dqc_0117, dqc_0126

SREF = re.compile(r'schemaRef[^>]*href="[^"]*?([\w.-]+?-\d{8})(?:_htm)?\.xsd"')
CIK = re.compile(r'<(?:xbrli:)?identifier[^>]*scheme="http://www\.sec\.gov/CIK"[^>]*>(\d+)<')

Finding = Tuple[str, Decimal, Decimal]


def num(text) -> Optional[Decimal]:
    """Exact parse of a reported number; None for nil or non-numeric text."""
    if text is None:
        return None
    t = str(text).strip().replace(",", "").replace("−", "-")
    if t.startswith("(") and t.endswith(")"):
        t = "-" + t[1:-1].strip()
    if not t:
        return None
    try:
        d = Decimal(t)
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def filing_key(query: str) -> Optional[str]:
    """``<cik10>-<stem>`` of the filing a case names, from its schemaRef and context identifier."""
    m = SREF.search(query)
    k = CIK.search(query.split("##Instance document", 1)[-1])
    if not (m and k):
        return None
    return f"{k.group(1).zfill(10)}-{m.group(1)}"


def filing_dir(query: str, filings_root: Path) -> Optional[Path]:
    key = filing_key(query)
    if key is None:
        return None
    d = Path(filings_root) / key
    return d if d.is_dir() else None


def _pair_0015(f: dict) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    return num(f.get("extracted")), num(f.get("calculated"))


def _pair_0117(f: dict) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    return num(f.get("total")), num(f.get("member_sum"))


def _pair_0126(f: dict) -> Tuple[Optional[Decimal], Optional[Decimal]]:
    return num(f.get("parent_value")), num(f.get("children_sum"))


def official_findings(query: str, fdir: Optional[Path], options_0117=None) -> List[Finding]:
    """Distinct (rule, extracted, calculated) findings of the faithful logic for the question."""
    out: List[Finding] = []
    for f in dqc_0015.findings_0015(query, filing_dir=fdir):
        e, c = _pair_0015(f)
        if e is not None and c is not None:
            out.append(("DQC_US_0015", e, c))
    for f in dqc_0117.findings_0117(query, fdir, options_0117, all_alignments=True):
        e, c = _pair_0117(f)
        if e is not None and c is not None:
            out.append(("DQC_US_0117", e, c))
    for f in dqc_0126.findings_0126(query, filing_dir=fdir):
        e, c = _pair_0126(f)
        if e is not None and c is not None:
            out.append(("DQC_US_0126", e, c))
    seen, uniq = set(), []
    for r, e, c in out:
        if (r, e, c) not in seen:
            seen.add((r, e, c))
            uniq.append((r, e, c))
    return uniq
