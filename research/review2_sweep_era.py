#!/usr/bin/env python3
"""Variant sweep, era step: guard settings switched per filing by an observable property.

    python3 review2_sweep_era.py      # -> scratchpad/sweep2/era.json + printed table

An era rule assigns each filing one 0117 setting:
    us-gaap <= 2022            -> LEGACY (kept fixed: "the 2021/2022 fit unchanged")
    otherwise, property in V   -> S (the switched setting)
    otherwise                  -> 2026 (faithful)
Properties: us-gaap year, filing date (dev: EDGAR manifest; practice: period end + 70 days for a
10-K / + 42 days for a 10-Q, an ESTIMATE), form, fiscal period focus, filing software, filer
category.  Settings S are the CLOSED variants of review2_sweep.py plus element-split composites
("9574 from A, 10093 from B"), all read from scratchpad/sweep2/raw_*.jsonl.

For every (property, threshold/value, S) it reports
  practice us-gaap 2023+ at set level (9574 findings; and 9574+10093) vs the released 0117 cases:
      exact filings, released, extra, missed;
  dev: which of the seven unexplained cases (no faithful module fires) get candidates,
      how many single-answer cases (one faithful module, one answer) gain/lose/change,
      and how many keys the switch adds in dev filings and how many of those are dev questions
      (the ranked generator samples: faithful keys are drawn at 673/1225 = 55%).
Practice gold is read only for the set-level counts.
"""
from __future__ import annotations

import collections
import datetime as dt
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review2_sweep_common as C  # noqa: E402
from review2_sweep_analyze import (N, R17, answers, bucket, classify, faithful_answers, load_raw,  # noqa: E402
                                   practice_sets)

RELEASES = {  # merge dates of the DQC releases that touched DQC_0117.xule (GitHub history)
    "V21 (notes guard, 10093, subtotal guard added)": "2023-07-27",
    "v23.0.0 (2024 rule file created)": "2024-01-17",
    "v24.0.3 (parenthetical guard added)": "2024-08-09",
    "v25.0.8 (copyright)": "2025-01-24",
    "v26.0.0 (2025 rule file created)": "2025-03-05",
    "v27.0.0": "2025-06-22",
    "v28.0.0 (DQCRT applicable_form check added)": "2025-10-25",
    "v28.0.7": "2026-02-15",
}


def composite(spec):
    """spec: name -> (9574 source variant, 10093 source variant)."""
    a, b = spec
    return lambda fr: [r for r in fr["f17c"][a] if r["re"] == "9574"] + [r for r in fr["f17c"][b] if r["re"] == "10093"]


SETTINGS = {
    "2026": composite(("2026", "2026")),
    "no_notes (both elements)": composite(("no_notes", "no_notes")),
    "legacy (both elements)": composite(("legacy", "legacy")),
    "10093-only notes guard off (9574 2026)": composite(("2026", "no_notes")),
    "9574-only notes guard off (10093 2026)": composite(("no_notes", "2026")),
    "10093-only legacy (9574 2026)": composite(("2026", "legacy")),
    "no_paren": composite(("no_paren", "no_paren")),
    "no_rev": composite(("no_rev", "no_rev")),
    "no_period": composite(("no_period", "no_period")),
    "no_validity": composite(("no_validity", "no_validity")),
    "sub_any": composite(("sub_any", "sub_any")),
    "sub_strict": composite(("sub_strict", "sub_strict")),
    "no_notes+no_paren": composite(("no_notes+no_paren", "no_notes+no_paren")),
    "no_notes+no_rev": composite(("no_notes+no_rev", "no_notes+no_rev")),
}
LEGACY_FIXED = composite(("legacy", "legacy"))


def d(s):
    return dt.date.fromisoformat(s) if s else None


def filing_dates():
    man = json.loads(C.MANIFEST.read_text())
    return man


