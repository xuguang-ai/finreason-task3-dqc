#!/usr/bin/env python3
"""Variant sweep, analysis step.  Reads scratchpad/sweep2/raw_{practice,dev}.jsonl (review2_sweep.py).

    python3 review2_sweep_analyze.py            # writes scratchpad/sweep2/analysis.json + prints the tables

(a) practice consistency at SET level per variant, us-gaap 2023+ and 2021/2022 filings apart:
    findings over all concepts/periods of each filing whose released rule is the variant's rule,
    against the released curated cases of that rule in that filing (released / extra / missed);
(b) dev side effects over the 680 dev cases: the faithful single-answer cases (one module, one
    distinct answer) that gain, lose or change candidates for the questioned concept/period,
    plus findings in dev filings that match no dev question of the filing (dev and test
    filings are disjoint, so in a dev filing every finding of the generator's rule should be a
    dev question);
(c) the full candidate list of the focus cases under every variant.
The era analysis (rules switched by per-filing properties) is in review2_sweep_era.py.

Practice gold is read here only for (a).  No dev gold exists; none is looked for.
"""
from __future__ import annotations

import collections
import json
import sys
from decimal import Decimal
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review2_sweep_common as C  # noqa: E402

D15 = C.D15
OUT = C.SWEEP_OUT
R17, R26, R15 = "DQC_US_0117", "DQC_US_0126", "DQC_US_0015"


def N(v):
    return None if v is None else Decimal(str(v).replace(",", "").strip())


#: element-split composites: name -> (variant for rule element 9574, variant for 10093)
COMPOSITES = {
    "split:9574=2026,10093=no_notes": ("2026", "no_notes"),
    "split:9574=no_notes,10093=2026": ("no_notes", "2026"),
    "split:9574=2026,10093=legacy": ("2026", "legacy"),
    "split:9574=2026,10093=none": ("2026", None),
}


def load_raw(split):
    out = {}
    for line in open(OUT / f"raw_{split}.jsonl"):
        r = json.loads(line)
        for key in ("f17c", "f17o"):
            for name, (a, b) in COMPOSITES.items():
                r[key][name] = [x for x in r[key][a] if x["re"] == "9574"] + \
                               ([x for x in r[key][b] if x["re"] == "10093"] if b else [])
        out[r["filing"]] = r
    return out


# --------------------------------------------------------------------------- #
# Variant registry
# --------------------------------------------------------------------------- #

def variants_17(raw_any):
    r = next(iter(raw_any.values()))
    return [("C", v) for v in r["f17c"]] + [("O", v) for v in r["f17o"]]


V26 = ["faithful", "no_cube_skip", "alt_min_child_decimals", "alt_all_children_counted", "alt_first_value_only"]


def item_of(reason: str) -> str:
    kind, rest = reason.split(":", 1)
    if kind == "member-substring":
        return "string:" + rest.split(":", 1)[0]
    return {"member": "member:", "axis": "axis:", "axis-member": "pair:"}[kind] + rest


def items_15():
    out = ["string:" + s for s in D15.EXCLUDE_NON_NEG_STRING_MEMBERS]
    out += ["member:" + m[1] for m in sorted(D15.EXCLUDE_NON_NEG_MEMBERS)]
    out += ["axis:" + a[1] for a in sorted(D15.EXCLUDE_NON_NEG_AXIS)]
    out += ["pair:" + ax[1] + "=" + m[1] for ax, ms in D15.EXCLUDE_NON_NEG_AXIS_MEMBERS for m in sorted(ms)]
    return out


V15 = [f"v{v}" for v in range(17, D15.LATEST_VERSION + 1)] + ["drop:" + i for i in items_15()] + \
      ["drop:ALL_exclusions", "v_any+drop:ALL_exclusions"]


def flagged15(rec, v):
    if v.startswith("v_any"):
        listed = bool(rec["listed"])
    elif v.startswith("v") and v[1:].isdigit():
        return int(v[1:]) in rec["listed"] and not rec["reasons"]
    else:
        listed = D15.DEFAULT_VERSION in rec["listed"]
    if not listed:
        return False
    if v.endswith("drop:ALL_exclusions"):
        return True
    item = v.split("drop:", 1)[1]
    return all(item_of(x) == item for x in rec["reasons"])


