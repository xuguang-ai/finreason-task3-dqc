#!/usr/bin/env python3
"""Validate claude_agent/dqc/dqc_0117.py against the practice gold.

    python3 validate_0117.py                         # all configurations on practice
    python3 validate_0117.py --config 2026 --misses
    python3 validate_0117.py --dev                   # + the 680 dev cases (no gold exists)
    python3 validate_0117.py --dev --compare validate_0117_report_prev.json

Practice basis
--------------
PRIMARY: the 330 curated cases (task3_source_data/curated/public_dev_curated.jsonl;
0117: 119).  The original public file has 332 cases; the two the curation
dropped, DEV_000117 (0117, a Southern Co. minority message) and DEV_000273
(0126), are reported separately ("extras"); on the 330 shared cases the
values and rule labels are identical.  Input text is dsh/task3_inputs.jsonl
(released linkbases + complete Instance) for the 330; the extras use their
released query and the complete filing.  Every case is solved with its complete
filing under task3_source_data/raw_filings/.

Conflicting duplicates (same CIK + concept + period, more than one distinct
gold) are 46 curated cases (0015: 32, 0117: 14, all Southern Co.); 47 of the
332.  No key (CIK / filing x concept x period [x rule]) gives 49.

Configurations
--------------
"2026" is the source and the module default.  "auto" (LEGACY for us-gaap <=
2022) and "legacy" were FITTED on the 46 practice 0117 cases of the 2021/2022
taxonomies: their numbers on those cases are in-sample, not estimates.  Dev
and test contain no us-gaap <= 2022 filing, so "auto" = "2026" there.

Evidence kinds (kept apart in the output)
-----------------------------------------
* per case: for the questioned concept and period, does the rule fire, is the
  gold pair (extracted = total, calculated = member_sum) among the findings,
  is it the only one.
* set level: per filing, the set of 9574 findings over ALL concepts and periods
  versus the set of 0117 golds of that filing.  This ASSUMES the dataset
  holds every 0117 finding of each filing -- an untested assumption; a
  finding outside the gold set may be a real DQC message the dataset did not
  sample.  Guards that change nothing per case (e.g. the notes guard on
  2023+) are supported by set-level evidence only.
* structure: which kind of role each case's released linkbase sections are
  scoped to (statement cube with a target axis, other statement cube, notes,
  parenthetical, no cube), by gold rule.  0117 can only report in a statement
  cube with a target axis; DQC_US_0126 skips every statement-cube role.
"""
from __future__ import annotations

import argparse
import collections
import dataclasses
import json
import re
import sys
import time
import traceback
from decimal import Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent  # /Users/xai/Desktop/FinReason
sys.path.insert(0, str(ROOT / "claude-agent-sdk-benchmark"))

from claude_agent import task3_xbrl as X  # noqa: E402
from claude_agent.dqc import dqc_0117 as D  # noqa: E402

COMPLETE_INPUTS = ROOT / "dsh/task3_inputs.jsonl"
RELEASED_INPUTS = ROOT / "task3_source_data/finmr_public_dev/public_dev_inputs.jsonl"
ORIGINAL_GOLD = ROOT / "task3_source_data/finmr_public_dev/public_dev.jsonl"
CURATED_GOLD = ROOT / "task3_source_data/curated/public_dev_curated.jsonl"
PRACTICE_MAP = ROOT / "task3_source_data/finmr_to_filing_mapping.json"
PRACTICE_FILINGS = ROOT / "task3_source_data/raw_filings"
DEV_INPUTS = ROOT / "task3_source_data/ranked/development_inputs_hybrid_v0928.jsonl"
DEV_FILINGS = ROOT / "task3_source_data/ranked/raw_filings_ranked"