def props_dev(fr, man):
    p = dict(fr["props"])
    cands = man.get(fr["filing"], {}).get("candidates", [])
    pe = p.get("DocumentPeriodEndDate")
    pick = [c for c in cands if c["form"].startswith(("10-K", "10-Q")) and c["reportDate"] == pe] or \
           [c for c in cands if c["form"].startswith(("10-K", "10-Q"))] or cands
    p["filing_date"] = pick[0]["filingDate"] if pick else None
    p["filing_date_source"] = "edgar_manifest"
    return p


def props_practice(fr):
    p = dict(fr["props"])
    pe = d(p.get("DocumentPeriodEndDate"))
    lag = 70 if (p.get("DocumentType") or "").startswith("10-K") else 42
    p["filing_date"] = (pe + dt.timedelta(days=lag)).isoformat() if pe else None
    p["filing_date_source"] = "estimate: period end + %d days" % lag
    return p


def software_family(s):
    s = (s or "").lower()
    if "workiva" in s or "wdesk" in s:
        return "Workiva"
    if "thunderdome" in s:
        return "ThunderDome"
    return "other/unknown" if s else "none"


def era_rules():
    rules = []
    for y in (2023, 2024, 2025, 2026):
        rules.append((f"us-gaap year >= {y}", lambda p, y=y: (p["us_gaap_year"] or 0) >= y))
        rules.append((f"us-gaap year == {y}", lambda p, y=y: (p["us_gaap_year"] or 0) == y))
    for name, date in RELEASES.items():
        rules.append((f"filing date >= {date} [{name}]", lambda p, t=date: (p["filing_date"] or "") >= t))
        rules.append((f"filing date < {date} [{name}]", lambda p, t=date: bool(p["filing_date"]) and p["filing_date"] < t))
    for t in ("2024-04-01", "2024-06-01", "2024-10-01", "2025-01-01", "2025-02-01", "2025-06-01", "2025-09-01",
              "2025-12-01", "2026-01-01"):
        rules.append((f"filing date >= {t}", lambda p, t=t: (p["filing_date"] or "") >= t))
    for form in ("10-K", "10-Q"):
        rules.append((f"form == {form}", lambda p, f=form: (p["DocumentType"] or "").startswith(f)))
    for fp in ("FY", "Q1", "Q2", "Q3"):
        rules.append((f"fiscal period focus == {fp}", lambda p, fp=fp: p.get("DocumentFiscalPeriodFocus") == fp))
    for sw in ("Workiva", "ThunderDome", "other/unknown", "none"):
        rules.append((f"software == {sw}", lambda p, sw=sw: software_family(p.get("software")) == sw))
    for cat in ("Large Accelerated Filer", "Accelerated Filer", "Non-accelerated Filer"):
        rules.append((f"filer category == {cat}", lambda p, c=cat: (p.get("EntityFilerCategory") or "") == c))
    rules.append(("all filings (no era)", lambda p: True))
    return rules