# --------------------------------------------------------------------------- #
# Candidates for one question
# --------------------------------------------------------------------------- #

def cands17(fr, qk, reading, v, mode="default"):
    """mode default = what findings_0117 returns (CLOSED: 9574; OPEN: dimension-free totals);
    dim = the rest (10093 / dimensional totals); all = both."""
    recs = fr["f17c" if reading == "C" else "f17o"][v]
    out = []
    for r in recs:
        if r["c"] != qk["c17"] or r["p"] != qk["p"]:
            continue
        default = (r["re"] == "9574") if reading == "C" else (not r["td"])
        if mode == "default" and not default:
            continue
        if mode == "dim" and default:
            continue
        out.append(r)
    return out


def fires26(r, v):
    """alt_* readings are recorded only where they differ in kind (e.g. first_value_only only for
    children with several facts); elsewhere the alternative reading equals the faithful one."""
    if v.startswith("alt_") and v not in r["fires"]:
        return bool(r["fires"].get("faithful"))
    return bool(r["fires"].get(v))


def cands26(fr, concept, qk, v):
    out = []
    for r in fr["f26"]:
        if r["c"] != concept or r["p"] != qk["p26"] or not fires26(r, v):
            continue
        out.append(r)
    return out


def calc26(r, v):
    return r["alt_calc"].get(v, r["calc"])


def cands15(fr, qk, v):
    return [r for r in fr["f15"] if r["key"] == qk["k15"] and r["p"] == qk["p15"] and flagged15(r, v)]


def answers(pairs):
    out = []
    for p in pairs:
        if p not in out:
            out.append(p)
    return out


def ans17(cs):
    return answers([(N(r["t"]), N(r["m"])) for r in cs])


def ans26(cs, v):
    return answers([(N(r["e"]), N(calc26(r, v))) for r in cs])


def ans15(cs):
    return answers([(N(r["e"]), N(r["calc"])) for r in cs])


# --------------------------------------------------------------------------- #
# Faithful partition (dev)
# --------------------------------------------------------------------------- #

def faithful_answers(fr, cid, e):
    qk = fr["qk"][cid]
    return {
        R17: ans17(cands17(fr, qk, "C", "2026")),
        R26: ans26(cands26(fr, e["concept"], qk, "faithful"), "faithful"),
        R15: ans15(cands15(fr, qk, f"v{D15.DEFAULT_VERSION}")),
    }


def classify(fa):
    fired = [r for r, a in fa.items() if a]
    if not fired:
        return "none"
    if len(fired) > 1:
        return "overlap"
    a = fa[fired[0]]
    return "single" if len(a) == 1 else "multi"


# --------------------------------------------------------------------------- #
# (a) practice set level
# --------------------------------------------------------------------------- #

def bucket(year):
    return "us-gaap<=2022" if (year or 9999) <= 2022 else "us-gaap>=2023"


def practice_sets(P, RP):
    """Per filing: curated gold keys by rule (concept resolved by the 0117 module, period)."""
    by_filing = collections.defaultdict(lambda: collections.defaultdict(set))
    rules_of = collections.defaultdict(set)
    for cid, e in P.items():
        fr = RP[e["filing"]]
        rules_of[e["filing"]].add(e["rule"])
        if not e["curated"]:
            continue
        qk = fr["qk"][cid]
        if e["rule"] == R17:
            by_filing[e["filing"]][R17].add((qk["c17"], tuple(qk["p"]), N(e["ge"]), N(e["gc"])))
        elif e["rule"] == R26:
            by_filing[e["filing"]][R26].add((e["concept"], tuple(qk["p26"]), N(e["ge"]), N(e["gc"])))
        else:
            by_filing[e["filing"]][R15].add((tuple(qk["k15"]), tuple(qk["p15"]), N(e["ge"]), N(e["gc"])))
    return by_filing, rules_of