O = D.Options
#: name -> (options or None, era).  Options override era.
CONFIGS = {
    "2026": (D.FAITHFUL, "2026"),  # the source = module default
    "auto": (None, "auto"),  # IN-SAMPLE: LEGACY for us-gaap <= 2022, 2026 otherwise
    "legacy": (D.LEGACY, "legacy"),  # IN-SAMPLE
    "2026_subtotal_off": (O(subtotal_guard="off", label="x"), "-"),
    "2026_subtotal_any": (O(subtotal_guard="any", label="x"), "-"),
    "2026_subtotal_strict": (O(subtotal_guard="strict", label="x"), "-"),
    "2026_no_notes": (O(notes_guard=False, label="x"), "-"),
    "2026_no_paren": (O(parenthetical_guard=False, label="x"), "-"),
    "2026_no_rev": (O(revenue_exceptions=False, label="x"), "-"),
    "2026_no_period": (O(period_filter=False, label="x"), "-"),
    "2026_no_member_validity": (O(member_validity=False, label="x"), "-"),
    "legacy_no_period": (O(notes_guard=False, parenthetical_guard=False, revenue_exceptions=False,
                           period_filter=False, label="x"), "-"),
    "legacy_subtotal_strict": (O(notes_guard=False, parenthetical_guard=False, revenue_exceptions=False,
                                 subtotal_guard="strict", label="x"), "-"),
}
IN_SAMPLE = {"auto", "legacy", "legacy_no_period", "legacy_subtotal_strict"}
CIK_RE = re.compile(r'<(?:xbrli:)?identifier[^>]*scheme="http://www\.sec\.gov/CIK"[^>]*>\s*(\d+)\s*<')

ASSUMPTIONS = [
    "Practice basis: curated 330 (0117: 119); DEV_000117 and DEV_000273 (original-only) reported as extras.",
    "auto / legacy* configurations were fitted on the 46 us-gaap<=2022 practice 0117 cases: in-sample there.",
    "Set level assumes the dataset holds every 0117 finding of each filing (untested).",
    "Dev has no gold; dev numbers are firing statistics and structure only.",
]


def num(v):
    if v is None:
        return None
    try:
        return Decimal(str(v).replace(",", "").strip())
    except InvalidOperation:
        return None


def _conflicts(cases):
    groups = collections.defaultdict(set)
    for c in cases:
        groups[(c["cik"], c["concept"], c["period"])].add((c["ge"], c["gc"]))
    return {c["id"] for c in cases if len(groups[(c["cik"], c["concept"], c["period"])]) > 1}


def load_practice():
    original = {json.loads(l)["id"]: json.loads(l) for l in ORIGINAL_GOLD.open()}
    curated = {json.loads(l)["id"]: json.loads(l) for l in CURATED_GOLD.open()}
    mapping = json.loads(PRACTICE_MAP.read_text())
    queries = {}
    for line in RELEASED_INPUTS.open():
        r = json.loads(line)
        queries[r["id"]] = r["query"]
    for line in COMPLETE_INPUTS.open():  # complete Instance where available
        r = json.loads(line)
        queries[r["id"]] = r["query"]
    cases = []
    for cid, g0 in original.items():
        g = curated.get(cid, g0)
        q = queries[cid]
        fdir = PRACTICE_FILINGS / mapping[cid] if cid in mapping else D.locate_filing_dir(q, [PRACTICE_FILINGS])
        qq = X.parse_question(q)
        km = CIK_RE.search(q.split("##Instance document", 1)[-1])
        cases.append({
            "id": cid, "rule": g["dqc_id"], "query": q, "fdir": fdir, "filing": fdir.name,
            "cik": km.group(1).zfill(10) if km else None, "concept": qq.concept, "period": qq.period_key,
            "ge": num(g["answer"]["extracted_value"]), "gc": num(g["answer"]["calculated_value"]),
            "curated": cid in curated, "year": D.us_gaap_year(q),
        })
    conf_cur = _conflicts([c for c in cases if c["curated"]])
    conf_all = _conflicts(cases)
    for c in cases:
        c["conflict"] = c["id"] in (conf_cur if c["curated"] else conf_all)
        c["conflict_332"] = c["id"] in conf_all
    cases.sort(key=lambda c: (c["filing"], c["id"]))  # reuse per-filing caches
    return cases


def _call(query, fdir, opts, era, **kw):
    if opts is None:
        return D.findings_0117(query, fdir, era=era, **kw)
    return D.findings_0117(query, fdir, opts, **kw)


