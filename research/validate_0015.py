#!/usr/bin/env python3
"""Validate claude_agent/dqc/dqc_0015.py (official DQC_US_0015 logic) on practice, and profile dev.

    python3 validate_0015.py                  # everything
    python3 validate_0015.py --no-dev         # practice only
    python3 validate_0015.py --version 24     # evaluate the element list as of another DQC release
    python3 validate_0015.py --no-crosscheck  # skip the independent re-implementation

Practice gold is read only here. Dev has no gold and none is looked for.

1. Rule reproduction, 110 practice DQC_US_0015 cases, on all 330 and on the cases outside the
   conflicting-duplicate groups (same CIK + concept + period, different gold calculated value):
   is the gold among the findings; when the rule yields exactly one distinct answer, is it gold.
2. False positives: how often 0015 flags the questioned concept/period on 0117/0126 cases.
3. Multiplicity, a fact-level check of false positives and negatives: practice emits one case per
   finding, so n_cases_with_identical_query should equal n_findings for every distinct 0015
   query. It is also shown without duplicate elimination.
4. Tie-break, UNVALIDATED and reported apart from the rule: on multi-answer cases, is the first
   finding the gold, against the maximum ANY deterministic pick can reach on the same cases.
5. Exclusion dependency by one-at-a-time ablation over every matching reason (not the first).
6. Release sweep v17..v30: practice gold-among per release; dev cases whose answer set changes
   (a full sweep, so concepts listed only in other releases are seen too). v29 is CHOSEN;
   v20..v29 is the practice-consistent window only under a single-release assumption.
7. Independent cross-check (crosscheck_0015_independent.py, no shared code or constants):
   question-level and whole-filing agreement on practice and dev.
8. Constants vs. the published sources, namespace-aware. Synthetic self-tests of the module's own
   reading (regression tests, not evidence).
9. Dev profile: findings per case, multi-answer cases, contrast with the current submission.

Numbers are compared numerically (commas stripped, Decimal equality).
Writes validate_0015_report.json and validate_0015_dev_findings.json next to this script.
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import json
import re
import sys
import time
from decimal import Decimal, InvalidOperation
from pathlib import Path

ROOT = Path("/Users/xai/Desktop/FinReason")
sys.path.insert(0, str(ROOT / "claude-agent-sdk-benchmark"))

from claude_agent import task3_xbrl as X  # noqa: E402
from claude_agent.dqc import dqc_0015 as D  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
PRACTICE_INPUTS = ROOT / "dsh/task3_inputs.jsonl"
PRACTICE_GOLD = ROOT / "task3_source_data/curated/public_dev_curated.jsonl"
DEV_INPUTS = ROOT / "task3_source_data/ranked/development_inputs_hybrid_v0928.jsonl"
PRACTICE_FILINGS = ROOT / "task3_source_data/raw_filings"
DEV_FILINGS = ROOT / "task3_source_data/ranked/raw_filings_ranked"
CURRENT_DEV_PREDICTIONS = ROOT / "task3_source_data/ranked/predictions_dev_choice_majority_sign.jsonl"
REPORT = HERE / "validate_0015_report.json"
DEV_FINDINGS = HERE / "validate_0015_dev_findings.json"
SWEEP = range(17, D.LATEST_VERSION + 1)

SREF = re.compile(r'schemaRef[^>]*href="[^"]*?([\w.-]+?-\d{8})(?:_htm)?\.xsd"')
CIK = re.compile(r"<(?:xbrli:)?identifier[^>]*>(\d+)<")


def num(v):
    if v is None:
        return None
    try:
        return Decimal(str(v).replace(",", "").strip())
    except InvalidOperation:
        return None


def filing_dir(query: str, split: str):
    m = SREF.search(query)
    if not m:
        return None
    stem = m.group(1)
    if split == "dev":
        k = CIK.search(query.split("##Instance document", 1)[-1])
        d = DEV_FILINGS / f"{k.group(1).zfill(10)}-{stem}" if k else None
        return d if d and d.is_dir() else None
    hits = [p for p in PRACTICE_FILINGS.iterdir() if p.is_dir() and p.name.endswith("-" + stem)]
    return hits[0] if hits else None


def answers(fs):
    """Distinct (extracted, calculated) pairs, in finding order."""
    out = []
    for f in fs:
        p = (num(f["extracted"]), num(f["calculated"]))
        if p not in out:
            out.append(p)
    return out


def dist(counter):
    return {str(k): counter[k] for k in sorted(counter)}


def qhash(query: str) -> str:
    return hashlib.md5(query.encode()).hexdigest()


# --------------------------------------------------------------------------- #
# 8. Constants vs. published sources; self-tests
# --------------------------------------------------------------------------- #


def check_constants():
    """Module constants vs. MemberExclusions.xlsx + the explicit 2026 additions in the .xule,
    compared as (namespace family, local name). The sheet records the ConsolidatedEntitiesAxis
    pair as us-gaap (2017); its family comes from the srt: prefix the 2026 XULE literal gives it
    (the 2018 SRT move), and that move is reported, not hidden."""
    import crosscheck_0015_independent as C

    ex = C.load_exclusions()
    fam = lambda k: ("ext" if k[0] == "EXT" else k[0], k[1])  # noqa: E731
    src_members = {fam(m) for m in ex["members"]}
    src_axes = {fam(a) for a in ex["axes"]}
    src_pairs = {fam(a): {fam(m) for m in ms} for a, ms in ex["pairs"].items()}
    mod_pairs = {a: set(ms) for a, ms in D.EXCLUDE_NON_NEG_AXIS_MEMBERS}
    return {
        "strings_equal": set(D.EXCLUDE_NON_NEG_STRING_MEMBERS) == ex["strings"],
        "strings_only_in_module": sorted(set(D.EXCLUDE_NON_NEG_STRING_MEMBERS) - ex["strings"]),
        "strings_only_in_sources": sorted(ex["strings"] - set(D.EXCLUDE_NON_NEG_STRING_MEMBERS)),
        "members_equal": set(D.EXCLUDE_NON_NEG_MEMBERS) == src_members,
        "members_diff": sorted(set(D.EXCLUDE_NON_NEG_MEMBERS) ^ src_members),
        "axes_equal": set(D.EXCLUDE_NON_NEG_AXIS) == src_axes,
        "axes_diff": sorted(set(D.EXCLUDE_NON_NEG_AXIS) ^ src_axes),
        "pairs_equal": mod_pairs == src_pairs,
        "added_explicitly_in_2026_xule": {k: [list(x) if isinstance(x, tuple) else x for x in v] for k, v in ex["added_2026"].items()},
        "sheet_namespace_replaced_by_xule_literal": [list(x) for x in ex["sheet_namespace_replaced_by_xule_literal"]],
    }


_SYN_HEAD = ('<?xml version="1.0"?><xbrl xmlns="http://www.xbrl.org/2003/instance" '
             'xmlns:xbrldi="http://xbrl.org/2006/xbrldi" xmlns:iso4217="http://www.xbrl.org/2003/iso4217" '
             'xmlns:us-gaap="http://fasb.org/us-gaap/2024" xmlns:srt="http://fasb.org/srt/2024" '
             'xmlns:abc="http://abc.com/20241231" xmlns:agent="http://www.agent.example.com" '
             'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
             '<context id="c0"><entity><identifier scheme="http://www.sec.gov/CIK">1</identifier></entity>'
             '<period><instant>2024-12-31</instant></period></context>'
             '<context id="c0b"><entity><identifier scheme="http://www.sec.gov/CIK">1</identifier></entity>'
             '<period><instant>2024-12-31</instant></period></context>'
             '<context id="c1"><entity><identifier scheme="http://www.sec.gov/CIK">1</identifier><segment>'
             '<xbrldi:explicitMember dimension="abc:IncomeTaxEffectChangeInLawAxis">abc:XMember</xbrldi:explicitMember>'
             '</segment></entity><period><instant>2024-12-31</instant></period></context>'
             '<context id="c2"><entity><identifier scheme="http://www.sec.gov/CIK">1</identifier><segment>'
             '<xbrldi:explicitMember dimension="agent:IncomeTaxEffectChangeInLawAxis">abc:XMember</xbrldi:explicitMember>'
             '</segment></entity><period><instant>2024-12-31</instant></period></context>'
             '<unit id="usd"><measure>iso4217:USD</measure></unit><unit id="usd2"><measure>iso4217:USD</measure></unit>')
_SYN_Q = "\n##Schema document\n<xs:schema targetNamespace=\"http://abc.com/20241231\"></xs:schema>\n##Instance document\n{inst}\n##US GAAP Taxonomy\nNone\nQuestion1: What's the reported value of {c} in the Instance document for the period 2024-12-31?\nQuestion2: x\nAnswer:"


def _syn(facts, concept="us-gaap:AccountsPayableCurrent", close=True):
    inst = _SYN_HEAD + facts + ("</xbrl>" if close else "")
    return _SYN_Q.format(inst=inst, c=concept)


def selftest():
    """Regression tests of the module's own reading (self-referential by construction; the
    independent cross-check and the multiplicity check are the evidence)."""
    ns = {"us-gaap": "http://fasb.org/us-gaap/2024", "srt": "http://fasb.org/srt/2024",
          "abc": "http://abc.com/20241231", "agent": "http://www.agent.example.com",
          "country": "http://xbrl.sec.gov/country/2024"}
    ext = "http://abc.com/20241231"
    cases = [
        ([], None, None),
        ([("us-gaap:StatementBusinessSegmentsAxis", "abc:RetailMember")], None, "axis"),
        ([("us-gaap:StatementEquityComponentsAxis", "us-gaap:RetainedEarningsMember")], None, "axis"),
        ([("us-gaap:InvestmentIdentifierAxis", "abc:LoanToXMember")], None, "axis"),
        ([("abc:IncomeTaxEffectChangeInLawAxis", "abc:XMember")], None, "axis"),
        ([("abc:IncomeTaxEffectChangeInLawAxis", "abc:XMember")], ext, "axis"),
        ([("agent:IncomeTaxEffectChangeInLawAxis", "abc:XMember")], ext, None),  # not $EXTENSION_NS
        ([("us-gaap:IncomeTaxEffectChangeInLawAxis", "abc:XMember")], None, None),  # not the extension axis
        ([("srt:ConsolidatedEntitiesAxis", "srt:ParentCompanyMember")], None, "axis-member"),
        ([("srt:ConsolidatedEntitiesAxis", "abc:OperatingSubMember")], None, None),
        ([("us-gaap:FairValueByMeasurementBasisAxis", "us-gaap:ChangeDuringPeriodFairValueDisclosureMember")], None, "axis-member"),
        ([("us-gaap:FairValueByMeasurementBasisAxis", "us-gaap:CarryingReportedAmountFairValueDisclosureMember")], None, None),
        ([("srt:RestatementAxis", "srt:RestatementAdjustmentMember")], None, "member-substring"),
        ([("abc:FooAxis", "abc:IntersegmentEliminationsMember")], None, "member-substring"),
        ([("abc:FooAxis", "abc:BasisSwapYearOneMember")], None, "member-substring"),
        ([("abc:FooAxis", "abc:UnfundedCommitmentsMember")], None, "member-substring"),
        ([("abc:AdjustmentsAxis", "abc:OtherMember")], None, None),  # axis names are not substring-tested
        ([("abc:FooAxis", "<typed>adjustment")], None, None),  # typed values are not tested
        ([("us-gaap:FinancingReceivablePortfolioSegmentAxis", "us-gaap:UnallocatedFinancingReceivablesMember")], None, "member"),
        ([("us-gaap:StatementEquityComponentsAxis", "abc:Foo")], None, "axis"),
        ([("abc:FooAxis", "abc:CorporateNonSegmentMember")], None, None),  # extension member, not the us-gaap QName
        ([("srt:ProductOrServiceAxis", "us-gaap:CorporateNonSegmentMember")], None, "member"),
        ([("country:CountryAxis", "country:US")], None, None),
    ]
    results = []
    for dims, ext_ns, want in cases:
        got = D.exclusion_reason(dims, ns, ext_ns)
        ok = (got is None) if want is None else (got is not None and got.split(":", 1)[0] == want)
        results.append({"dims": dims, "ext_ns": ext_ns, "expected": want, "got": got, "ok": ok})
    both = D.exclusion_reasons([("us-gaap:AdjustmentsForNewAccountingPronouncementsAxis", "abc:CumulativeAdjustmentMember")], ns)
    results.append({"dims": "axis + 'adjust' member", "expected": "2 reasons", "got": both, "ok": len(both) == 2})

    F = 'us-gaap:AccountsPayableCurrent'
    behav = {}
    # @unit=*: a numeric-looking fact without a unit is not admitted
    behav["no_unit_rejected"] = [f["extracted"] for f in D.findings_0015(_syn(f'<{F} contextRef="c0" decimals="0">-5</{F}>'))] == []
    behav["with_unit_flagged"] = [f["extracted"] for f in D.findings_0015(_syn(f'<{F} contextRef="c0" unitRef="usd" decimals="0">-5</{F}>'))] == ["-5"]
    # duplicates: same aspects across context/unit ids collapse; precision-consistent values collapse to the more precise
    fs = D.findings_0015(_syn(f'<{F} contextRef="c0" unitRef="usd" decimals="0">-5</{F}><{F} contextRef="c0b" unitRef="usd2" decimals="0">-5</{F}>'))
    behav["aspect_duplicates_one_finding"] = [(f["extracted"], f["duplicates"]) for f in fs] == [("-5", 2)]
    fs = D.findings_0015(_syn(f'<{F} contextRef="c0" unitRef="usd" decimals="-5">-7000000</{F}><{F} contextRef="c0" unitRef="usd" decimals="-3">-6995000</{F}>'))
    behav["precision_duplicates_keep_more_precise"] = [(f["extracted"], f["duplicates"]) for f in fs] == [("-6995000", 2)]
    fs = D.findings_0015(_syn(f'<{F} contextRef="c0" unitRef="usd" decimals="0">-5</{F}><{F} contextRef="c0" unitRef="usd" decimals="0">-6</{F}>'))
    behav["inconsistent_duplicates_both_kept"] = sorted(f["extracted"] for f in fs) == ["-5", "-6"]
    # $EXTENSION_NS: only the entry-point namespace's IncomeTaxEffectChangeInLawAxis exempts
    fs = D.findings_0015(_syn(f'<{F} contextRef="c1" unitRef="usd" decimals="0">-1</{F}><{F} contextRef="c2" unitRef="usd" decimals="0">-2</{F}>'))
    behav["extension_axis_only_entry_point"] = [f["extracted"] for f in fs] == ["-2"]
    # truncation: error unless allowed; then flagged incomplete
    try:
        D.findings_0015(_syn(f'<{F} contextRef="c0" unitRef="usd" decimals="0">-5</{F}>', close=False))
        behav["truncated_raises"] = False
    except D.IncompleteInstanceError:
        behav["truncated_raises"] = True
    fs = D.findings_0015(_syn(f'<{F} contextRef="c0" unitRef="usd" decimals="0">-5</{F}>', close=False), allow_truncated=True)
    behav["truncated_allowed_is_flagged"] = [(f["extracted"], f["instance_complete"], f["instance_source"]) for f in fs] == [("-5", False, "query(truncated)")]
    # order: tie-break vs document
    fs_t = D.findings_0015(_syn(f'<{F} contextRef="c2" unitRef="usd" decimals="0">-2</{F}><{F} contextRef="c0" unitRef="usd" decimals="0">-3</{F}>'))
    fs_d = D.findings_0015(_syn(f'<{F} contextRef="c2" unitRef="usd" decimals="0">-2</{F}><{F} contextRef="c0" unitRef="usd" decimals="0">-3</{F}>'), order="document")
    behav["order_tiebreak_dimension_free_first"] = [f["extracted"] for f in fs_t] == ["-3", "-2"]
    behav["order_document"] = [f["extracted"] for f in fs_d] == ["-2", "-3"]
    listed = {
        "us-gaap:IncomeTaxReconciliationTaxCredits@29": D.is_listed("us-gaap:IncomeTaxReconciliationTaxCredits", 29),
        "us-gaap:IncomeTaxReconciliationTaxCredits@30": D.is_listed("us-gaap:IncomeTaxReconciliationTaxCredits", 30),
        "us-gaap:CostOfRevenue@20": D.is_listed("us-gaap:CostOfRevenue", 20),
        "us-gaap:CostOfRevenue@21": D.is_listed("us-gaap:CostOfRevenue", 21),
        "srt:LifeInsuranceInForceNet@29": D.is_listed("srt:LifeInsuranceInForceNet", 29),
        "us-gaap:NetIncomeLoss@29": D.is_listed("us-gaap:NetIncomeLoss", 29),
        "abc:Foo@29": D.is_listed("abc:Foo", 29),
    }
    expected_listed = {
        "us-gaap:IncomeTaxReconciliationTaxCredits@29": True, "us-gaap:IncomeTaxReconciliationTaxCredits@30": False,
        "us-gaap:CostOfRevenue@20": True, "us-gaap:CostOfRevenue@21": False,
        "srt:LifeInsuranceInForceNet@29": True, "us-gaap:NetIncomeLoss@29": False, "abc:Foo@29": False,
    }
    return {
        "exclusion_cases": len(results),
        "exclusion_cases_ok": sum(r["ok"] for r in results),
        "exclusion_failures": [r for r in results if not r["ok"]],
        "behaviour": behav,
        "behaviour_ok": all(behav.values()),
        "listing_ok": listed == expected_listed,
        "listing": listed,
    }


# --------------------------------------------------------------------------- #
# Practice
# --------------------------------------------------------------------------- #


def load_practice():
    rows = [json.loads(l) for l in open(PRACTICE_INPUTS)]
    gold = {}
    for l in open(PRACTICE_GOLD):
        r = json.loads(l)
        gold[r["id"]] = (num(r["answer"]["extracted_value"]), num(r["answer"]["calculated_value"]), r["dqc_id"])
    groups = collections.defaultdict(list)
    for r in rows:
        q = X.parse_question(r["query"])
        k = CIK.search(r["query"].split("##Instance document", 1)[-1])
        groups[(k.group(1) if k else "?", q.concept, q.start, q.end, q.instant)].append(r["id"])
    dirty_groups = [ids for ids in groups.values() if len({gold[i][1] for i in ids}) > 1]
    dirty = {i for ids in dirty_groups for i in ids}
    by_hash = collections.defaultdict(list)
    for r in rows:
        by_hash[qhash(r["query"])].append(r["id"])
    hash_dirty_groups = [ids for ids in by_hash.values() if len({gold[i][:2] for i in ids}) > 1]
    conflicts = {
        "definition": "same CIK + concept + period, different gold calculated value",
        "cases": len(dirty), "groups": len(dirty_groups),
        "query_hash_definition": {"cases": sum(len(g) for g in hash_dirty_groups), "groups": len(hash_dirty_groups)},
        "note": "the brief's figure of 49 does not reproduce on these 330 cases",
    }
    return rows, gold, dirty, conflicts


def evaluate(rows, split, versions, default_version):
    """{version: {id: findings}} plus {id: findings with rejections at default_version}."""
    per = {v: {} for v in versions}
    rejected = {}
    for r in rows:
        fd = filing_dir(r["query"], split)
        for v in versions:
            per[v][r["id"]] = D.findings_0015(r["query"], fd, version=v)
        rejected[r["id"]] = D.findings_0015(r["query"], fd, version=default_version, include_rejected=True)
    return per, rejected


def summarize_0015(rows, gold, per_case, subset):
    ids = [r["id"] for r in rows if r["dqc_id"] == "DQC_US_0015" and r["id"] in subset]
    n_find, n_ans = collections.Counter(), collections.Counter()
    gold_in = one_ans = one_ans_right = one_find = 0
    misses = []
    for i in ids:
        fs = per_case[i]
        ans = answers(fs)
        n_find[min(len(fs), 5)] += 1
        n_ans[min(len(ans), 5)] += 1
        one_find += len(fs) == 1
        if gold[i][:2] in ans:
            gold_in += 1
        else:
            misses.append(i)
        if len(ans) == 1:
            one_ans += 1
            one_ans_right += ans[0] == gold[i][:2]
    return {
        "cases": len(ids),
        "gold_among_findings": gold_in,
        "exactly_one_finding": one_find,
        "exactly_one_distinct_answer": one_ans,
        "exactly_one_distinct_answer_and_it_is_gold": one_ans_right,
        "more_than_one_distinct_answer": len(ids) - one_ans - n_ans[0],
        "zero_findings": n_find[0],
        "findings_per_case": dist(n_find),
        "distinct_answers_per_case": dist(n_ans),
        "gold_not_among_findings": misses,
    }


def summarize_other(rows, gold, per_case, subset, rule):
    ids = [r["id"] for r in rows if r["dqc_id"] == rule and r["id"] in subset]
    fires = coincide_extracted = coincide_both = 0
    n_find = collections.Counter()
    fired_ids = []
    for i in ids:
        fs = per_case[i]
        n_find[min(len(fs), 5)] += 1
        if fs:
            fires += 1
            fired_ids.append(i)
            ans = answers(fs)
            coincide_extracted += any(a[0] == gold[i][0] for a in ans)
            coincide_both += gold[i][:2] in ans
    return {
        "cases": len(ids),
        "0015_fires_on_questioned_concept_period": fires,
        "a_0015_finding_has_gold_extracted": coincide_extracted,
        "a_0015_finding_equals_gold_pair": coincide_both,
        "findings_per_case": dist(n_find),
        "fired_ids": fired_ids,
    }


def tiebreak(rows, gold, per_case, subset):
    """UNVALIDATED tie-break accuracy on multi-answer 0015 cases, against the best any
    deterministic pick could do (cases with byte-identical queries must get the same answer)."""
    byid = {r["id"]: r for r in rows}
    ids = [r["id"] for r in rows if r["dqc_id"] == "DQC_US_0015" and r["id"] in subset and len(answers(per_case[r["id"]])) > 1]
    first_tie = sum(answers(per_case[i])[0] == gold[i][:2] for i in ids)
    first_doc = 0
    for i in ids:
        doc_first = min(per_case[i], key=lambda f: f["pos"])
        first_doc += (num(doc_first["extracted"]), num(doc_first["calculated"])) == gold[i][:2]
    groups = collections.defaultdict(list)
    for i in ids:
        groups[qhash(byid[i]["query"])].append(i)
    best = 0
    for g in groups.values():
        cands = answers(per_case[g[0]])
        best += max(sum(gold[i][:2] == a for i in g) for a in cands)
    return {
        "status": "UNVALIDATED heuristic, not rule logic",
        "multi_answer_cases": len(ids),
        "distinct_queries_among_them": len(groups),
        "max_any_deterministic_pick": best,
        "first_finding_is_gold_order_tiebreak": first_tie,
        "first_finding_is_gold_order_document": first_doc,
        "every_multi_answer_query_is_a_permutation_group": all(
            sorted(map(str, (gold[i][:2] for i in g))) == sorted(map(str, answers(per_case[g[0]]))) for g in groups.values()),
    }


def multiplicity(rows, per_case):
    """Practice emits one case per finding: n_cases_with_identical_query vs n_findings."""
    groups = collections.defaultdict(list)
    for r in rows:
        if r["dqc_id"] == "DQC_US_0015":
            groups[qhash(r["query"])].append(r["id"])
    tab, tab_raw = collections.Counter(), collections.Counter()
    mism, mism_raw = [], []
    for ids in groups.values():
        fs = per_case[ids[0]]
        n_raw = sum(f["duplicates"] for f in fs)
        tab[(len(ids), len(fs))] += 1
        tab_raw[(len(ids), n_raw)] += 1
        if len(ids) != len(fs):
            mism.append({"ids": ids, "n_cases": len(ids), "n_findings": len(fs), "values": [f["extracted"] for f in fs]})
        if len(ids) != n_raw:
            mism_raw.append({"ids": ids, "n_cases": len(ids), "n_facts_without_dedup": n_raw})
    return {
        "distinct_0015_queries": len(groups),
        "n_cases_equals_n_findings": sum(v for (a, b), v in tab.items() if a == b),
        "table_(n_cases,n_findings)": {f"{a},{b}": v for (a, b), v in sorted(tab.items())},
        "mismatches": mism,
        "without_duplicate_elimination": {
            "n_cases_equals_n_facts": sum(v for (a, b), v in tab_raw.items() if a == b),
            "mismatches": mism_raw,
        },
    }


def miss_details(rows, gold, ids, rejected, version):
    byid = {r["id"]: r for r in rows}
    out = []
    for i in ids:
        q = X.parse_question(byid[i]["query"])
        out.append({
            "id": i, "concept": q.concept, "period": [q.start, q.end, q.instant],
            "gold": [str(gold[i][0]), str(gold[i][1])], "listed": D.is_listed(q.concept, version),
            "facts_for_concept_period": [{"value": f["extracted"], "ctx": f["context_id"], "dims": f["dims"],
                                          "rejected": f.get("rejected_all")} for f in rejected[i]],
        })
    return out


# --------------------------------------------------------------------------- #
# 5. Exclusion dependency by ablation
# --------------------------------------------------------------------------- #

_FILTER_REASONS = {"nil", "no-unit", "non-numeric", "not-negative", "not-listed"}


def _item(reason: str) -> str:
    """The constant a reason rests on: string:<s>, member:<m>, axis:<a>, pair:<a>=<m>."""
    kind, rest = reason.split(":", 1)
    if kind == "member-substring":
        return "string:" + rest.split(":", 1)[0]
    return {"member": "member:", "axis": "axis:", "axis-member": "pair:"}[kind] + rest


def ablation(rejected: dict, flagged: dict) -> dict:
    """For each constant: the cases whose answer set (or only finding count) changes when that
    one constant is dropped. A fact becomes flagged only when EVERY reason exempting it rests on
    the dropped constant."""
    exempted = collections.Counter()
    sole = collections.Counter()
    ans_change = collections.defaultdict(set)
    count_change = collections.defaultdict(set)
    for cid, recs in rejected.items():
        have = {f["extracted"] for f in flagged[cid]}
        for f in recs:
            rs = f.get("rejected_all") or []
            if not rs or rs[0] in _FILTER_REASONS:
                continue
            items = {_item(x) for x in rs}
            for it in items:
                exempted[it] += 1
            if len(items) == 1:
                it = next(iter(items))
                sole[it] += 1
                (count_change if f["extracted"] in have else ans_change)[it].add(cid)
    return {
        "exempted_negative_listed_facts_by_constant": dict(sorted(exempted.items())),
        "facts_exempted_by_that_constant_alone": dict(sorted(sole.items())),
        "cases_whose_answer_set_changes_if_dropped": {k: sorted(v) for k, v in sorted(ans_change.items())},
        "cases_whose_finding_count_only_changes_if_dropped": {k: sorted(v - ans_change[k]) for k, v in sorted(count_change.items()) if v - ans_change[k]},
    }


# --------------------------------------------------------------------------- #
# 6. Release sweep
# --------------------------------------------------------------------------- #


def sweep_changes(per: dict, ids) -> dict:
    """Cases whose answer set differs across releases: {id: {answers: [versions...]}}."""
    out = {}
    for i in ids:
        by = collections.defaultdict(list)
        for v in sorted(per):
            by[tuple(str(a[0]) for a in sorted(answers(per[v][i]), key=lambda a: a[0]))].append(v)
        if len(by) > 1:
            out[i] = {(" ".join(k) or "-"): f"v{min(vs)}-v{max(vs)}" if vs == list(range(min(vs), max(vs) + 1)) else vs
                      for k, vs in by.items()}
    return out


# --------------------------------------------------------------------------- #
# 7. Independent cross-check
# --------------------------------------------------------------------------- #


def _dims_key(dims):
    """Module dims [[axis, member], ...] -> sorted (axis local, member local or '<typed>')."""
    return tuple(sorted((a.split(":")[-1], "<typed>" if m.startswith("<typed>") else m.split(":")[-1]) for a, m in dims))


def crosscheck(rows, split, version, per_case):
    """Module vs. crosscheck_0015_independent.py at ``version``: per case (questioned
    concept/period, ``per_case`` = the module's findings) and per filing (every flagged fact)."""
    import crosscheck_0015_independent as C

    items, excl = C.load_items(), C.load_exclusions()
    by_inst = collections.defaultdict(list)
    for r in rows:
        by_inst[hashlib.md5(C.section(r["query"], "##Instance document").encode()).hexdigest()].append(r)
    q_agree = q_n = f_agree = f_n = flagged_facts = 0
    q_diff, f_diff = [], []
    for key, group in by_inst.items():
        cache = {}
        whole = None
        for r in group:
            fd = filing_dir(r["query"], split)
            qf, run_all, _ = C.case_findings(r["query"], items, excl, version, fd, cache)
            mine = collections.Counter((num(f["extracted"]), _dims_key(f["dims"])) for f in per_case[r["id"]])
            theirs = collections.Counter((v, dims) for _, _, v, dims, _ in qf)
            q_n += 1
            if mine == theirs:
                q_agree += 1
            else:
                q_diff.append({"id": r["id"], "module_only": [str(k) for k in (mine - theirs)], "independent_only": [str(k) for k in (theirs - mine)]})
            if whole is None:
                whole = (run_all(), r, fd)
        allf, r0, fd0 = whole
        mod_all = collections.Counter(
            (f["concept"].split(":")[-1], (f["period"]["start"], f["period"]["end"], f["period"]["instant"]),
             num(f["extracted"]), _dims_key(f["dims"]))
            for f in D.all_findings_0015(r0["query"], fd0, version=version))
        ind_all = collections.Counter((k[1], p, v, dims) for k, p, v, dims, _ in allf)
        f_n += 1
        flagged_facts += sum(ind_all.values())
        if mod_all == ind_all:
            f_agree += 1
        else:
            f_diff.append({"filing_of": r0["id"], "module_only": [str(k) for k in (mod_all - ind_all)][:5],
                           "independent_only": [str(k) for k in (ind_all - mod_all)][:5]})
    return {"split": split, "question_level_agree": q_agree, "question_level_cases": q_n, "question_level_diffs": q_diff,
            "filing_level_agree": f_agree, "filings": f_n, "filing_level_flagged_facts_independent": flagged_facts,
            "filing_level_diffs": f_diff}


# --------------------------------------------------------------------------- #
# 9. Dev
# --------------------------------------------------------------------------- #


def dev_profile(rows, per_default, version):
    """Structural profile, no gold. Also contrasts the official findings with the submitted
    answers in CURRENT_DEV_PREDICTIONS (the 94.12% upload):
      A  submitted answer is 0015-shaped (calc == -extracted < 0) and is an official finding
      B  submitted answer is 0015-shaped but the official rule raises nothing for the question
      C  submitted answer is 0015-shaped, the rule raises findings, none equals it
      D  submitted answer is not 0015-shaped, yet the rule raises a finding
      F  neither
    """
    cur = {}
    if CURRENT_DEV_PREDICTIONS.exists():
        for l in open(CURRENT_DEV_PREDICTIONS):
            p = json.loads(l)
            cur[p["id"]] = (num(p["extracted_value"]), num(p["calculated_value"]))
    n_find, n_ans = collections.Counter(), collections.Counter()
    cats = collections.defaultdict(list)
    multi, fires, sens = [], 0, []
    per = {}
    for r in rows:
        fs = per_default[r["id"]]
        ans = answers(fs)
        n_find[min(len(fs), 5)] += 1
        n_ans[min(len(ans), 5)] += 1
        fires += bool(fs)
        if len(ans) > 1:
            multi.append(r["id"])
        if any(f["version_sensitive"] for f in fs):
            sens.append(r["id"])
        per[r["id"]] = [[f["extracted"], f["calculated"], f["context_id"], bool(f["dims"])] for f in fs]
        if r["id"] in cur:
            e, c = cur[r["id"]]
            shaped = e is not None and c is not None and e < 0 and c == -e
            if shaped and (e, c) in ans:
                k = "A"
            elif shaped and not ans:
                k = "B"
            elif shaped:
                k = "C"
            elif ans and (e, c) not in ans:
                k = "D"
            elif ans:
                k = "A"
            else:
                k = "F"
            rec = r["id"]
            if k in "BCD":
                q = X.parse_question(r["query"])
                rec = {"id": r["id"], "concept": q.concept, "submitted": [str(e), str(c)],
                       "official": [[str(a), str(b)] for a, b in ans], "concept_listed": D.is_listed(q.concept, version)}
            cats[k].append(rec)
    out = {
        "cases": len(rows),
        "cases_with_a_finding": fires,
        "findings_per_case": dist(n_find),
        "distinct_answers_per_case": dist(n_ans),
        "multi_answer_cases_decided_by_tiebreak": multi,
        "cases_with_version_sensitive_finding": sens,
    }
    if cur:
        out["vs_submitted_" + CURRENT_DEV_PREDICTIONS.name] = {
            "counts": {k: len(v) for k, v in sorted(cats.items())},
            "B_submitted_0015_shaped_but_rule_cannot_fire": cats.get("B", []),
            "C_rule_fires_on_a_different_fact": cats.get("C", []),
            "D_rule_fires_but_submitted_answer_not_0015": cats.get("D", []),
        }
    return out, per


# --------------------------------------------------------------------------- #


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", type=int, default=D.DEFAULT_VERSION)
    ap.add_argument("--no-dev", action="store_true")
    ap.add_argument("--no-sweep", action="store_true")
    ap.add_argument("--no-crosscheck", action="store_true")
    args = ap.parse_args()
    t0 = time.time()
    versions = list(SWEEP) if not args.no_sweep else [args.version]
    if args.version not in versions:
        versions.append(args.version)

    report = {"version": args.version, "version_status": "chosen (single-release window v20-v29 on practice)",
              "approximations": list(D.APPROXIMATIONS), "heuristics": list(D.HEURISTICS)}
    report["constants_vs_sources"] = cc = check_constants()
    print("constants vs sources (namespace-aware):", {k: v for k, v in cc.items() if k.endswith("_equal")},
          "| sheet namespace replaced by the 2026 XULE literal:", [f"{a}->{b}:{c}" for a, b, c in cc["sheet_namespace_replaced_by_xule_literal"]])
    st = selftest()
    report["selftest"] = st
    print(f"selftest (regression, self-referential): exclusion cases {st['exclusion_cases_ok']}/{st['exclusion_cases']}, "
          f"behaviour {sum(st['behaviour'].values())}/{len(st['behaviour'])}, listing ok={st['listing_ok']}")
    for f in st["exclusion_failures"]:
        print("  FAIL", f)
    for k, ok in st["behaviour"].items():
        if not ok:
            print("  FAIL behaviour", k)

    rows, gold, dirty, conflicts = load_practice()
    all_ids = {r["id"] for r in rows}
    clean = all_ids - dirty
    print(f"\npractice: {len(rows)} cases; conflicting duplicates {conflicts['cases']} cases in {conflicts['groups']} groups "
          f"(query-hash definition: {conflicts['query_hash_definition']}); rest {len(clean)}")
    print(f"  by rule (all): {dict(collections.Counter(r['dqc_id'] for r in rows))}")
    print(f"  by rule (rest): {dict(collections.Counter(r['dqc_id'] for r in rows if r['id'] in clean))}")

    per, rejected = evaluate(rows, "practice", versions, args.version)
    pc = per[args.version]
    prac = {"conflicting_duplicates": conflicts}
    for name, subset in (("all", all_ids), ("rest", clean)):
        prac[name] = {
            "DQC_US_0015": summarize_0015(rows, gold, pc, subset),
            "DQC_US_0117": summarize_other(rows, gold, pc, subset, "DQC_US_0117"),
            "DQC_US_0126": summarize_other(rows, gold, pc, subset, "DQC_US_0126"),
            "tiebreak_unvalidated": tiebreak(rows, gold, pc, subset),
        }
    prac["multiplicity"] = mult = multiplicity(rows, pc)
    prac["miss_details"] = miss_details(rows, gold, prac["all"]["DQC_US_0015"]["gold_not_among_findings"], rejected, args.version)
    prac["exclusion_dependency"] = abl_p = ablation(rejected, pc)
    report["practice"] = prac

    for name in ("all", "rest"):
        s = prac[name]["DQC_US_0015"]
        t = prac[name]["tiebreak_unvalidated"]
        print(f"\n[{name}] DQC_US_0015 cases: {s['cases']}")
        print(f"  gold among findings                 : {s['gold_among_findings']}")
        print(f"  exactly one distinct answer         : {s['exactly_one_distinct_answer']} (it is gold: {s['exactly_one_distinct_answer_and_it_is_gold']})")
        print(f"  more than one distinct answer       : {s['more_than_one_distinct_answer']}")
        print(f"  zero findings                       : {s['zero_findings']}")
        print(f"  findings/case                       : {s['findings_per_case']}")
        print(f"  distinct answers/case               : {s['distinct_answers_per_case']}")
        print(f"  gold not among findings             : {s['gold_not_among_findings']}")
        print(f"  tie-break (UNVALIDATED) on {t['multi_answer_cases']} multi-answer cases / {t['distinct_queries_among_them']} queries: "
              f"first finding is gold {t['first_finding_is_gold_order_tiebreak']} (order=tiebreak), "
              f"{t['first_finding_is_gold_order_document']} (order=document); max any deterministic pick {t['max_any_deterministic_pick']}; "
              f"all permutation groups: {t['every_multi_answer_query_is_a_permutation_group']}")
        for rule in ("DQC_US_0117", "DQC_US_0126"):
            o = prac[name][rule]
            print(f"  {rule}: {o['cases']} cases, 0015 fires on {o['0015_fires_on_questioned_concept_period']} "
                  f"(has gold extracted: {o['a_0015_finding_has_gold_extracted']}, equals gold pair: {o['a_0015_finding_equals_gold_pair']})")
    print(f"\nmultiplicity: n_cases == n_findings for {mult['n_cases_equals_n_findings']}/{mult['distinct_0015_queries']} distinct 0015 queries; "
          f"table {mult['table_(n_cases,n_findings)']}; mismatches {[(m['ids'], m['n_findings']) for m in mult['mismatches']]}")
    print(f"  without duplicate elimination: {mult['without_duplicate_elimination']['n_cases_equals_n_facts']}/{mult['distinct_0015_queries']}; "
          f"mismatches {mult['without_duplicate_elimination']['mismatches']}")
    print(f"practice exclusion dependency (ablation): answer set changes {abl_p['cases_whose_answer_set_changes_if_dropped']}; "
          f"count only {abl_p['cases_whose_finding_count_only_changes_if_dropped']}")

    if not args.no_sweep:
        sweep = {}
        for v in versions:
            s = summarize_0015(rows, gold, per[v], all_ids)
            sweep[v] = {"0015_gold_among": s["gold_among_findings"], "0015_one_answer": s["exactly_one_distinct_answer"],
                        "0015_one_answer_gold": s["exactly_one_distinct_answer_and_it_is_gold"],
                        "0117_fires": summarize_other(rows, gold, per[v], all_ids, "DQC_US_0117")["0015_fires_on_questioned_concept_period"],
                        "0126_fires": summarize_other(rows, gold, per[v], all_ids, "DQC_US_0126")["0015_fires_on_questioned_concept_period"],
                        "misses": s["gold_not_among_findings"]}
        window = [v for v in versions if sweep[v]["0015_gold_among"] == max(x["0015_gold_among"] for x in sweep.values())]
        report["release_sweep_practice"] = {"per_version": sweep, "single_release_window": [min(window), max(window)],
                                            "answer_set_changes": sweep_changes(per, sorted(all_ids))}
        print(f"\nrelease sweep, practice (all 330): v{args.version} chosen; single-release window v{min(window)}-v{max(window)}")
        for v, s in sweep.items():
            print(f"  v{v}: 0015 gold among {s['0015_gold_among']}/110, one-answer {s['0015_one_answer']} (gold {s['0015_one_answer_gold']}); "
                  f"fires on 0117 {s['0117_fires']}, on 0126 {s['0126_fires']}; misses {s['misses']}")
        print(f"  practice cases whose answer set changes across v17-v30: {report['release_sweep_practice']['answer_set_changes']}")

    if not args.no_crosscheck:
        xc = crosscheck(rows, "practice", args.version, pc)
        report["crosscheck_independent_practice"] = xc
        print(f"\nindependent cross-check, practice: question level {xc['question_level_agree']}/{xc['question_level_cases']}; "
              f"filing level {xc['filing_level_agree']}/{xc['filings']} filings ({xc['filing_level_flagged_facts_independent']} flagged facts)")
        for d in xc["question_level_diffs"][:5] + xc["filing_level_diffs"][:5]:
            print("   DIFF", d)

    if not args.no_dev:
        drows = [json.loads(l) for l in open(DEV_INPUTS)]
        dper, drej = evaluate(drows, "dev", versions, args.version)
        dev, per_out = dev_profile(drows, dper[args.version], args.version)
        dev["exclusion_dependency"] = abl_d = ablation(drej, dper[args.version])
        if not args.no_sweep:
            dev["release_sweep_answer_set_changes"] = sweep_changes(dper, [r["id"] for r in drows])
        if not args.no_crosscheck:
            dev["crosscheck_independent"] = xd = crosscheck(drows, "dev", args.version, dper[args.version])
        dev["instances"] = dict(collections.Counter(
            f"{i['instance_source']}/{i['extension_ns_source']}" for i in (D.instance_info(r["query"], filing_dir(r["query"], "dev")) for r in drows)))
        report["dev"] = dev
        print(f"\ndev: {dev['cases']} cases, {dev['cases_with_a_finding']} with a finding; findings/case {dev['findings_per_case']}; "
              f"distinct answers/case {dev['distinct_answers_per_case']}")
        print(f"  multi-answer cases (decided by the UNVALIDATED tie-break): {len(dev['multi_answer_cases_decided_by_tiebreak'])} {dev['multi_answer_cases_decided_by_tiebreak']}")
        print(f"  instances: {dev['instances']}")
        if not args.no_sweep:
            print(f"  answer set changes across v17-v30 (full sweep): {dev['release_sweep_answer_set_changes']}")
        print(f"  exclusion dependency (ablation): answer set changes {abl_d['cases_whose_answer_set_changes_if_dropped']}; "
              f"count only {abl_d['cases_whose_finding_count_only_changes_if_dropped']}")
        if not args.no_crosscheck:
            print(f"  independent cross-check: question level {xd['question_level_agree']}/{xd['question_level_cases']}; "
                  f"filing level {xd['filing_level_agree']}/{xd['filings']} filings ({xd['filing_level_flagged_facts_independent']} flagged facts)")
            for d in xd["question_level_diffs"][:5] + xd["filing_level_diffs"][:5]:
                print("   DIFF", d)
        for k, v in dev.items():
            if k.startswith("vs_"):
                print(f"  {k}: {v['counts']}")
                for cat in ("C_rule_fires_on_a_different_fact", "D_rule_fires_but_submitted_answer_not_0015"):
                    for rec in v[cat]:
                        print(f"    {cat[0]} {rec['id']} {rec['concept']} submitted {rec['submitted']} official {rec['official']}")
                print(f"    B ids: {[rec['id'] for rec in v['B_submitted_0015_shaped_but_rule_cannot_fire']]}")
        DEV_FINDINGS.write_text(json.dumps(per_out, indent=0))

    report["seconds"] = round(time.time() - t0, 1)
    REPORT.write_text(json.dumps(report, indent=1, default=str))
    print(f"\nwrote {REPORT} ({report['seconds']} s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