def keys17(fr, reading, v, view):
    out = set()
    for r in fr["f17c" if reading == "C" else "f17o"][v]:
        if view == "9574" and r["re"] != "9574":
            continue
        if view == "9574_dimfree" and (r["re"] != "9574" or r["td"]):
            continue
        if view == "10093" and r["re"] != "10093":
            continue
        out.add((r["c"], tuple(r["p"]), N(r["t"]), N(r["m"])))
    return out


def keys26(fr, v):
    return {(r["c"], tuple(r["p"]), N(r["e"]), N(calc26(r, v))) for r in fr["f26"] if fires26(r, v)}


def keys15(fr, v):
    return {(tuple(r["key"]), tuple(r["p"]), N(r["e"]), N(r["calc"])) for r in fr["f15"] if flagged15(r, v)}


def set_level(RP, gold, rules_of, rule, keyfun, P_year):
    """{bucket: counts} over filings whose curated released rule includes ``rule``; also the
    findings in practice filings that released other rules only (secondary evidence)."""
    out = collections.defaultdict(lambda: collections.Counter())
    detail = []
    other = collections.Counter()
    for filing, fr in RP.items():
        b = bucket(P_year[filing])
        fk = keyfun(fr)
        gk = gold[filing].get(rule, set())
        if not gk:
            if rule not in rules_of[filing]:
                other[b + ":filings"] += 1
                other[b + ":filings_with_findings"] += bool(fk)
                other[b + ":findings"] += len(fk)
            continue
        for k in (b, "all"):
            s = out[k]
            s["filings"] += 1
            s["exact"] += fk == gk
            s["gold"] += len(gk)
            s["released"] += len(gk & fk)
            s["missed"] += len(gk - fk)
            s["extra"] += len(fk - gk)
        if fk != gk:
            detail.append({"filing": filing, "bucket": b, "missed": sorted(map(str, gk - fk))[:6],
                           "extra": sorted(map(str, fk - gk))[:6], "n_missed": len(gk - fk),
                           "n_extra": len(fk - gk)})
    return {k: dict(v) for k, v in out.items()}, detail, dict(other)


def practice_case_level(P, RP, rule, candfun):
    """Curated cases of ``rule``: gold among the variant's question-level candidates, by bucket."""
    out = collections.defaultdict(collections.Counter)
    for cid, e in P.items():
        if not e["curated"] or e["rule"] != rule:
            continue
        fr = RP[e["filing"]]
        a = candfun(fr, cid, e)
        g = (N(e["ge"]), N(e["gc"]))
        for k in (bucket(e["us_gaap_year"]), "all"):
            out[k]["cases"] += 1
            out[k]["gold_among"] += g in a
            out[k]["exactly_gold"] += a == [g]
            out[k]["no_candidate"] += not a
    return {k: dict(v) for k, v in out.items()}


def practice_0015_extra(P, RP, v):
    """0015-specific practice checks: per-query multiplicity (n cases == n flagged facts) and
    firing on the questioned concept/period of curated 0117/0126 cases."""
    groups = collections.defaultdict(list)
    for cid, e in P.items():
        if e["curated"] and e["rule"] == R15:
            groups[(e["filing"], e["concept"], tuple(e["period"]))].append(cid)
    mult = collections.Counter()
    for (filing, concept, period), ids in groups.items():
        fr = RP[filing]
        n = len(cands15(fr, fr["qk"][ids[0]], v))
        mult["queries"] += 1
        mult["n_cases_eq_n_findings"] += n == len(ids)
    fires_other = collections.Counter()
    for cid, e in P.items():
        if e["curated"] and e["rule"] != R15:
            fr = RP[e["filing"]]
            if cands15(fr, fr["qk"][cid], v):
                fires_other[e["rule"]] += 1
    return {"multiplicity": dict(mult), "fires_on_other_rule_cases": dict(fires_other)}


# --------------------------------------------------------------------------- #
# (b) dev side effects
# --------------------------------------------------------------------------- #