def run(cases, opts, era):
    rows = []
    for c in cases:
        try:
            fs = _call(c["query"], c["fdir"], opts, era)
            err = None
        except Exception as exc:  # noqa: BLE001
            fs, err = [], f"{type(exc).__name__}: {exc}"
            traceback.print_exc()
        pairs, rel = [], []
        for f in fs:
            p = (num(f["total"]), num(f["member_sum"]))
            if p not in pairs:
                pairs.append(p)
            if f["in_released_role"] and p not in rel:
                rel.append(p)
        gold = (c["ge"], c["gc"])
        rows.append({
            "id": c["id"], "rule": c["rule"], "conflict": c["conflict"], "curated": c["curated"],
            "filing": c["filing"], "year": c["year"], "era": fs[0]["era"] if fs else None,
            "fired": bool(fs), "n": len(pairs), "gold_in": gold in pairs, "only_gold": pairs == [gold],
            "n_rel": len(rel), "gold_in_rel": gold in rel,
            "gold": [str(gold[0]), str(gold[1])], "pairs": [[str(a), str(b)] for a, b in pairs], "err": err,
        })
    return rows


def summarize(rows, subset_pred):
    r17 = [r for r in rows if r["rule"] == "DQC_US_0117" and subset_pred(r)]
    r15 = [r for r in rows if r["rule"] == "DQC_US_0015" and subset_pred(r)]
    r26 = [r for r in rows if r["rule"] == "DQC_US_0126" and subset_pred(r)]
    dist = collections.Counter(min(r["n"], 3) for r in r17)
    return {
        "n_0117": len(r17),
        "fired": sum(r["fired"] for r in r17),
        "gold_among_findings": sum(r["gold_in"] for r in r17),
        "exactly_one_finding": sum(r["n"] == 1 for r in r17),
        "exactly_one_and_gold": sum(r["only_gold"] for r in r17),
        "findings_per_case": {("3+" if k == 3 else str(k)): v for k, v in sorted(dist.items())},
        "fires_on_0015": f"{sum(r['fired'] for r in r15)}/{len(r15)}",
        "fires_on_0126": f"{sum(r['fired'] for r in r26)}/{len(r26)}",
        "other_rule_gold_pair_among_findings": sum(r["gold_in"] for r in r15 + r26),
        "errors": sum(1 for r in r17 + r15 + r26 if r["err"]),
    }


def set_level(cases, opts, era, gold_pred):
    """Per filing: set of 9574 findings (all concepts/periods) vs the set of
    0117 golds of that filing (cases selected by ``gold_pred``)."""
    by_filing = collections.defaultdict(list)
    for c in cases:
        by_filing[c["filing"]].append(c)
    out = collections.defaultdict(lambda: {"filings": 0, "exact": 0, "gold": 0, "gold_found": 0, "extra": 0})
    detail = []
    for filing, cs in sorted(by_filing.items()):
        g17 = [c for c in cs if c["rule"] == "DQC_US_0117" and gold_pred(c)]
        if not g17:
            continue
        o = opts if opts is not None else D.options_for(cs[0]["query"], era)
        fl = D.load_filing(cs[0]["query"], cs[0]["fdir"])
        fk = {(f["concept"], (f["period"]["start"], f["period"]["end"], f["period"]["instant"]),
               num(f["total"]), num(f["member_sum"]))
              for f in D._all_findings(fl, o, None) if f["rule_element"] == "9574"}
        gk = {(c["concept"], c["period"], c["ge"], c["gc"]) for c in g17}
        eraname = "us-gaap<=2022" if (cs[0]["year"] or 9999) <= 2022 else "us-gaap>=2023"
        for k in (eraname, "all"):
            s = out[k]
            s["filings"] += 1
            s["exact"] += fk == gk
            s["gold"] += len(gk)
            s["gold_found"] += len(gk & fk)
            s["extra"] += len(fk - gk)
        if fk != gk:
            detail.append({"filing": filing, "missing_gold": len(gk - fk), "extra_findings": len(fk - gk)})
    return dict(out), detail


def role_class(query, fdir):
    """Kind of role the released linkbase sections are scoped to."""
    prof = D.released_role_profile(query, fdir)
    if any(p["statement_cube"] and p["target_axes"] for p in prof):
        k = "statement_cube_with_target_axis"
    elif any(p["statement_cube"] for p in prof):
        k = "statement_cube_no_target_axis"
    elif any(p["parenthetical_cube"] for p in prof):
        k = "parenthetical_cube"
    elif any(p["notes_cube"] for p in prof):
        k = "notes_cube"
    elif any("- Statement -" in (p["description"] or "") for p in prof):
        k = "statement_without_cube"
    else:
        k = "other_without_cube"
    return k, len(prof)


