#!/usr/bin/env python3
"""Validate claude_agent/dqc/dqc_0126.py (faithful DQC_US_0126) on practice gold; run it on dev.

Practice (gold known, used ONLY for validation):
  inputs  /Users/xai/Desktop/FinReason/dsh/task3_inputs.jsonl          (330 cases)
  gold    task3_source_data/curated/public_dev_curated.jsonl           (330 curated golds)
  release task3_source_data/finmr_public_dev/public_dev{,_inputs}.jsonl (original 332-case release;
          DEV_000273, the 0126 case removed from curation for its digit-typo gold, is reported apart)

Modes (row keys in the JSON):
  query     "released linkbases + complete instance": findings_0126(query) on the dsh inputs, which
            splice the filing's complete instance into the released, statement-scoped query.  This
            is NOT the original release; dev inputs (development_inputs_hybrid_v0928) have the same
            shape.
  filing    complete filing: .xsd (roleType definitions, embedded linkbases) + every presentation/
            calculation/definition linkbase + the complete instance (findings_0126(query, filing_dir)).
  original  practice only: the original 332-case release as published (truncated, statement-scoped
            instance; query sections only).  A robustness probe -- the ranked inputs are not like this.

Checks reported:
  * per-rule reproduction of gold (0126 cases) and firing on the other rules' cases, all cases and
    without the conflicting duplicates (string-level and numeric-level counts both stated);
  * FILING LEVEL: in every practice filing that holds a released 0126 case, all_findings_0126 vs the
    released 0126 questions of that filing (precision and recall -- the over-firing test the
    question-scoped numbers cannot give);
  * the released calculation network equals the complete filing's network (practice and dev);
  * dev: findings per case, gates, every reading-sensitive case (fires_alt), the old solver's
    grandchild-expansion delta, and the faithful 0015/0117 outcome for every case, with the
    disagreements against the best upload (predictions_dev_choice_majority_sign.jsonl = 94.12%)
    listed with all evidence columns.  Agreement with our own submission is not accuracy.
  * --before PATH: per-case before/after against an earlier results JSON of this script.

Usage:
  python3 validate_0126.py [--skip-dev] [--dev-limit N] [--no-siblings] [--before OLD.json]
                           [--out validate_0126_results.json]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from collections import Counter, defaultdict
from decimal import Decimal, InvalidOperation
from pathlib import Path

sys.path.insert(0, "/Users/xai/Desktop/FinReason/claude-agent-sdk-benchmark")
from claude_agent import task3_xbrl as X  # noqa: E402
from claude_agent.dqc import dqc_0126 as D  # noqa: E402

ROOT = Path("/Users/xai/Desktop/FinReason")
PRACTICE_INPUTS = ROOT / "dsh/task3_inputs.jsonl"
GOLD = ROOT / "task3_source_data/curated/public_dev_curated.jsonl"
ORIG_GOLD = ROOT / "task3_source_data/finmr_public_dev/public_dev.jsonl"
ORIG_INPUTS = ROOT / "task3_source_data/finmr_public_dev/public_dev_inputs.jsonl"
DEV_INPUTS = ROOT / "task3_source_data/ranked/development_inputs_hybrid_v0928.jsonl"
BEST_DEV = ROOT / "task3_source_data/ranked/predictions_dev_choice_majority_sign.jsonl"
BASE_DETAIL = ROOT / "task3_source_data/ranked/predictions_dev_detail.jsonl"
CHANGES = ROOT / "task3_source_data/ranked/predictions_dev_choice_majority_sign_changes.json"
DEFAULT_OUT = Path(__file__).resolve().parent / "validate_0126_results.json"

MODE_LABELS = {
    "query": "released linkbases + complete instance (query only)",
    "filing": "complete filing DTS (.xsd + all linkbases, incl. embedded) + complete instance",
    "original": "original 332-case release as published (truncated, statement-scoped; query only)",
}

_CIK_RE = re.compile(r"<(?:xbrli:)?identifier\b[^>]*>\s*0*(\d+)\s*</")


def N(s):
    if s is None:
        return None
    try:
        return Decimal(str(s).replace(",", "").strip())
    except InvalidOperation:
        return None


def jl(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            if line.strip():
                yield json.loads(line)


def pct(a, b):
    return f"{a}/{b}" + (f" ({100.0 * a / b:.1f}%)" if b else "")


def md5(path):
    try:
        return hashlib.md5(Path(path).read_bytes()).hexdigest()
    except OSError:
        return None


def case_key(query):
    q = X.parse_question(query)
    i = query.find("##Instance document")
    m = _CIK_RE.search(query[i:] if i >= 0 else query)
    return (m.group(1) if m else None, q.concept, q.period_key)


def q_key(query):
    """(concept, (start, end, instant)) of the question, dates normalised like dqc_0126."""
    q = X.parse_question(query)
    return q.concept, tuple(D._norm_date(x) for x in q.period_key)


def finding_key(f):
    p = f["period"]
    return f["concept"], (p["start"], p["end"], p["instant"])


# --------------------------------------------------------------------------- #
# Conflicting duplicates
# --------------------------------------------------------------------------- #


def conflicting_duplicates():
    """Practice cases in (CIK, concept, period) groups whose gold pairs differ.

    Two counts: 'string' compares the gold text as released ('-4000000' != '-4,000,000');
    'numeric' compares the numbers (the count used for the non-conflicting subsets).
    """
    orig = {r["id"]: r for r in jl(ORIG_GOLD)}
    groups = defaultdict(list)
    for r in jl(ORIG_INPUTS):
        groups[case_key(r["query"])].append(r["id"])
    out = {}
    for kind, norm in (("string", lambda s: str(s).strip()), ("numeric", N)):
        conf, ngroups = set(), 0
        for ids in groups.values():
            if len(ids) < 2:
                continue
            pairs = {(norm(orig[i]["answer"]["extracted_value"]), norm(orig[i]["answer"]["calculated_value"]))
                     for i in ids}
            if len(pairs) > 1:
                ngroups += 1
                conf.update(ids)
        out[kind] = {"ids": conf, "groups": ngroups,
                     "by_rule": dict(Counter(orig[i]["dqc_id"] for i in conf))}
    return out


# --------------------------------------------------------------------------- #
# Practice
# --------------------------------------------------------------------------- #


def gold_hit(findings, ans):
    ge, gc = N(ans["extracted_value"]), N(ans["calculated_value"])
    both = [f for f in findings if N(f["parent_value"]) == ge and N(f["children_sum"]) == gc]
    ext = [f for f in findings if N(f["parent_value"]) == ge]
    return both, ext


def gate_label(ex):
    g = ex.get("gate")
    if g == "not_parent_in_checked_role":
        sts = sorted({s["status"] for s in ex.get("parent_roles", [])})
        return g + (":" + "|".join(sts) if sts else ":not_a_calc_parent")
    return g


def mode_row(ex, ans=None):
    fs = ex.get("findings", [])
    row = {
        "n": len(fs),
        "gate": gate_label(ex),
        "pairs": [[f["parent_value"], f["children_sum"]] for f in fs],
        "released_role_status": next((s["status"] for s in ex.get("roles", []) if s["released"]), None),
        "released_role_def_source": next((s["definition_source"] for s in ex.get("roles", []) if s["released"]),
                                         None),
        "role_def_mode": ex.get("role_def_mode"),
        "duplicates_removed": ex.get("duplicates_removed"),
        # every contextRef in the instance became a parsed fact with a context (task3_xbrl reads
        # double-quoted attributes only; this makes silent fact loss visible)
        "instance_ok": (lambda ic: bool(ic) and ic.get("contextRef_attributes") == ic.get("facts_parsed")
                        and not ic.get("facts_without_context"))(ex.get("instance_check") or {}),
        "fs_tied": any(f["fs_decimals_tied"] for f in fs),
        "calc11": any(f["calc11"] for f in fs),
        "multi_value_children": any(f["multi_value_children"] for f in fs),
        "fires_alt": [f["fires_alt"] for f in fs],
        "question_is_current_period": ex.get("question_is_current_period"),
        "findings": [{k: f[k] for k in ("role", "released_role", "role_definition_source", "parent_value",
                                        "children_sum", "n_addends", "n_children", "fs_decimals", "tolerance",
                                        "difference", "fires_alt", "children_detail")} for f in fs],
    }
    if ans is not None:
        both, ext = gold_hit(fs, ans)
        row["gold_hit"] = bool(both)
        row["gold_ext_hit"] = bool(ext)
        row["alt_ok"] = ({k: all(f["fires_alt"].get(k, True) for f in both)
                          for k in ("min_child_decimals", "all_children_counted")} if both else None)
    return row


def run_practice():
    gold = {r["id"]: r for r in jl(GOLD)}
    orig_q = {r["id"]: r["query"] for r in jl(ORIG_INPUTS)}
    conf = conflicting_duplicates()
    rows = []
    t0 = time.time()
    for r in jl(PRACTICE_INPUTS):
        rid, rule, query = r["id"], r["dqc_id"], r["query"]
        fdir = D.find_filing_dir(query)
        ans = gold[rid]["answer"]
        row = {"id": rid, "rule": rule, "conflict": rid in conf["numeric"]["ids"],
               "conflict_string": rid in conf["string"]["ids"],
               "filing_dir": str(fdir) if fdir else None, "question": list(q_key(query))}
        for mode, q, fd in (("query", query, None), ("filing", query, fdir), ("original", orig_q.get(rid), None)):
            if q is None:
                row[mode] = None
                continue
            row[mode] = mode_row(D.explain_material(D.load_material(q, fd)), ans)
        rows.append(row)
    return rows, conf, time.time() - t0


def report_practice(rows, conf):
    out = {"mode_labels": MODE_LABELS}
    lines = []
    P = lines.append
    cn, cs = conf["numeric"], conf["string"]
    cur_n = [r for r in rows if r["conflict"]]
    cur_s = [r for r in rows if r["conflict_string"]]
    out["conflicting_duplicates"] = {
        "original_release_numeric": {"cases": len(cn["ids"]), "groups": cn["groups"], "by_rule": cn["by_rule"]},
        "original_release_string": {"cases": len(cs["ids"]), "groups": cs["groups"], "by_rule": cs["by_rule"]},
        "curated_numeric": {"cases": len(cur_n), "by_rule": dict(Counter(r["rule"] for r in cur_n))},
        "curated_string": {"cases": len(cur_s), "by_rule": dict(Counter(r["rule"] for r in cur_s))},
        "string_only_ids": sorted(cs["ids"] - cn["ids"]),
        "0126_cases_in_conflict_groups": sum(1 for r in cur_n if r["rule"] == "DQC_US_0126"),
    }
    cd = out["conflicting_duplicates"]
    P("Conflicting duplicates (same CIK+concept+period, >=2 distinct gold pairs):")
    P(f"  original 332 release: string-level {cd['original_release_string']['cases']} cases in "
      f"{cd['original_release_string']['groups']} groups; numeric {cd['original_release_numeric']['cases']} cases in "
      f"{cd['original_release_numeric']['groups']} groups (string-only: {cd['string_only_ids']}, which differ only "
      f"by thousands separators)")
    P(f"  curated 330 inputs: numeric {cd['curated_numeric']['cases']} {cd['curated_numeric']['by_rule']}; "
      f"string {cd['curated_string']['cases']}.  0126 cases in conflict groups: "
      f"{cd['0126_cases_in_conflict_groups']} -> the non-conflicting 0126 numbers equal the 'all' numbers by "
      f"construction.")
    for mode in ("query", "filing", "original"):
        P(f"\n=== mode={mode}: {MODE_LABELS[mode]} ===")
        res = {}
        mrows = [r for r in rows if r.get(mode)]
        for subset_name, pred in (("all", lambda r: True), ("non_conflicting", lambda r: not r["conflict"])):
            sub = [r for r in mrows if pred(r)]
            c26 = [r for r in sub if r["rule"] == "DQC_US_0126"]
            hit = sum(1 for r in c26 if r[mode]["gold_hit"])
            one = sum(1 for r in c26 if r[mode]["n"] == 1)
            one_hit = sum(1 for r in c26 if r[mode]["n"] == 1 and r[mode]["gold_hit"])
            dist = Counter(r[mode]["n"] for r in c26)
            block = {"0126_cases": len(c26), "gold_among_findings": hit, "exactly_one": one,
                     "exactly_one_and_gold": one_hit, "findings_per_case": dict(sorted(dist.items()))}
            P(f"[{subset_name}] DQC_US_0126: gold among findings {pct(hit, len(c26))}; exactly one finding "
              f"{pct(one, len(c26))}; exactly one AND it is gold {pct(one_hit, len(c26))}; "
              f"findings/case {dict(sorted(dist.items()))}")
            for other in ("DQC_US_0015", "DQC_US_0117"):
                co = [r for r in sub if r["rule"] == other]
                fires = [r for r in co if r[mode]["n"] > 0]
                coinc = [r for r in fires if r[mode]["gold_hit"]]
                ext_c = [r for r in fires if r[mode]["gold_ext_hit"]]
                gates = Counter(r[mode]["gate"] for r in co)
                block[other] = {"cases": len(co), "fires": len(fires), "fires_ids": [r["id"] for r in fires],
                                "finding_equals_gold_pair": len(coinc),
                                "finding_extracted_equals_gold_extracted": len(ext_c),
                                "gates": dict(gates.most_common())}
                P(f"[{subset_name}] {other}: 0126 fires on {pct(len(fires), len(co))} "
                  f"(finding == gold pair on {len(coinc)}, extracted == gold extracted on {len(ext_c)}); "
                  f"gates {dict(gates.most_common())}")
            fp = sum(1 for r in sub if r["rule"] != "DQC_US_0126" and r[mode]["n"] > 0)
            fn = len(c26) - sum(1 for r in c26 if r[mode]["n"] > 0)
            block["as_classifier"] = {"tp_gold_found": hit, "fp_other_rule_fires": fp, "fn_0126_not_firing": fn}
            P(f"[{subset_name}] as a 0126 detector: 0126 cases firing {len(c26) - fn}/{len(c26)}, "
              f"other-rule cases firing {fp}/{len(sub) - len(c26)}")
            res[subset_name] = block
        c26 = [r for r in mrows if r["rule"] == "DQC_US_0126"]
        alt = Counter()
        for r in c26:
            for k, v in (r[mode]["alt_ok"] or {}).items():
                alt[(k, v)] += 1
        res["sensitivity_on_gold_findings"] = {f"{k}={v}": n for (k, v), n in sorted(alt.items())}
        res["sensitivity_on_gold_findings_ids"] = {
            k: [r["id"] for r in c26 if r[mode]["alt_ok"] and not r[mode]["alt_ok"][k]]
            for k in ("min_child_decimals", "all_children_counted")}
        res["fs_decimals_tied_0126"] = sum(1 for r in c26 if r[mode]["fs_tied"])
        res["multi_value_children_0126"] = sum(1 for r in c26 if r[mode]["multi_value_children"])
        res["released_role_status_0126"] = dict(Counter(r[mode]["released_role_status"] for r in c26))
        res["released_role_def_source_0126"] = dict(Counter(r[mode]["released_role_def_source"] for r in c26))
        res["role_def_mode_all"] = dict(Counter(r[mode]["role_def_mode"] for r in mrows))
        res["instance_parse_anomalies"] = [r["id"] for r in mrows if not r[mode]["instance_ok"]]
        res["released_role_status_all"] = {
            f"{k[0]}|{k[1]}": v
            for k, v in Counter((r["rule"], r[mode]["released_role_status"]) for r in mrows).most_common()}
        P(f"gold finding still fires under alternative readings: {res['sensitivity_on_gold_findings']} "
          f"(not under: {res['sensitivity_on_gold_findings_ids']})")
        P(f"fs_decimals ties on 0126 cases: {res['fs_decimals_tied_0126']}; multi-value children: "
          f"{res['multi_value_children_0126']}; released-role status on 0126: {res['released_role_status_0126']}; "
          f"role definition source: {res['released_role_def_source_0126']}; role-definition mode (all cases): "
          f"{res['role_def_mode_all']}; instance parse anomalies: {len(res['instance_parse_anomalies'])}")
        P(f"released-role status by rule: {res['released_role_status_all']}")
        misses = [r["id"] for r in c26 if not r[mode]["gold_hit"]]
        if misses:
            P(f"0126 misses: {misses}")
        res["0126_misses"] = misses
        out[mode] = res
    return out, lines


def run_dev_000273():
    """The 0126 case removed from curation (gold 320002 = digit typo of 32002)."""
    gold = {r["id"]: r["answer"] for r in jl(ORIG_GOLD)}
    q = next(r["query"] for r in jl(ORIG_INPUTS) if r["id"] == "DEV_000273")
    fdir = D.find_filing_dir(q)
    out = {"gold": gold["DEV_000273"], "filing_dir": str(fdir) if fdir else None}
    for mode, fd in (("filing", fdir), ("original", None)):
        ex = D.explain_material(D.load_material(q, fd))
        out[mode] = {"gate": gate_label(ex),
                     "findings": [{k: f[k] for k in ("parent_value", "children_sum", "children", "role")}
                                  for f in ex.get("findings", [])]}
    out["findings"] = out["filing"]["findings"]
    return out


# --------------------------------------------------------------------------- #
# Filing level (practice): does the rule fire ONLY where the generator asked?
# --------------------------------------------------------------------------- #


def run_filing_level():
    """Original 332-case release (ids, dqc_id, gold, query) grouped by filing directory."""
    by_dir = defaultdict(list)
    for r in jl(ORIG_GOLD):
        fdir = D.find_filing_dir(r["query"])
        by_dir[str(fdir) if fdir else None].append(r)
    res = {"filings_with_0126_case": 0, "findings": 0, "findings_matching_released_0126": 0,
           "findings_matching_released_0126_and_gold_pair": 0, "findings_matching_released_other_rule": [],
           "findings_matching_no_released_case": [], "released_0126_cases": 0, "released_0126_found": 0,
           "released_0126_missed": [], "rows": []}
    info = {"filings_without_0126_case": 0, "with_findings": 0, "findings": 0, "examples": []}
    for d, cases in sorted(by_dir.items(), key=lambda kv: str(kv[0])):
        if d is None:
            continue
        q0 = cases[0]["query"]
        found = D.all_findings_0126(q0, d)
        released = defaultdict(list)
        for c in cases:
            released[q_key(c["query"])].append(c)
        has26 = any(c["dqc_id"] == "DQC_US_0126" for c in cases)
        if not has26:
            info["filings_without_0126_case"] += 1
            if found:
                info["with_findings"] += 1
                info["findings"] += len(found)
                info["examples"].append({"filing": Path(d).name, "findings": [
                    [f["concept"], f["period"], f["parent_value"], f["children_sum"],
                     [c["id"] + ":" + c["dqc_id"] for c in released.get(finding_key(f), [])]] for f in found]})
            continue
        res["filings_with_0126_case"] += 1
        res["findings"] += len(found)
        hit_ids = set()
        for f in found:
            rel = released.get(finding_key(f), [])
            r26 = [c for c in rel if c["dqc_id"] == "DQC_US_0126"]
            if r26:
                res["findings_matching_released_0126"] += 1
                hit_ids.update(c["id"] for c in r26)
                if any(N(c["answer"]["extracted_value"]) == N(f["parent_value"]) and
                       N(c["answer"]["calculated_value"]) == N(f["children_sum"]) for c in r26):
                    res["findings_matching_released_0126_and_gold_pair"] += 1
            elif rel:
                res["findings_matching_released_other_rule"].append(
                    [Path(d).name, f["concept"], [c["id"] + ":" + c["dqc_id"] for c in rel]])
            else:
                res["findings_matching_no_released_case"].append(
                    [Path(d).name, f["concept"], f["period"], f["parent_value"], f["children_sum"]])
        c26 = [c for c in cases if c["dqc_id"] == "DQC_US_0126"]
        res["released_0126_cases"] += len(c26)
        res["released_0126_found"] += sum(1 for c in c26 if c["id"] in hit_ids)
        res["released_0126_missed"] += [c["id"] for c in c26 if c["id"] not in hit_ids]
        res["rows"].append({"filing": Path(d).name, "findings": len(found), "released_0126": len(c26),
                            "found": sum(1 for c in c26 if c["id"] in hit_ids)})
    res["precision"] = f"{res['findings_matching_released_0126']}/{res['findings']}"
    res["recall"] = f"{res['released_0126_found']}/{res['released_0126_cases']}"
    # how the generator sampled: released rules per filing (explains unreleased findings in other filings)
    info["released_rule_mix_per_filing"] = {
        "+".join(k): v for k, v in Counter(tuple(sorted({c["dqc_id"] for c in cs}))
                                           for d, cs in by_dir.items() if d is not None).most_common()}
    return res, info


# --------------------------------------------------------------------------- #
# Released calculation network vs the complete filing's
# --------------------------------------------------------------------------- #

_RAW_CALC_CACHE = {}


def raw_calc_networks(fdir):
    key = str(fdir)
    if key not in _RAW_CALC_CACHE:
        files = D.dts_files(fdir)
        text = "\n".join(t for t in [D._read(p) for p in files["linkbases"] + files["xsd"]] if t)
        _RAW_CALC_CACHE[key] = D.calculation_networks(text)
    return _RAW_CALC_CACHE[key]


def arcs_of(net):
    return {(p, c, str(w)) for p, lst in net.children.items() for c, w in lst}


def released_vs_raw_calc(query, fdir):
    sec = X.split_sections(query)
    rel = D.calculation_networks(sec.get("calculation", ""))
    if not rel or fdir is None:
        return None
    raw = raw_calc_networks(fdir)
    diffs = []
    for role, net in rel.items():
        rn = raw.get(role)
        if rn is None:
            diffs.append([role, "role_missing_in_filing"])
        elif arcs_of(net) != arcs_of(rn):
            diffs.append([role, f"released_only={len(arcs_of(net) - arcs_of(rn))} "
                                f"filing_only={len(arcs_of(rn) - arcs_of(net))}"])
    return {"equal": not diffs, "roles": len(rel), "diffs": diffs}


# --------------------------------------------------------------------------- #
# Dev
# --------------------------------------------------------------------------- #


def _expand(mat, net, child, align, depth=0, seen=()):
    """The older task3_solver's fallback: a child without a fact is replaced by the sum of its own
    calculation children (first aligned fact each, recursively).  NOT XULE -- evidence only."""
    if depth > 4 or child in seen or child not in net.children:
        return None
    tot, found = Decimal(0), 0
    for c, w in net.children[child]:
        cs = [f for f in mat.nondim.get(c, []) if f.alignment == align]
        v = cs[0].value if cs else _expand(mat, net, c, align, depth + 1, seen + (child,))
        if v is not None:
            tot, found = tot + w * v, found + 1
    return tot if found else None


def expansion_delta(mat, ev):
    net, extra, k = mat.calc[ev.role], Decimal(0), 0
    for c, w, f in ev.children:
        if f is None:
            v = _expand(mat, net, c, ev.parent_fact.alignment)
            if v is not None:
                extra, k = extra + w * v, k + 1
    if not k:
        return None
    new = ev.addend + extra
    fires = D.tolerance_for_decimals(ev.parent_fact.value, ev.parent_fact.decimals, new, None,
                                     ev.n_addends + k + 1)[0]
    return {"expanded_children": k, "expanded_sum": D._plain(new), "fires_if_expanded": fires}


def sibling_outcome(query, fdir, mods):
    out = {}
    for name, fn in mods:
        try:
            fs = fn(query, fdir)
        except Exception as e:  # sibling modules are developed in parallel; never let them stop this run
            out[name] = {"error": repr(e)[:200]}
            continue
        pairs = []
        for f in fs:
            e = f.get("extracted", f.get("total"))
            c = f.get("calculated", f.get("member_sum"))
            pairs.append([str(e), str(c)])
        out[name] = {"n": len(fs), "pairs": pairs}
    return out


def run_dev(limit=None, siblings=True):
    best = {r["id"]: r for r in jl(BEST_DEV)}
    base = {r["id"]: r for r in jl(BASE_DETAIL)}
    changes = json.load(open(CHANGES))
    rule_of = {i: (changes[i]["rule"] if i in changes else base[i]["rule"]) for i in base}
    mods = []
    if siblings:
        from claude_agent.dqc import dqc_0015 as D15, dqc_0117 as D17
        mods = [("DQC_US_0015", D15.findings_0015), ("DQC_US_0117", D17.findings_0117)]
    rows = []
    filing_level = {"filings": 0, "findings": 0, "matching_a_dev_question": 0}
    seen_dirs = set()
    dev_questions = defaultdict(set)
    inputs = list(jl(DEV_INPUTS))
    for r in inputs:
        fdir = D.find_filing_dir(r["query"])
        dev_questions[str(fdir)].add(q_key(r["query"]))
    t0 = time.time()
    for n, r in enumerate(inputs):
        if limit and n >= limit:
            break
        rid, query = r["id"], r["query"]
        fdir = D.find_filing_dir(query)
        row = {"id": rid, "filing_dir": fdir.name if fdir else None, "base_rule": rule_of.get(rid),
               "best": [best[rid]["extracted_value"], best[rid]["calculated_value"]] if rid in best else None,
               "question": list(q_key(query))}
        for mode, fd in (("query", None), ("filing", fdir)):
            if mode == "filing" and fd is None:
                row[mode] = None
                continue
            mat = D.load_material(query, fd)
            ex = D.explain_material(mat)
            mr = mode_row(ex)
            if mode == "filing":
                q = mat.question
                evs, _ = D.evaluate(mat, concept=q.concept)
                mr["expansion"] = [expansion_delta(mat, ev) for ev in evs
                                   if ev.fires and D._question_matches(ev, q)]
                mr["calc_released_vs_filing"] = released_vs_raw_calc(query, fd)
                if str(fd) not in seen_dirs:
                    seen_dirs.add(str(fd))
                    allf = D.all_findings_0126(query, fd, mat=mat)
                    filing_level["filings"] += 1
                    filing_level["findings"] += len(allf)
                    filing_level["matching_a_dev_question"] += sum(
                        1 for f in allf if finding_key(f) in dev_questions[str(fd)])
            row[mode] = mr
        if mods:
            row["siblings"] = sibling_outcome(query, fdir, mods)
        rows.append(row)
    return rows, filing_level, time.time() - t0


def classify_vs_upload(r, m):
    b = r["best"]
    bp = (N(b[0]), N(b[1])) if b else None
    pairs = [(N(p[0]), N(p[1])) for p in m["pairs"]]
    base26 = r["base_rule"] == "DQC_US_0126"
    if pairs and base26 and bp not in pairs:
        return "0126_value_differs"
    if pairs and not base26:
        return "0126_fires_but_upload_used_" + str(r["base_rule"])
    if not pairs and base26:
        return "upload_used_0126_but_rule_cannot_fire:" + str(m["gate"])
    return None


def report_dev(rows, filing_level):
    lines = []
    P = lines.append
    out = {"cases": len(rows), "mode_labels": {k: MODE_LABELS[k] for k in ("query", "filing")}}
    for mode in ("query", "filing"):
        rs = [r for r in rows if r.get(mode)]
        fires = [r for r in rs if r[mode]["n"] > 0]
        dist = Counter(r[mode]["n"] for r in rs)
        gates = Counter(r[mode]["gate"] for r in rs)
        c11 = sum(1 for r in fires if r[mode]["calc11"])
        tied = sum(1 for r in fires if r[mode]["fs_tied"])
        multi = [r["id"] for r in fires if r[mode]["multi_value_children"]]
        bad_inst = [r["id"] for r in rs if not r[mode]["instance_ok"]]
        srcs = Counter(f["role_definition_source"] for r in fires for f in r[mode]["findings"])
        agree = Counter()
        for r in rs:
            b = r["best"]
            bp = (N(b[0]), N(b[1])) if b else None
            pairs = [(N(p[0]), N(p[1])) for p in r[mode]["pairs"]]
            base26 = r["base_rule"] == "DQC_US_0126"
            if pairs:
                agree[("fires", "base=0126" if base26 else f"base={r['base_rule']}",
                       "best_pair_in_findings" if bp in pairs else "best_pair_differs")] += 1
            else:
                agree[("no_finding", "base=0126" if base26 else f"base={r['base_rule']}")] += 1
        # every fired case whose result depends on a reading the case material cannot show
        alt_dep = defaultdict(list)
        for r in fires:
            for fa in r[mode]["fires_alt"]:
                for k, v in fa.items():
                    if v is False:
                        alt_dep[k].append(r["id"])
        out[mode] = {"evaluated": len(rs), "fires": len(fires), "findings_per_case": dict(sorted(dist.items())),
                     "gates": dict(gates.most_common()), "fires_on_calc11_network": c11,
                     "fires_with_fs_decimals_tie": tied, "fires_with_multi_value_children": multi,
                     "instance_parse_anomalies": bad_inst,
                     "role_definition_source_of_findings": dict(srcs),
                     "fires_but_not_under_alternative_reading": {k: sorted(set(v)) for k, v in alt_dep.items()},
                     "agreement_with_best_upload": {"|".join(k): v for k, v in sorted(agree.items())}}
        P(f"\n=== dev mode={mode}: {MODE_LABELS[mode]}; evaluated {len(rs)} ===")
        P(f"0126 fires on {pct(len(fires), len(rs))}; findings/case {dict(sorted(dist.items()))}")
        P(f"gates: {dict(gates.most_common())}")
        P(f"fired cases relying on a calc-1.1 network: {c11}; with an fs_decimals tie: {tied}; with multi-value "
          f"children: {len(multi)}; role-definition source of findings: {dict(srcs)}; instance parse anomalies: "
          f"{len(bad_inst)}")
        P(f"fired, but would NOT fire under an alternative reading: "
          f"{ {k: sorted(set(v)) for k, v in alt_dep.items()} or 'none'}")
        P("agreement with best upload (94.12%): " + "; ".join(f"{'|'.join(k)}={v}" for k, v in sorted(agree.items())))
    both = [r for r in rows if r.get("query") and r.get("filing")]
    same = sum(1 for r in both if sorted(map(tuple, r["query"]["pairs"])) == sorted(map(tuple, r["filing"]["pairs"])))
    out["query_vs_filing_same_answer"] = f"{same}/{len(both)}"
    P(f"\nquery mode and filing mode give the same finding pairs on {same}/{len(both)} cases")
    # expansion (old solver) deltas on the faithful findings
    exp = [(r["id"], e) for r in rows if r.get("filing") for e in r["filing"].get("expansion", []) if e]
    out["expansion_changes"] = [{"id": i, **e} for i, e in exp]
    P(f"fired cases where the old solver's grandchild expansion changes the sum: {len(exp)}; would not fire "
      f"at all if expanded: {sorted(i for i, e in exp if not e['fires_if_expanded'])}")
    # released calc network == complete network
    cmp_ = [r["filing"]["calc_released_vs_filing"] for r in rows if r.get("filing") and
            r["filing"].get("calc_released_vs_filing")]
    eq = sum(1 for c in cmp_ if c["equal"])
    out["released_calc_equals_filing_calc"] = f"{eq}/{len(cmp_)}"
    out["released_calc_differs_ids"] = [r["id"] for r in rows if r.get("filing") and
                                        r["filing"].get("calc_released_vs_filing") and
                                        not r["filing"]["calc_released_vs_filing"]["equal"]]
    P(f"released calculation network == complete filing network: {eq}/{len(cmp_)} cases with a released network")
    out["filing_level"] = filing_level
    P(f"filing level: {filing_level['findings']} fired findings in {filing_level['filings']} dev filings, "
      f"{filing_level['matching_a_dev_question']} of them are a dev question (the rest may be test questions "
      f"or unsampled findings -- information only)")
    # sibling partition
    if rows and "siblings" in rows[0]:
        part = Counter()
        none_ids = []
        for r in rows:
            m = r.get("filing") or r.get("query")
            k = (m["n"] > 0, r["siblings"].get("DQC_US_0015", {}).get("n", 0) > 0,
                 r["siblings"].get("DQC_US_0117", {}).get("n", 0) > 0)
            part[k] += 1
            if not any(k):
                none_ids.append(r["id"])
        lab = {k: "+".join(n for n, b in zip(("0126", "0015", "0117"), k) if b) or "none" for k in part}
        out["faithful_module_partition"] = {lab[k]: v for k, v in sorted(part.items(), key=lambda kv: -kv[1])}
        out["no_faithful_module_fires"] = none_ids
        P(f"faithful modules that fire per dev case (filing mode): {out['faithful_module_partition']}; "
          f"none: {none_ids}")
        # Practice releases (almost) one rule per filing (see practice_filing_level_info).  Dev filings
        # whose questions are explained by different rules, or by none, are listed for review.
        by_f = defaultdict(list)
        for r in rows:
            m = r.get("filing") or r.get("query")
            fired = [n for n, b in (("0126", m["n"] > 0),
                                    ("0015", r["siblings"].get("DQC_US_0015", {}).get("n", 0) > 0),
                                    ("0117", r["siblings"].get("DQC_US_0117", {}).get("n", 0) > 0)) if b]
            by_f[r["filing_dir"]].append((r["id"], "+".join(fired) or "none"))
        mixed = {f: v for f, v in by_f.items() if len({x[1] for x in v}) > 1}
        out["dev_filings"] = len(by_f)
        out["dev_filings_with_mixed_rule_explanations"] = mixed
        P(f"dev filings: {len(by_f)}; filings whose questions are explained by different rules (or none): "
          f"{len(mixed)}")
        for f, v in sorted(mixed.items()):
            P(f"  {f}: {v}")
    # disagreements with the best upload, with every evidence column
    dis = []
    for r in rows:
        m = r.get("filing") or r.get("query")
        kind = classify_vs_upload(r, m)
        if not kind:
            continue
        sib = r.get("siblings", {})
        dis.append({"id": r["id"], "kind": kind, "faithful_0126": m["pairs"], "best_upload": r["best"],
                    "base_rule": r["base_rule"], "gate": m["gate"], "calc11": m["calc11"],
                    "fires_alt": m["fires_alt"], "expansion": m.get("expansion"),
                    "dqc_0015": sib.get("DQC_US_0015"), "dqc_0117": sib.get("DQC_US_0117"),
                    "only_0126_fires": bool(m["pairs"]) and not any(
                        (sib.get(k) or {}).get("n", 0) for k in ("DQC_US_0015", "DQC_US_0117"))})
    out["disagreements_with_best_upload"] = dis
    out["disagreement_kinds"] = dict(Counter(d["kind"].split(":")[0] for d in dis))
    P(f"\ncases where faithful 0126 disagrees with the best upload: {len(dis)} {out['disagreement_kinds']}")
    for d in dis:
        alt = [k for fa in d["fires_alt"] for k, v in fa.items() if v is False]
        exps = [e for e in (d["expansion"] or []) if e]
        sib = "; ".join(f"{k[-4:]}={(d[k] or {}).get('pairs', (d[k] or {}).get('error'))}"
                        for k in ("dqc_0015", "dqc_0117"))
        P(f"  {d['id']}  {d['kind']}  faithful={d['faithful_0126']}  upload={d['best_upload']}"
          f"{'  calc11' if d['calc11'] else ''}{'  alt-sensitive:' + ','.join(alt) if alt else ''}"
          f"{'  expanded=' + exps[0]['expanded_sum'] + (' (fires)' if exps[0]['fires_if_expanded'] else ' (silent)') if exps else ''}"
          f"  siblings: {sib}")
    return out, lines


# --------------------------------------------------------------------------- #
# Regression self-checks (parsing defects fixed on 2026-10-08)
# --------------------------------------------------------------------------- #

RAW_PRACTICE = ROOT / "task3_source_data/raw_filings"
RAW_RANKED = ROOT / "task3_source_data/ranked/raw_filings_ranked"


def self_checks():
    out = {}
    # 1. single-quoted (EDGARsuite) definition linkbase: 6 has-hypercube roles incl. the balance sheet
    p = RAW_RANKED / "0001131903-fccn-20250630/fccn-20250630_def.xml"
    h = D.hypercube_roles(D._read(p))
    bs = any(r.endswith("idr_StatementCondensedConsolidatedBalanceSheets") for r in h)
    out["single_quoted_cubes_fccn"] = {"roles": len(h), "balance_sheet": bs, "pass": len(h) == 6 and bs}
    # 2. ThunderDome schema: <link:definition xmlns="..."> must parse
    p = RAW_PRACTICE / "10q-ensv-20220930/ensv-20220930.xsd"
    t = D._read(p)
    defs = D.parse_role_definitions(t)
    n_rt = len(re.findall(r"<(?:\w+:)?roleType\b", t))
    out["thunderdome_role_definitions_ensv"] = {"parsed": len(defs), "roleTypes": n_rt,
                                                "pass": n_rt > 0 and len(defs) == n_rt}
    # 3. linkbases embedded in the .xsd (no separate _cal/_pre/_def files)
    mat = D.load_material("", RAW_PRACTICE / "10k-glxz-20231231")
    out["embedded_linkbases_glxz"] = {"calc_networks": len(mat.calc), "pres_networks": len(mat.pres_roles),
                                      "cube_roles": len(mat.cubes), "role_definitions": len(mat.role_defs),
                                      "pass": len(mat.calc) == 17 and len(mat.pres_roles) == 69}
    # 4. XULE duplicate elimination: consistent duplicates collapse to the more precise fact,
    #    inconsistent ones stay
    F = D.FactRec

    def mk(v, d, pos):
        return F("us-gaap:X", Decimal(v), d, (None, None, "2025-06-30"), "iso4217:USD", "1", "c", None, pos)

    idx, n = D.xule_dedup({"us-gaap:X": [mk("1000000", -6.0, 1), mk("1234000", -3.0, 2), mk("1234000", -3.0, 3),
                                         mk("1235000", -3.0, 4)]})
    got = [(str(f.value), f.decimals) for f in idx["us-gaap:X"]]
    out["xule_dedup"] = {"kept": got, "dropped": n,
                         "pass": got == [("1234000", -3.0), ("1235000", -3.0)] and n == 2}
    # 5. L53 bare factset: every fact at $fs_decimals is an addend; otherwise one fact
    c = [mk("5", 0.0, 1), mk("6", 0.0, 2), mk("7", -3.0, 3)]
    eq = [str(f.value) for f in D._child_facts(c, 0.0)]
    ge = [str(f.value) for f in D._child_facts(c, -6.0)]
    out["bare_factset_children"] = {"eq": eq, "ge": ge, "pass": eq == ["5", "6"] and ge == ["5"]}
    out["all_pass"] = all(v["pass"] for v in out.values() if isinstance(v, dict))
    return out


# --------------------------------------------------------------------------- #
# Before/after
# --------------------------------------------------------------------------- #


def compare_before(before_path, result):
    old = json.load(open(before_path))
    lines = []
    P = lines.append
    out = {"before_file": str(before_path), "practice": {}, "dev": {}}
    orow = {r["id"]: r for r in old.get("practice_rows", [])}
    nrow = {r["id"]: r for r in result.get("practice_rows", [])}
    P(f"\n=== before/after vs {before_path} ===")
    for mode in ("query", "filing"):
        ch = []
        for i, nr in nrow.items():
            o = (orow.get(i) or {}).get(mode)
            n = nr.get(mode)
            if not o or not n:
                continue
            ov = (o.get("n"), o.get("gold_hit"), o.get("gate"))
            nv = (n.get("n"), n.get("gold_hit"), n.get("gate"))
            if ov != nv:
                ch.append([i, ov, nv])
        out["practice"][mode] = ch
        for lab, rws in (("before", old.get("practice_rows", [])), ("after", result.get("practice_rows", []))):
            c26 = [r for r in rws if r["rule"] == "DQC_US_0126" and r.get(mode)]
            oth = [r for r in rws if r["rule"] != "DQC_US_0126" and r.get(mode)]
            P(f"practice {mode} {lab}: 0126 gold among findings {sum(r[mode]['gold_hit'] for r in c26)}/{len(c26)}, "
              f"exactly one {sum(r[mode]['n'] == 1 for r in c26)}/{len(c26)}, other-rule fires "
              f"{sum(r[mode]['n'] > 0 for r in oth)}/{len(oth)}")
        P(f"practice {mode}: per-case changes (n, gold_hit, gate): {len(ch)} {ch[:10]}")
    odev = {r["id"]: r for r in old.get("dev_rows", [])}
    ndev = {r["id"]: r for r in result.get("dev_rows", [])}
    for mode in ("query", "filing"):
        ch_pairs, ch_gate = [], []
        for i, nr in ndev.items():
            o = (odev.get(i) or {}).get(mode)
            n = nr.get(mode)
            if not o or not n:
                continue
            op = sorted((str(N(a)), str(N(b))) for a, b in o.get("pairs", []))
            np_ = sorted((str(N(a)), str(N(b))) for a, b in n.get("pairs", []))
            if op != np_:
                ch_pairs.append([i, op, np_])
            if o.get("gate") != n.get("gate"):
                ch_gate.append([i, o.get("gate"), n.get("gate")])
        out["dev"][mode] = {"pair_changes": ch_pairs, "gate_changes": ch_gate}
        ofires = sum(1 for r in odev.values() if (r.get(mode) or {}).get("n"))
        nfires = sum(1 for r in ndev.values() if (r.get(mode) or {}).get("n"))
        P(f"dev {mode}: fires before {ofires}/{len(odev)}, after {nfires}/{len(ndev)}; answer-pair changes "
          f"{len(ch_pairs)} {ch_pairs[:10]}; gate changes {len(ch_gate)} {ch_gate[:10]}")
    od = {d["id"]: d for d in (old.get("dev") or {}).get("disagreements_with_best_upload", [])}
    nd = {d["id"]: d for d in (result.get("dev") or {}).get("disagreements_with_best_upload", [])}
    out["dev"]["disagreements"] = {"before": sorted(od), "after": sorted(nd),
                                   "added": sorted(set(nd) - set(od)), "removed": sorted(set(od) - set(nd))}
    P(f"dev disagreements with the best upload: before {len(od)}, after {len(nd)}; added "
      f"{sorted(set(nd) - set(od))}, removed {sorted(set(od) - set(nd))}")
    return out, lines


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip-dev", action="store_true")
    ap.add_argument("--dev-limit", type=int, default=None)
    ap.add_argument("--no-siblings", action="store_true", help="skip the dqc_0015/dqc_0117 evidence columns")
    ap.add_argument("--before", default=None, help="earlier results JSON of this script for a before/after diff")
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args(argv)

    t0 = time.time()
    checks = self_checks()
    print(f"regression self-checks: {'ALL PASS' if checks['all_pass'] else 'FAILURES'} "
          f"{ {k: v for k, v in checks.items() if k != 'all_pass'} }\n")
    rows, conf, secs = run_practice()
    prac, lines = report_practice(rows, conf)
    print(f"practice: {len(rows)} cases in {secs:.1f}s")
    print("\n".join(lines))

    fl, fl_info = run_filing_level()
    print(f"\n=== practice FILING LEVEL (mode=filing): all_findings_0126 in the {fl['filings_with_0126_case']} "
          f"filings holding a released 0126 case ===")
    print(f"findings {fl['findings']}; each a released 0126 question: {fl['findings_matching_released_0126']} "
          f"(precision {fl['precision']}), of which gold pair equal {fl['findings_matching_released_0126_and_gold_pair']}; "
          f"released 0126 cases found {fl['recall']} (missed {fl['released_0126_missed']}); findings on a released "
          f"other-rule question {fl['findings_matching_released_other_rule']}; findings on no released question "
          f"{fl['findings_matching_no_released_case']}")
    print(f"information: released rules per practice filing {fl_info['released_rule_mix_per_filing']} -- the "
          f"generator sampled (almost) one rule per filing, so 0126 findings in a filing released for another rule "
          f"are not evidence of over-firing.  {fl_info['filings_without_0126_case']} filings hold only 0015/0117 "
          f"cases; {fl_info['with_findings']} of them have 0126 findings ({fl_info['findings']} in total; listed in "
          f"the JSON)")

    pcmp = [r for r in (released_vs_raw_calc(x["query"], D.find_filing_dir(x["query"])) for x in jl(PRACTICE_INPUTS))
            if r]
    peq = sum(1 for c in pcmp if c["equal"])
    print(f"\npractice: released calculation network == complete filing network: {peq}/{len(pcmp)} cases with a "
          f"released network")

    d273 = run_dev_000273()
    print(f"\nDEV_000273 (excluded bad gold {d273['gold']}): filing mode "
          f"{[(f['parent_value'], f['children_sum']) for f in d273['filing']['findings']]}; original release alone: "
          f"gate {d273['original']['gate']}")

    result = {"provenance": {"dqc_0126_md5": md5(D.__file__), "run_at": time.strftime("%Y-%m-%d %H:%M:%S")},
              "self_checks": checks, "practice": prac, "practice_filing_level": fl, "practice_filing_level_info": fl_info,
              "practice_released_calc_equals_filing_calc": f"{peq}/{len(pcmp)}",
              "practice_rows": rows, "dev_000273": d273, "approximations": list(D.APPROXIMATIONS)}
    if not a.skip_dev:
        drows, dfl, dsecs = run_dev(a.dev_limit, siblings=not a.no_siblings)
        dev, dlines = report_dev(drows, dfl)
        print(f"\ndev: {len(drows)} cases in {dsecs:.1f}s")
        print("\n".join(dlines))
        result["dev"] = dev
        result["dev_rows"] = drows
        if not a.no_siblings:
            from claude_agent.dqc import dqc_0015 as D15, dqc_0117 as D17
            result["provenance"].update(dqc_0015_md5=md5(D15.__file__), dqc_0117_md5=md5(D17.__file__))
    if a.before:
        cmp_out, clines = compare_before(a.before, result)
        print("\n".join(clines))
        result["before_after"] = cmp_out
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(result, fh, indent=1, default=str)
    print(f"\nwrote {a.out} ({time.time() - t0:.0f}s)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