def main():
    P = C.practice_index()
    Dv = C.dev_index()
    RP, RD = load_raw("practice"), load_raw("dev")
    man = filing_dates()
    gold, rules_of = practice_sets(P, RP)
    Pprops = {f: props_practice(fr) for f, fr in RP.items()}
    Dprops = {f: props_dev(fr, man) for f, fr in RD.items()}
    faithful = {cid: faithful_answers(RD[e["filing"]], cid, e) for cid, e in Dv.items()}
    none_ids = sorted(c for c, fa in faithful.items() if classify(fa) == "none")
    qs = collections.defaultdict(set)
    for cid, e in Dv.items():
        qk = RD[e["filing"]]["qk"][cid]
        qs[e["filing"]].add((qk["c17"], tuple(qk["p"])))

    def recs_for(fr, props, setting, pred):
        if (props["us_gaap_year"] or 9999) <= 2022:
            return LEGACY_FIXED(fr)
        return SETTINGS[setting](fr) if pred(props) else SETTINGS["2026"](fr)

    results = []
    for rname, pred in era_rules():
        for setting in SETTINGS:
            if setting == "2026":
                continue
            # practice 2023+ set level
            st = collections.Counter()
            st_all = collections.Counter()
            applied_practice = 0
            for f, fr in RP.items():
                gk = gold[f].get(R17)
                if not gk or (Pprops[f]["us_gaap_year"] or 9999) <= 2022:
                    continue
                applied_practice += bool(pred(Pprops[f]))
                recs = recs_for(fr, Pprops[f], setting, pred)
                for view, s in (("9574", st), ("all", st_all)):
                    fk = {(r["c"], tuple(r["p"]), N(r["t"]), N(r["m"])) for r in recs if view == "all" or r["re"] == "9574"}
                    s["filings"] += 1
                    s["exact"] += fk == gk
                    s["released"] += len(fk & gk)
                    s["extra"] += len(fk - gk)
                    s["missed"] += len(gk - fk)
            # dev
            dev = collections.Counter()
            gained = {}
            applied_dev = 0
            new_keys = drawn = 0
            for f, fr in RD.items():
                on = pred(Dprops[f]) and (Dprops[f]["us_gaap_year"] or 9999) > 2022
                applied_dev += on
                base = {(r["c"], tuple(r["p"])) for r in SETTINGS["2026"](fr)}
                recs = recs_for(fr, Dprops[f], setting, pred)
                keys = {(r["c"], tuple(r["p"])) for r in recs}
                nk = keys - base
                new_keys += len(nk)
                drawn += len(nk & qs[f])
            for cid, e in Dv.items():
                fr = RD[e["filing"]]
                qk = fr["qk"][cid]
                recs = recs_for(fr, Dprops[e["filing"]], setting, pred)
                cs = [r for r in recs if r["c"] == qk["c17"] and r["p"] == qk["p"]]
                new_default = answers([(N(r["t"]), N(r["m"])) for r in cs if r["re"] == "9574"])
                new_all = answers([(N(r["t"]), N(r["m"])) for r in cs])
                fa = faithful[cid]
                cls = classify(fa)
                old = fa[R17]
                if cid in none_ids:
                    if new_all:
                        gained[cid] = [[str(a), str(b)] for a, b in new_all]
                    continue
                if set(new_default) == set(old) and set(new_all) <= set(old) | set(
                        answers([(N(r["t"]), N(r["m"])) for r in SETTINGS["2026"](fr) if r["c"] == qk["c17"] and r["p"] == qk["p"]])):
                    continue
                if cls == "single":
                    cur = [a for aa in fa.values() for a in aa][0]
                    if cur not in new_all and old:
                        dev["single_" + ("lose" if not new_all else "change")] += 1
                    else:
                        dev["single_gain"] += 1
                else:
                    dev[cls + "_changed"] += 1
            ok = st["extra"] == 0 and st["missed"] == 0
            results.append({
                "rule": rname, "setting": setting, "practice_2023plus_filings_switched": applied_practice,
                "practice_2023plus_9574": dict(st), "practice_2023plus_9574_10093": dict(st_all),
                "practice_exact_2023plus": ok, "practice_exact_2023plus_incl_10093": st_all["extra"] == 0 and st_all["missed"] == 0,
                "dev_filings_switched": applied_dev, "unexplained_with_candidates": gained,
                "dev_single_answer_effects": dict(dev), "dev_new_keys": new_keys, "dev_new_keys_drawn": drawn,
            })
    out = {"releases": RELEASES, "dev_filing_dates_focus": {cid: Dprops[Dv[cid]["filing"]]["filing_date"] for cid in C.FOCUS},
           "practice_breakers_no_notes": [], "results": results}
    # practice filings that a 9574 notes-guard switch breaks (for the record)
    for f, fr in RP.items():
        gk = gold[f].get(R17)
        if not gk or (Pprops[f]["us_gaap_year"] or 9999) <= 2022:
            continue
        fk = {(r["c"], tuple(r["p"]), N(r["t"]), N(r["m"])) for r in SETTINGS["no_notes (both elements)"](fr) if r["re"] == "9574"}
        if fk != gk:
            out["practice_breakers_no_notes"].append({"filing": f, "extra": len(fk - gk), "missed": len(gk - fk),
                                                      **{k: Pprops[f].get(k) for k in ("us_gaap_year", "DocumentType", "DocumentPeriodEndDate", "filing_date", "software", "EntityFilerCategory", "DocumentFiscalPeriodFocus")}})
    (C.SWEEP_OUT / "era.json").write_text(json.dumps(out, indent=1, default=str))
    print("practice 2023+ filings broken by switching the notes guard off:")
    for b in out["practice_breakers_no_notes"]:
        print("   ", b)
    print("dev filing dates of focus cases:", out["dev_filing_dates_focus"])
    print("\nrules that keep practice 2023+ exact (9574 set level) AND give candidates to unexplained dev cases:")
    for r in results:
        if r["practice_exact_2023plus"] and r["unexplained_with_candidates"]:
            print(f"  [{r['setting']}] {r['rule']}: practice switched {r['practice_2023plus_filings_switched']}, "
                  f"dev switched {r['dev_filings_switched']}, unexplained {sorted(r['unexplained_with_candidates'])}, "
                  f"single-answer effects {r['dev_single_answer_effects']}, new keys {r['dev_new_keys']} drawn {r['dev_new_keys_drawn']}, "
                  f"exact incl 10093 {r['practice_exact_2023plus_incl_10093']}")
    print("\nrules that give candidates but break practice 2023+:")
    seen = collections.Counter()
    for r in results:
        if not r["practice_exact_2023plus"] and r["unexplained_with_candidates"]:
            seen[r["setting"]] += 1
    print("   ", dict(seen))