def structure(cases):
    tab = collections.Counter()
    for c in cases:
        k, n = role_class(c["query"], c["fdir"])
        c["role_class"], c["n_released_roles"] = k, n
        tab[(c["rule"], k, "single-role" if n == 1 else "multi-role")] += 1
    return tab


def _other_rule_fires(query, fdir):
    out = {}
    for rid in ("0015", "0126"):
        try:
            mod = __import__(f"claude_agent.dqc.dqc_{rid}", fromlist=["x"])
            out[rid] = len(getattr(mod, f"findings_{rid}")(query, filing_dir=fdir) or [])
        except Exception as exc:  # noqa: BLE001
            out[rid] = f"error {type(exc).__name__}"
    return out


def dev_stats(opts, era, with_fallbacks: bool):
    rows = []
    t0 = time.time()
    with DEV_INPUTS.open() as fh:
        for line in fh:
            r = json.loads(line)
            q = r["query"]
            fdir = D.locate_filing_dir(q, [DEV_FILINGS])
            try:
                fs = _call(q, fdir, opts, era)
                err = None
            except Exception as exc:  # noqa: BLE001
                fs, err = [], f"{type(exc).__name__}: {exc}"
            pairs = []
            for f in fs:
                p = (f["total"], f["member_sum"])
                if p not in pairs:
                    pairs.append(p)
            k, nroles = role_class(q, fdir)
            row = {"id": r["id"], "has_dir": fdir is not None, "n": len(pairs), "pairs": pairs, "err": err,
                   "year": D.us_gaap_year(q), "era": fs[0]["era"] if fs else None, "role_class": k,
                   "n_released_roles": nroles, "in_released_role": [f["in_released_role"] for f in fs],
                   "n_messages": [f["n_messages"] for f in fs],
                   "order_sensitive_606": any(f.get("exception_order_sensitive") for f in fs)}
            if with_fallbacks and not fs and k == "statement_cube_with_target_axis":
                o = opts if opts is not None else D.options_for(q, era)
                nn = D.findings_0117(q, fdir, dataclasses.replace(o, notes_guard=False, label="no-notes"))
                aa = [f for f in _call(q, fdir, opts, era, all_alignments=True) if f["rule_element"] == "10093"]
                if nn or aa:
                    row["fallback"] = {
                        "no_notes_9574": [(f["total"], f["member_sum"], D.local(f["axis"])) for f in nn],
                        "10093": [(f["total"], f["member_sum"], D.local(f["axis"]), D.local(f["sub_member"]),
                                   D.local(f["dim2"])) for f in aa],
                        "other_rules_fire": _other_rule_fires(q, fdir),
                    }
            rows.append(row)
    dist = collections.Counter(min(r["n"], 3) for r in rows)
    fired = [r for r in rows if r["n"]]
    return rows, {
        "cases": len(rows), "with_filing_dir": sum(r["has_dir"] for r in rows),
        "fires": len(fired),
        "findings_per_case": {("3+" if k == 3 else str(k)): v for k, v in sorted(dist.items())},
        "firing_findings_in_released_role": f"{sum(all(r['in_released_role']) for r in fired)}/{len(fired)}",
        "firing_role_class": dict(collections.Counter(r["role_class"] for r in fired)),
        "firing_n_messages_gt1": sum(any(m > 1 for m in r["n_messages"]) for r in fired),
        "order_sensitive_606": sum(r["order_sensitive_606"] for r in rows),
        "role_class_all": dict(collections.Counter(r["role_class"] for r in rows)),
        "us_gaap_years": dict(sorted(collections.Counter(r["year"] for r in rows).items(), key=lambda x: str(x[0]))),
        "fallback_candidates": sum(1 for r in rows if "fallback" in r),
        "errors": sum(1 for r in rows if r["err"]),
        "seconds": round(time.time() - t0, 1),
    }