def dev_effects(Dv, RD, faithful, rule, candfun):
    """For each dev case: the variant's candidates for ``rule`` replace the faithful ones."""
    st = collections.Counter()
    changed = []
    for cid, e in Dv.items():
        fr = RD[e["filing"]]
        fa = faithful[cid]
        cls = classify(fa)
        new = candfun(fr, cid, e)
        old = fa[rule]
        if new == old or set(new) == set(old):
            continue
        cur = [a for r, aa in fa.items() for a in aa]
        if cls == "single":
            cur_ans = cur[0]
            own = fa[rule] != []
            if not own:
                kind = "gain"
            elif cur_ans in new:
                kind = "gain" if len(set(new)) > 1 else "same"
            elif not new:
                kind = "lose"
            else:
                kind = "change"
            st["single_" + kind] += 1
        else:
            st[cls + "_changed"] += 1
            kind = cls
        changed.append({"id": cid, "class": cls, "kind": kind, "faithful": {r: [list(map(str, a)) for a in aa] for r, aa in fa.items() if aa},
                        "variant": [list(map(str, a)) for a in new]})
    return dict(st), changed


def dev_unreleased(Dv, RD, faithful, rule, keyfun_q):
    """Findings in dev filings (default question-level semantics, all concepts/periods) that
    match no dev question of the filing, split by the filing's faithful rule mix."""
    qs = collections.defaultdict(set)
    mix = collections.defaultdict(set)
    for cid, e in Dv.items():
        fr = RD[e["filing"]]
        qs[e["filing"]].add(keyfun_q(fr, cid, e))
        cls = classify(faithful[cid])
        for r, aa in faithful[cid].items():
            if aa:
                mix[e["filing"]].add(r)
        if cls == "none":
            mix[e["filing"]].add("none")
    st = collections.Counter()
    for filing, fr in RD.items():
        fk = fr["_keys"]
        if not fk:
            continue
        m = mix[filing]
        tag = "own_rule_filing" if m == {rule} else ("none_filing" if "none" in m else "other_rule_filing")
        n_un = len({k for k in fk if k not in qs[filing]})
        st[tag + ":findings"] += len(fk)
        st[tag + ":not_a_dev_question"] += n_un
        st[tag + ":filings_with_unmatched"] += bool(n_un)
    return dict(st)


# --------------------------------------------------------------------------- #
# Dev draw rate: the ranked generator samples one case per drawn question key
# --------------------------------------------------------------------------- #

def lk(c, p):
    return (c.split(":")[-1], tuple(p))


def faithful_keys(fr):
    return {
        R17: {lk(r["c"], r["p"]) for r in fr["f17c"]["2026"]},
        R26: {lk(r["c"], r["p"]) for r in fr["f26"] if fires26(r, "faithful")},
        R15: {(r["key"][1], tuple(r["p"])) for r in fr["f15"] if flagged15(r, f"v{D15.DEFAULT_VERSION}")},
    }


def dev_questions(Dv, RD):
    qs = collections.defaultdict(set)
    for cid, e in Dv.items():
        qk = RD[e["filing"]]["qk"][cid]
        qs[e["filing"]].add(lk(qk["c17"], qk["p"]))
    return qs


def draw_stats(RD, qs, rule, keyfun):
    """Keys (concept, period) the variant adds outside the faithful pool of all three rules, and
    how many of them are dev questions; keys of ``rule`` it removes that are dev questions no other
    faithful rule explains (a removed drawn key contradicts the variant)."""
    st = collections.Counter()
    for f, fr in RD.items():
        F = fr.setdefault("_fk", faithful_keys(fr))
        pool = F[R17] | F[R26] | F[R15]
        others = set().union(*(F[r] for r in (R17, R26, R15) if r != rule))
        V = keyfun(fr)
        added = V - pool
        removed = F[rule] - V
        st["added"] += len(added)
        st["added_drawn"] += len(added & qs[f])
        st["removed"] += len(removed)
        st["removed_drawn_unexplained"] += len((removed & qs[f]) - others)
    return dict(st)


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #

def main():
    P = C.practice_index()
    Dv = C.dev_index()
    RP, RD = load_raw("practice"), load_raw("dev")
    P_year = {}
    for cid, e in P.items():
        P_year[e["filing"]] = e["us_gaap_year"]
    gold, rules_of = practice_sets(P, RP)

    faithful = {cid: faithful_answers(RD[e["filing"]], cid, e) for cid, e in Dv.items()}
    qs = dev_questions(Dv, RD)
    base_pool = sum(len(set().union(*faithful_keys(fr).values())) for fr in RD.values())
    base_drawn = sum(len(set().union(*faithful_keys(fr).values()) & qs[f]) for f, fr in RD.items())
    print(f"faithful pool: {base_pool} keys in dev filings, {base_drawn} are dev questions")
    part = collections.Counter()
    for cid, fa in faithful.items():
        cls = classify(fa)
        part[cls] += 1
        if cls in ("single", "multi"):
            part[cls + ":" + next(r for r, a in fa.items() if a)] += 1
    print("dev faithful partition:", dict(part))
    none_ids = sorted(c for c, fa in faithful.items() if classify(fa) == "none")
    multi_ids = sorted(c for c, fa in faithful.items() if classify(fa) == "multi")
    print("none:", none_ids)
    print("multi:", len(multi_ids))

    # dev filing rule mix
    mix = collections.defaultdict(collections.Counter)
    for cid, e in Dv.items():
        fa = faithful[cid]
        cls = classify(fa)
        mix[e["filing"]]["none" if cls == "none" else next(r for r, a in fa.items() if a)[-4:]] += 1
    mixes = collections.Counter("+".join(sorted(m)) for m in mix.values())
    print("dev filing rule mix (faithful):", dict(mixes))
    pmix = collections.Counter("+".join(sorted(r[-4:] for r in rs)) for rs in rules_of.values())
    print("practice filing rule mix (released):", dict(pmix))

    report = {"faithful_pool": {"keys": base_pool, "drawn": base_drawn}, "dev_partition": dict(part), "none_ids": none_ids, "multi_ids": multi_ids,
              "dev_filing_rule_mix": dict(mixes), "practice_filing_rule_mix": dict(pmix),
              "focus_filing_mix": {cid: dict(mix[Dv[cid]["filing"]]) for cid in C.FOCUS},
              "variants": {}, "focus": {}}

    # ---- 0117 ---------------------------------------------------------------- #
    for reading, v in variants_17(RD):
        name = f"0117:{'CLOSED' if reading == 'C' else 'OPEN'}:{v}"
        rec = {}
        for view in ("9574", "9574_dimfree", "10093", "all"):
            sl, det, oth = set_level(RP, gold, rules_of, R17, lambda fr: keys17(fr, reading, v, view), P_year)
            rec["set_" + view] = sl
            rec["set_" + view + "_other_filings"] = oth
            if view == "9574":
                rec["set_9574_detail"] = det
        rec["case_level"] = practice_case_level(
            P, RP, R17, lambda fr, cid, e: ans17(cands17(fr, fr["qk"][cid], reading, v)))
        st, ch = dev_effects(Dv, RD, faithful, R17, lambda fr, cid, e: ans17(cands17(fr, fr["qk"][cid], reading, v)))
        rec["dev_effects"] = st
        rec["dev_changed"] = ch
        st2, ch2 = dev_effects(Dv, RD, faithful, R17,
                               lambda fr, cid, e: ans17(cands17(fr, fr["qk"][cid], reading, v, "all")))
        rec["dev_effects_with_dimensional_totals"] = st2
        rec["dev_changed_with_dimensional_totals"] = [c for c in ch2 if c["class"] != "single" or c["kind"] != "same"]
        for fr in RD.values():
            fr["_keys"] = {(r["c"], tuple(r["p"])) for r in fr["f17c" if reading == "C" else "f17o"][v]
                           if ((r["re"] == "9574") if reading == "C" else not r["td"])}
        rec["dev_unreleased"] = dev_unreleased(Dv, RD, faithful, R17,
                                               lambda fr, cid, e: (fr["qk"][cid]["c17"], tuple(fr["qk"][cid]["p"])))
        rec["dev_draw"] = draw_stats(RD, qs, R17, lambda fr: {lk(r["c"], r["p"]) for r in fr["f17c" if reading == "C" else "f17o"][v]})
        report["variants"][name] = rec

    # ---- 0126 ---------------------------------------------------------------- #
    for v in V26:
        name = f"0126:{v}"
        rec = {}
        sl, det, oth = set_level(RP, gold, rules_of, R26, lambda fr: keys26(fr, v), P_year)
        rec["set"] = sl
        rec["set_other_filings"] = oth
        rec["set_detail"] = det
        rec["case_level"] = practice_case_level(P, RP, R26, lambda fr, cid, e: ans26(cands26(fr, e["concept"], fr["qk"][cid], v), v))
        st, ch = dev_effects(Dv, RD, faithful, R26, lambda fr, cid, e: ans26(cands26(fr, e["concept"], fr["qk"][cid], v), v))
        rec["dev_effects"] = st
        rec["dev_changed"] = ch
        for fr in RD.values():
            fr["_keys"] = {(r["c"], tuple(r["p"])) for r in fr["f26"] if fires26(r, v)}
        rec["dev_unreleased"] = dev_unreleased(Dv, RD, faithful, R26,
                                               lambda fr, cid, e: (e["concept"], tuple(fr["qk"][cid]["p26"])))
        rec["dev_draw"] = draw_stats(RD, qs, R26, lambda fr: {lk(r["c"], r["p"]) for r in fr["f26"] if fires26(r, v)})
        report["variants"][name] = rec

    # ---- 0015 ---------------------------------------------------------------- #
    for v in V15:
        name = f"0015:{v}"
        rec = {}
        sl, det, oth = set_level(RP, gold, rules_of, R15, lambda fr: keys15(fr, v), P_year)
        rec["set"] = sl
        rec["set_other_filings"] = oth
        rec["set_detail_n"] = len(det)
        rec["case_level"] = practice_case_level(P, RP, R15, lambda fr, cid, e: ans15(cands15(fr, fr["qk"][cid], v)))
        rec.update(practice_0015_extra(P, RP, v))
        st, ch = dev_effects(Dv, RD, faithful, R15, lambda fr, cid, e: ans15(cands15(fr, fr["qk"][cid], v)))
        rec["dev_effects"] = st
        rec["dev_changed"] = ch
        for fr in RD.values():
            fr["_keys"] = {(tuple(r["key"]), tuple(r["p"])) for r in fr["f15"] if flagged15(r, v)}
        rec["dev_unreleased"] = dev_unreleased(Dv, RD, faithful, R15,
                                               lambda fr, cid, e: (tuple(fr["qk"][cid]["k15"]), tuple(fr["qk"][cid]["p15"])))
        rec["dev_draw"] = draw_stats(RD, qs, R15, lambda fr: {(r["key"][1], tuple(r["p"])) for r in fr["f15"] if flagged15(r, v)})
        report["variants"][name] = rec

    # ---- (c) focus cases --------------------------------------------------------- #
    A = C.predictions(C.PRED_A)
    B = C.predictions(C.PRED_B)
    for cid in C.FOCUS:
        e = Dv[cid]
        fr = RD[e["filing"]]
        qk = fr["qk"][cid]
        shipped = set(e["shipped_roles"])
        cands = collections.OrderedDict()

        def add(key, info, variant):
            if key not in cands:
                cands[key] = dict(info, variants=[])
            cands[key]["variants"].append(variant)

        for reading, v in variants_17(RD):
            for r in cands17(fr, qk, reading, v, "all"):
                key = ("0117", r["t"], r["m"], r["re"], json.dumps(r["td"]), r["role"], r["ax"], r.get("d2"))
                add(key, {"rule": "0117", "extracted": r["t"], "calculated": r["m"], "rule_element": r["re"],
                          "total_dims": r["td"], "statement_role": r["role"].rsplit("/", 1)[-1],
                          "shipped_role": r["role"] in shipped, "axis": r["ax"], "dim2": r.get("d2"),
                          "n_members": r["n"], "members": r["mem"]},
                    f"{'CLOSED' if reading == 'C' else 'OPEN'}:{v}")
        for v in V26:
            for r in cands26(fr, e["concept"], qk, v):
                key = ("0126", r["e"], calc26(r, v), r["role"])
                add(key, {"rule": "0126", "extracted": r["e"], "calculated": calc26(r, v),
                          "statement_role": r["role"].rsplit("/", 1)[-1], "shipped_role": r["role"] in shipped,
                          "cube_role": r["cube_role"], "n_addends": r["n_add"], "n_children": r["n_ch"]}, v)
        for v in V15:
            for r in cands15(fr, qk, v):
                key = ("0015", r["e"], r["calc"], json.dumps(r["dims"]))
                add(key, {"rule": "0015", "extracted": r["e"], "calculated": r["calc"], "dims": r["dims"],
                          "reasons": r["reasons"], "listed_versions": [min(r["listed"]), max(r["listed"])] if r["listed"] else []}, v)
        # 0015 facts of the questioned concept/period that no variant flags (for 198-like cases)
        unflagged = [{"e": r["e"], "dims": r["dims"], "listed": r["listed"], "reasons": r["reasons"]}
                     for r in fr["f15"] if r["key"] == qk["k15"] and r["p"] == qk["p15"]]
        a, b = A[cid], B[cid]
        for k, info in cands.items():
            ex, ca = N(info["extracted"]), N(info["calculated"])
            info["equals_A"] = (ex, ca) == a
            info["equals_B"] = (ex, ca) == b
            # calculation-errors-0: an upload whose extracted value equals the candidate's but whose
            # calculated value differs would have had a calculation error if this were gold
            info["ruled_out_by_calc0"] = (ex == a[0] and ca != a[1]) or (ex == b[0] and ca != b[1])
        report["focus"][cid] = {"filing": e["filing"], "concept": e["concept"], "period": e["period"],
                                "A": list(map(str, a)), "B": list(map(str, b)),
                                "shipped_roles": [s.rsplit("/", 1)[-1] for s in sorted(shipped)],
                                "candidates": list(cands.values()), "negative_facts_0015": unflagged[:20]}

    (OUT / "analysis.json").write_text(json.dumps(report, indent=1, default=str))
    print_summary(report)