if __name__ == "__main__":
    main()


# --------------------------------------------------------------------------- #
# Release-at-filing-date model (DQC release in production when the filing was made)
# --------------------------------------------------------------------------- #

MAJOR_FIRST = C.SWEEP_OUT / "gh_cache/major_release_first_dates.json"  # GitHub release list, first non-RC tag per major


def release_at(date, firsts):
    best = None
    for v, d0 in sorted(((int(k), v) for k, v in firsts.items())):
        if date and d0 <= date:
            best = v
    return best


def release_model():
    from review2_sweep_analyze import flagged15, keys15, cands15, ans15, R15
    firsts = json.loads(MAJOR_FIRST.read_text())
    P = C.practice_index()
    Dv = C.dev_index()
    RP, RD = load_raw("practice"), load_raw("dev")
    man = filing_dates()
    gold, rules_of = practice_sets(P, RP)
    Pprops = {f: props_practice(fr) for f, fr in RP.items()}
    Dprops = {f: props_dev(fr, man) for f, fr in RD.items()}
    faithful = {cid: faithful_answers(RD[e["filing"]], cid, e) for cid, e in Dv.items()}
    out = {}
    # 0015: element list as of the release at the filing date (clipped to v17..v30)
    def ver(props):
        v = release_at(props["filing_date"], firsts) or 17
        return min(max(v, 17), 30)
    st = collections.defaultdict(collections.Counter)
    for f, fr in RP.items():
        gk = gold[f].get(R15)
        if not gk:
            continue
        b = bucket(Pprops[f]["us_gaap_year"])
        fk = keys15(fr, f"v{ver(Pprops[f])}")
        s = st[b]
        s["filings"] += 1
        s["exact"] += fk == gk
        s["released"] += len(fk & gk)
        s["extra"] += len(fk - gk)
        s["missed"] += len(gk - fk)
    dev = collections.Counter()
    changed = []
    vdist = collections.Counter(ver(p) for p in Dprops.values())
    for cid, e in Dv.items():
        fr = RD[e["filing"]]
        new = ans15(cands15(fr, fr["qk"][cid], f"v{ver(Dprops[e['filing']])}"))
        old = faithful[cid][R15]
        if set(new) != set(old):
            cls = classify(faithful[cid])
            dev[cls + ("_lose" if not new else "_change")] += 1
            changed.append([cid, Dprops[e["filing"]]["filing_date"], ver(Dprops[e["filing"]]), [list(map(str, a)) for a in old], [list(map(str, a)) for a in new]])
    out["0015_release_at_filing_date"] = {"practice": {k: dict(v) for k, v in st.items()},
                                          "practice_versions": dict(collections.Counter(ver(Pprops[f]) for f in RP if gold[f].get(R15))),
                                          "dev_versions": dict(sorted(vdist.items())), "dev_effects": dict(dev), "dev_changed": changed}
    # 0117: pre-V21 -> LEGACY (fitted stand-in), V21..v24.0.3 -> no_paren, later -> 2026;
    # optionally with 10093's notes guard off in every era from V21 on
    for tag, late10093 in (("faithful", "2026"), ("10093 notes guard off from V21", "no_notes")):
        def setting(props):
            d0 = props["filing_date"] or ""
            if d0 < "2023-07-14":
                return ("legacy", "legacy")
            if d0 < "2024-08-09":
                return ("no_paren", "no_notes+no_paren" if late10093 == "no_notes" else "no_paren")
            return ("2026", late10093)
        def recs(fr, props):
            a, b = setting(props)
            return [r for r in fr["f17c"][a] if r["re"] == "9574"] + [r for r in fr["f17c"][b] if r["re"] == "10093"]
        st = collections.defaultdict(collections.Counter)
        for f, fr in RP.items():
            gk = gold[f].get(R17)
            if not gk:
                continue
            b = bucket(Pprops[f]["us_gaap_year"])
            for view in ("9574", "all"):
                fk = {(r["c"], tuple(r["p"]), N(r["t"]), N(r["m"])) for r in recs(fr, Pprops[f]) if view == "all" or r["re"] == "9574"}
                s = st[b + ":" + view]
                s["filings"] += 1
                s["exact"] += fk == gk
                s["released"] += len(fk & gk)
                s["extra"] += len(fk - gk)
                s["missed"] += len(gk - fk)
        dev = collections.Counter()
        gained = {}
        for cid, e in Dv.items():
            fr = RD[e["filing"]]
            qk = fr["qk"][cid]
            cs = [r for r in recs(fr, Dprops[e["filing"]]) if r["c"] == qk["c17"] and r["p"] == qk["p"]]
            new = answers([(N(r["t"]), N(r["m"])) for r in cs])
            cls = classify(faithful[cid])
            if cls == "none":
                if new:
                    gained[cid] = [list(map(str, a)) for a in new]
                continue
            base = answers([(N(r["t"]), N(r["m"])) for r in SETTINGS["2026"](fr) if r["c"] == qk["c17"] and r["p"] == qk["p"]])
            if set(new) != set(base):
                dev[cls + "_changed"] += 1
        out["0117_release_at_filing_date:" + tag] = {"practice": {k: dict(v) for k, v in st.items()},
                                                    "dev_single_or_multi_changed": dict(dev),
                                                    "unexplained_with_candidates": gained}
    return out


if __name__ == "__main__":
    rm = release_model()
    prev = json.loads((C.SWEEP_OUT / "era.json").read_text())
    prev["release_model"] = rm
    (C.SWEEP_OUT / "era.json").write_text(json.dumps(prev, indent=1, default=str))
    for k, v in rm.items():
        print("\n==", k)
        for kk, vv in v.items():
            print("  ", kk, vv if not isinstance(vv, list) else vv[:12])