def released_only(cases):
    """No filing directory: only the released sections.  ``assume`` = the old
    behaviour (a released role without roleType text counts as a statement)."""
    out = {}
    for era in ("2026", "auto"):
        for assume in (False, True):
            st = collections.Counter()
            for c in cases:
                if not c["curated"]:
                    continue
                try:
                    fs = D.findings_0117(c["query"], None, era=era, assume_released_statements=assume)
                except Exception:  # noqa: BLE001
                    fs = []
                pairs = {(num(f["total"]), num(f["member_sum"])) for f in fs}
                yr = ">=2023" if (c["year"] or 0) >= 2023 else "<=2022"
                if c["rule"] == "DQC_US_0117":
                    st["0117"] += 1
                    st["0117_fired"] += bool(fs)
                    st["0117_gold_among"] += (c["ge"], c["gc"]) in pairs
                    st[f"0117_{yr}"] += 1
                    st[f"0117_{yr}_gold_among"] += (c["ge"], c["gc"]) in pairs
                else:
                    st["other_rule_fired"] += bool(fs)
            out[f"era={era},assume_released_statements={assume}"] = dict(st)
    return out


def compare(report, old_path):
    """Per-case before/after against an earlier report (same config names)."""
    old = json.loads(Path(old_path).read_text())
    out = {}
    for name, rows in report["per_case"].items():
        if name not in old.get("per_case", {}):
            continue
        prev = {r["id"]: r for r in old["per_case"][name]}
        diffs = [{"id": r["id"], "rule": r["rule"], "before": prev[r["id"]]["pairs"], "after": r["pairs"]}
                 for r in rows if r["id"] in prev and prev[r["id"]]["pairs"] != r["pairs"]]
        out[name] = diffs
    dev_diffs = {}
    for name, d in report.get("dev", {}).items():
        oname = name if name in old.get("dev", {}) else ("auto" if "auto" in old.get("dev", {}) else None)
        if oname is None:
            continue
        prev = {r["id"]: r for r in old["dev"][oname]["per_case"]}
        dev_diffs[f"{oname}->{name}"] = [
            {"id": r["id"], "before": prev[r["id"]]["pairs"], "after": r["pairs"]}
            for r in d["per_case"] if r["id"] in prev and [list(p) for p in prev[r["id"]]["pairs"]] != [list(p) for p in r["pairs"]]]
    return out, dev_diffs


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", action="append", help="config name(s); default all")
    ap.add_argument("--misses", action="store_true", help="list 0117 cases whose gold is not among the findings")
    ap.add_argument("--dev", action="store_true", help="also run the 680 dev cases (no gold)")
    ap.add_argument("--dev-config", action="append", help="config(s) for --dev; default: 2026")
    ap.add_argument("--compare", help="earlier report to diff per case against")
    ap.add_argument("--released-only", action="store_true",
                    help="also measure the module without filing directories (released sections only)")
    ap.add_argument("--out", default=str(HERE / "validate_0117_report.json"))
    args = ap.parse_args(argv)
    names = args.config or list(CONFIGS)
    cases = load_practice()
    cur = [c for c in cases if c["curated"]]
    extras = [c for c in cases if not c["curated"]]
    n17 = [c for c in cur if c["rule"] == "DQC_US_0117"]
    conf_by_rule = collections.Counter(c["rule"] for c in cur if c["conflict"])
    print(f"practice: curated {len(cur)} cases (0117 {len(n17)}), extras {[c['id'] for c in extras]}; "
          f"conflicting duplicates (CIK+concept+period): curated {sum(c['conflict'] for c in cur)} {dict(conf_by_rule)}, "
          f"original 332: {sum(c['conflict_332'] for c in cases)}; no filing dir {sum(c['fdir'] is None for c in cases)}")
    print(f"curated 0117 cases by us-gaap year: {dict(sorted(collections.Counter(c['year'] for c in n17).items()))}")
    report = {"generated": time.strftime("%Y-%m-%d %H:%M"), "module": str(Path(D.__file__)),
              "assumptions": ASSUMPTIONS, "configs": {}, "per_case": {}, "set_level": {}}
    subsets = {
        "curated": lambda r: r["curated"],
        "curated_non_conflict": lambda r: r["curated"] and not r["conflict"],
        "curated_us-gaap<=2022": lambda r: r["curated"] and (r["year"] or 9999) <= 2022,
        "curated_us-gaap>=2023": lambda r: r["curated"] and (r["year"] or 0) >= 2023,
        "all_332": lambda r: True,
    }
    for name in names:
        opts, era = CONFIGS[name]
        t0 = time.time()
        rows = run(cases, opts, era)
        summ = {k: summarize(rows, p) for k, p in subsets.items()}
        sl_cur, det_cur = set_level(cases, opts, era, lambda c: c["curated"])
        sl_all, _ = set_level(cases, opts, era, lambda c: True)
        report["configs"][name] = {"in_sample": name in IN_SAMPLE, "per_case": summ,
                                   "set_level_curated": sl_cur, "set_level_332": sl_all,
                                   "extras": [{k: r[k] for k in ("id", "rule", "gold", "pairs", "gold_in")}
                                              for r in rows if not r["curated"]],
                                   "seconds": round(time.time() - t0, 1)}
        report["per_case"][name] = rows
        report["set_level"][name] = det_cur
        tag = "  [IN-SAMPLE on us-gaap<=2022]" if name in IN_SAMPLE else ""
        print(f"\n[{name}]{tag} ({round(time.time() - t0, 1)}s)")
        print("  per-case evidence (questioned concept/period):")
        for k, s in summ.items():
            print(f"    {k:22s} 0117 n={s['n_0117']:3d}: fired {s['fired']}, gold among {s['gold_among_findings']}, "
                  f"exactly-one {s['exactly_one_finding']} (=gold {s['exactly_one_and_gold']}), per-case "
                  f"{s['findings_per_case']} | fires on 0015 {s['fires_on_0015']}, 0126 {s['fires_on_0126']}, "
                  f"other-rule gold pair {s['other_rule_gold_pair_among_findings']}, errors {s['errors']}")
        for r in rows:
            if not r["curated"]:
                print(f"    extra {r['id']} ({r['rule']}): gold {r['gold']} findings {r['pairs']} -> gold among: {r['gold_in']}")
        print("  set-level evidence (assumes the dataset holds every 0117 finding of a filing):")
        for k, s in sl_cur.items():
            print(f"    curated {k:14s} filings exact {s['exact']}/{s['filings']}, gold found {s['gold_found']}/{s['gold']}, "
                  f"extra findings {s['extra']}")
        for k, s in sl_all.items():
            if k == "all":
                print(f"    332     {k:14s} filings exact {s['exact']}/{s['filings']}, gold found {s['gold_found']}/{s['gold']}, "
                      f"extra findings {s['extra']}")
        if det_cur:
            print(f"    mismatching filings (curated): {det_cur}")
        if args.misses:
            for r in rows:
                if r["rule"] == "DQC_US_0117" and not r["gold_in"]:
                    print(f"    MISS {r['id']} {r['filing']}{' [conflict]' if r['conflict'] else ''} gold={r['gold']} "
                          f"findings={r['pairs'][:4]}")
    # structure (independent of configuration)
    tab = structure(cases)
    report["structure_practice"] = {f"{r}|{k}|{s}": v for (r, k, s), v in sorted(tab.items())}
    print("\nstructure: released-role kind by gold rule (curated + extras)")
    for (r, k, s), v in sorted(tab.items()):
        print(f"    {r:12s} {k:34s} {s:12s} {v}")
    if args.released_only:
        ro = released_only(cases)
        report["released_only"] = ro
        print("\nreleased sections only (no filing directory), curated:")
        for k, v in ro.items():
            print(f"    {k}: {v}")
    if args.dev:
        report["dev"] = {}
        for name in (args.dev_config or ["2026"]):
            opts, era = CONFIGS[name]
            rows, st = dev_stats(opts, era, with_fallbacks=(name == (args.dev_config or ["2026"])[0]))
            report["dev"][name] = {"stats": st, "per_case": rows}
            print(f"\n[dev:{name}] {st}")
            for r in rows:
                if "fallback" in r:
                    print(f"    fallback candidate {r['id']}: {r['fallback']}")
    if args.compare:
        diffs, dev_diffs = compare(report, args.compare)
        report["compare"] = {"against": args.compare, "per_case": diffs, "dev": dev_diffs}
        print(f"\ncompare against {args.compare}:")
        for name, d in diffs.items():
            print(f"    practice [{name}] cases whose findings changed: {len(d)} {[x['id'] for x in d][:20]}")
        for name, d in dev_diffs.items():
            print(f"    dev [{name}] cases whose findings changed: {len(d)} {d[:10]}")
    Path(args.out).write_text(json.dumps(report, indent=1, default=str))
    print(f"\nreport -> {args.out}")


if __name__ == "__main__":
    main()