def fmt_set(s):
    if not s:
        return "-"
    return f"exact {s.get('exact', 0)}/{s.get('filings', 0)}, released {s.get('released', 0)}/{s.get('gold', 0)}, extra {s.get('extra', 0)}, missed {s.get('missed', 0)}"


def print_summary(rep):
    print("\n=== (a)+(b) per variant ===")
    for name, r in rep["variants"].items():
        if name.startswith("0117"):
            s = r["set_9574"]
            sa = r["set_all"]
            print(f"{name:40s} 9574 >=2023 [{fmt_set(s.get('us-gaap>=2023'))}] <=2022 [{fmt_set(s.get('us-gaap<=2022'))}]"
                  f" | +10093 >=2023 extra {sa.get('us-gaap>=2023', {}).get('extra')} <=2022 extra {sa.get('us-gaap<=2022', {}).get('extra')}"
                  f" | dev {r['dev_effects']} | dim {r['dev_effects_with_dimensional_totals']} | unrel {r['dev_unreleased']}")
        else:
            s = r["set"]
            extra = ""
            if name.startswith("0015"):
                extra = f" mult {r['multiplicity']} other {r['fires_on_other_rule_cases']}"
            print(f"{name:40s} >=2023 [{fmt_set(s.get('us-gaap>=2023'))}] <=2022 [{fmt_set(s.get('us-gaap<=2022'))}]{extra}"
                  f" | case {r['case_level'].get('all')} | dev {r['dev_effects']} | unrel {r['dev_unreleased']}")
    print("\n=== (c) focus ===")
    for cid, f in rep["focus"].items():
        print(cid, f["concept"], f["period"], "A", f["A"], "B", f["B"])
        for c in f["candidates"]:
            vs = c["variants"]
            print("    ", c["rule"], c["extracted"], c["calculated"], c.get("rule_element", ""), c.get("total_dims", c.get("dims", "")),
                  c.get("statement_role", ""), "shipped" if c.get("shipped_role") else "", "calc0-OUT" if c["ruled_out_by_calc0"] else "",
                  "=A" if c["equals_A"] else "", "=B" if c["equals_B"] else "", f"[{len(vs)} variants: {', '.join(vs[:8])}{' ...' if len(vs) > 8 else ''}]")


if __name__ == "__main__":
    main()
