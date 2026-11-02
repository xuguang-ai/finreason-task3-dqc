"""Shared loaders for the review2_sweep* harness (variant sweep of DQC 0117 / 0126 / 0015).

Read-only with respect to the rule modules: nothing under claude_agent/dqc/ is edited.  The
pre-fix 0117 module (OPEN factset reading) is loaded from the scratchpad snapshot under the
module name ``claude_agent.dqc.dqc_0117_open`` (in memory only).

Outputs go to SWEEP_OUT (scratchpad/sweep2/).
"""
from __future__ import annotations

import collections
import importlib.util
import json
import re
import sys
from pathlib import Path

ROOT = Path("/Users/xai/Desktop/FinReason")
SDK = ROOT / "claude-agent-sdk-benchmark"
RULES_DIR = ROOT / "task3_source_data/dqc_rules"
RANKED = ROOT / "task3_source_data/ranked"
SCRATCH = Path(__file__).resolve().parent / "scratch"   # working directory for the sweep outputs
SWEEP_OUT = SCRATCH / "sweep2"
OPEN_SNAPSHOT = SCRATCH / "before/dqc_0117.py"

for p in (str(SDK), str(RULES_DIR)):
    if p not in sys.path:
        sys.path.insert(0, p)

from claude_agent import task3_xbrl as X  # noqa: E402
from claude_agent.dqc import dqc_0015 as D15  # noqa: E402
from claude_agent.dqc import dqc_0117 as D17  # noqa: E402  (CLOSED reading, current)
from claude_agent.dqc import dqc_0126 as D26  # noqa: E402

DEV_HYBRID = RANKED / "development_inputs_hybrid_v0928.jsonl"
TEST_RELEASE = RANKED / "v20260928/test_inputs.jsonl"
DEV_RELEASE = RANKED / "v20260928/development_inputs.jsonl"
DEV_FILINGS = RANKED / "raw_filings_ranked"
PRACTICE_FILINGS = ROOT / "task3_source_data/raw_filings"
MANIFEST = RANKED / "edgar_manifest.json"
PRED_A = RANKED / "predictions_dev_dqc.jsonl"
PRED_B = RANKED / "predictions_dev_dqc2.jsonl"

FOCUS = ["DEV3_000110", "DEV3_000162", "DEV3_000189", "DEV3_000190", "DEV3_000193", "DEV3_000198",
         "DEV3_000214", "DEV3_000215"]
NONE_CASES = ["DEV3_000162", "DEV3_000189", "DEV3_000190", "DEV3_000193", "DEV3_000198", "DEV3_000214",
              "DEV3_000215"]

SREF = re.compile(r'schemaRef[^>]*href="[^"]*?([\w.-]+?-\d{8})(?:_htm)?\.xsd"')
CIK = re.compile(r'<(?:xbrli:)?identifier[^>]*scheme="http://www\.sec\.gov/CIK"[^>]*>\s*(\d+)\s*<')
PRES_ROLE = re.compile(r'<(?:[\w-]+:)?presentationLink\b[^>]*?xlink:role=["\']([^"\']+)["\']')
ANY_ROLE = re.compile(r'<(?:[\w-]+:)?(?:presentation|calculation|definition)Link\b[^>]*?xlink:role=["\']([^"\']+)["\']')


def load_open_module():
    """The pre-fix 0117 module (OPEN [...] factsets), as claude_agent.dqc.dqc_0117_open."""
    name = "claude_agent.dqc.dqc_0117_open"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, str(OPEN_SNAPSHOT))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def jl(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def filing_key(query: str):
    """(cik10, stem) from the instance's identifier and schemaRef."""
    inst = query.split("##Instance document", 1)[-1]
    m = SREF.search(inst) or SREF.search(query)
    k = CIK.search(inst)
    return (k.group(1).zfill(10) if k else None, m.group(1) if m else None)


def question(query: str):
    q = X.parse_question(query)
    return q.concept, tuple(q.period_key)


def shipped_roles(query: str):
    sec = X.split_sections(query)
    pres = set(PRES_ROLE.findall(sec.get("presentation", "") or ""))
    anyr = set()
    for k in ("presentation", "calculation", "definition"):
        anyr |= set(ANY_ROLE.findall(sec.get(k, "") or ""))
    return sorted(pres), sorted(anyr)


def build_ranked_index(path: Path, out: Path, split: str):
    """id -> {offset, length, concept, period, cik, stem, fdir, shipped roles} (cached JSON)."""
    if out.exists():
        return json.loads(out.read_text())
    idx = {}
    with open(path, "rb") as fh:
        while True:
            off = fh.tell()
            line = fh.readline()
            if not line:
                break
            if not line.strip():
                continue
            r = json.loads(line)
            q = r["query"]
            cik, stem = filing_key(q)
            concept, period = question(q)
            fdir = DEV_FILINGS / f"{cik}-{stem}" if cik and stem else None
            pres, anyr = shipped_roles(q)
            idx[r["id"]] = {"offset": off, "length": len(line), "concept": concept, "period": list(period),
                            "cik": cik, "stem": stem, "filing": f"{cik}-{stem}",
                            "fdir": str(fdir) if fdir and fdir.is_dir() else None,
                            "us_gaap_year": D17.us_gaap_year(q), "shipped_pres_roles": pres,
                            "shipped_roles": anyr, "split": split}
    out.write_text(json.dumps(idx))
    return idx


def read_query(path: Path, entry: dict) -> str:
    with open(path, "rb") as fh:
        fh.seek(entry["offset"])
        line = fh.read(entry["length"])
    return json.loads(line)["query"]


def dev_index():
    SWEEP_OUT.mkdir(parents=True, exist_ok=True)
    return build_ranked_index(DEV_HYBRID, SWEEP_OUT / "dev_index.json", "dev")


def test_index():
    SWEEP_OUT.mkdir(parents=True, exist_ok=True)
    return build_ranked_index(TEST_RELEASE, SWEEP_OUT / "test_index.json", "test")


def predictions(path: Path):
    from decimal import Decimal
    out = {}
    for r in jl(path):
        out[r["id"]] = (Decimal(str(r["extracted_value"]).replace(",", "")),
                        Decimal(str(r["calculated_value"]).replace(",", "")))
    return out


def by_filing(idx: dict):
    g = collections.defaultdict(list)
    for cid, e in idx.items():
        g[e["filing"]].append(cid)
    return g


# --------------------------------------------------------------------------- #
# Practice index (same case basis as validate_0117.load_practice, without holding
# every query in memory): curated 330 + the two original-only cases as extras.
# --------------------------------------------------------------------------- #

PRACTICE_COMPLETE = ROOT / "dsh/task3_inputs.jsonl"
PRACTICE_RELEASED = ROOT / "task3_source_data/finmr_public_dev/public_dev_inputs.jsonl"
PRACTICE_ORIGINAL = ROOT / "task3_source_data/finmr_public_dev/public_dev.jsonl"
PRACTICE_CURATED = ROOT / "task3_source_data/curated/public_dev_curated.jsonl"
PRACTICE_MAP = ROOT / "task3_source_data/finmr_to_filing_mapping.json"


def _offsets(path: Path):
    out = {}
    with open(path, "rb") as fh:
        while True:
            off = fh.tell()
            line = fh.readline()
            if not line:
                break
            if not line.strip():
                continue
            r = json.loads(line)
            out[r["id"]] = (off, len(line), r)
    return out


def practice_index():
    out_path = SWEEP_OUT / "practice_index.json"
    if out_path.exists():
        return json.loads(out_path.read_text())
    from decimal import Decimal
    num = lambda v: str(Decimal(str(v).replace(",", "").strip()))  # noqa: E731
    original = {r["id"]: r for r in jl(PRACTICE_ORIGINAL)}
    curated = {r["id"]: r for r in jl(PRACTICE_CURATED)}
    mapping = json.loads(PRACTICE_MAP.read_text())
    rel = _offsets(PRACTICE_RELEASED)
    comp = _offsets(PRACTICE_COMPLETE)
    idx = {}
    for cid, g0 in original.items():
        g = curated.get(cid, g0)
        if cid in comp:
            src, (off, ln, r) = str(PRACTICE_COMPLETE), comp[cid]
        else:
            src, (off, ln, r) = str(PRACTICE_RELEASED), rel[cid]
        q = r["query"]
        fdir = PRACTICE_FILINGS / mapping[cid] if cid in mapping else D17.locate_filing_dir(q, [PRACTICE_FILINGS])
        concept, period = question(q)
        cik, stem = filing_key(q)
        pres, anyr = shipped_roles(q)
        idx[cid] = {"src": src, "offset": off, "length": ln, "rule": g["dqc_id"],
                    "ge": num(g["answer"]["extracted_value"]), "gc": num(g["answer"]["calculated_value"]),
                    "curated": cid in curated, "fdir": str(fdir), "filing": fdir.name, "cik": cik, "stem": stem,
                    "concept": concept, "period": list(period), "us_gaap_year": D17.us_gaap_year(q),
                    "shipped_pres_roles": pres, "shipped_roles": anyr, "split": "practice"}
    # conflicting duplicates: same CIK + concept + period, more than one distinct gold pair
    for subset in ("curated", "all"):
        groups = collections.defaultdict(set)
        for cid, e in idx.items():
            if subset == "curated" and not e["curated"]:
                continue
            groups[(e["cik"], e["concept"], tuple(e["period"]))].add((e["ge"], e["gc"]))
        for cid, e in idx.items():
            if subset == "curated" and not e["curated"]:
                continue
            e["conflict" if subset == "curated" else "conflict_332"] = len(groups[(e["cik"], e["concept"], tuple(e["period"]))]) > 1
    out_path.write_text(json.dumps(idx))
    return idx


def read_practice_query(entry: dict) -> str:
    return read_query(Path(entry["src"]), entry)
