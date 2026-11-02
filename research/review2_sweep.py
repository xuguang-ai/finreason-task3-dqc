#!/usr/bin/env python3
"""Variant sweep, compute step: every finding of every rule variant in every practice and dev filing.

    python3 review2_sweep.py [--split practice|dev|all] [--workers 10] [--limit N]

For each filing (practice: the 144 filings behind the 332 released cases; dev: the 352 filings
behind the 680 dev cases) this computes, with the complete filing DTS and instance:

  0117 CLOSED  current module claude_agent.dqc.dqc_0117 (XULE [...] read as closed factsets)
  0117 OPEN    pre-fix snapshot scratchpad/before/dqc_0117.py (open factsets), loaded in memory
               under the name claude_agent.dqc.dqc_0117_open
               -> ``_all_findings(filing, options, None)`` for every option variant below
                  (all concepts and periods, rule elements 9574 and 10093, all total dims)
  0126         ``evaluate(material)`` with the cube skip (faithful) and with
               ``statement_cube_uris`` patched to return nothing (no cube skip), plus the
               alternative readings the module records per evaluation (fires_alt)
  0015         every negative numeric fact after XULE duplicate elimination, with the
               releases v17..v30 that list its concept and every exclusion reason

and writes one JSON line per filing to scratchpad/sweep2/raw_<split>.jsonl.  No module file is
edited; the 0126 patch is a runtime attribute swap inside the worker process.
The analysis is in review2_sweep_analyze.py.
"""
from __future__ import annotations

import argparse
import concurrent.futures as cf
import json
import re
import sys
import time
import traceback
from dataclasses import replace
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import review2_sweep_common as C  # noqa: E402

D15, D17, D26, X = C.D15, C.D17, C.D26, C.X

VERSIONS = list(range(17, D15.LATEST_VERSION + 1))


def closed_variants():
    F, L = D17.FAITHFUL, D17.LEGACY
    return {
        "2026": F,
        "legacy": L,
        "no_notes": replace(F, notes_guard=False, label="x"),
        "no_paren": replace(F, parenthetical_guard=False, label="x"),
        "no_rev": replace(F, revenue_exceptions=False, label="x"),
        "no_period": replace(F, period_filter=False, label="x"),
        "no_validity": replace(F, member_validity=False, label="x"),
        "sub_off": replace(F, subtotal_guard="off", label="x"),
        "sub_any": replace(F, subtotal_guard="any", label="x"),
        "sub_strict": replace(F, subtotal_guard="strict", label="x"),
        "no_notes+no_paren": replace(F, notes_guard=False, parenthetical_guard=False, label="x"),
        "no_notes+no_rev": replace(F, notes_guard=False, revenue_exceptions=False, label="x"),
        "no_paren+no_rev": replace(F, parenthetical_guard=False, revenue_exceptions=False, label="x"),
        "legacy+no_period": replace(L, period_filter=False, label="x"),
        "legacy+no_validity": replace(L, member_validity=False, label="x"),
        "legacy+sub_any": replace(L, subtotal_guard="any", label="x"),
        "legacy+sub_strict": replace(L, subtotal_guard="strict", label="x"),
    }


def open_variants(O):
    F, L = O.FAITHFUL, O.LEGACY  # snapshot default subtotal_guard = "any"
    return {
        "2026": F,
        "legacy": L,
        "no_notes": replace(F, notes_guard=False, label="x"),
        "no_paren": replace(F, parenthetical_guard=False, label="x"),
        "no_rev": replace(F, revenue_exceptions=False, label="x"),
        "no_period": replace(F, period_filter=False, label="x"),
        "no_validity": replace(F, member_validity=False, label="x"),
        "sub_off": replace(F, subtotal_guard="off", label="x"),
        "sub_strict": replace(F, subtotal_guard="strict", label="x"),
        "literal_10093": replace(F, literal_10093=True, label="x"),
        "no_notes+no_paren": replace(F, notes_guard=False, parenthetical_guard=False, label="x"),
        "no_notes+no_rev": replace(F, notes_guard=False, revenue_exceptions=False, label="x"),
        "no_paren+no_rev": replace(F, parenthetical_guard=False, revenue_exceptions=False, label="x"),
        "legacy+no_period": replace(L, period_filter=False, label="x"),
        "legacy+no_validity": replace(L, member_validity=False, label="x"),
        "legacy+sub_off": replace(L, subtotal_guard="off", label="x"),
        "legacy+sub_strict": replace(L, subtotal_guard="strict", label="x"),
    }


# --------------------------------------------------------------------------- #
# Per-filing properties (for the era analysis)
# --------------------------------------------------------------------------- #

_DEI = {k: re.compile(r"<dei:%s\b[^>]*>([^<]*)</dei:%s>" % (k, k)) for k in (
    "DocumentType", "DocumentPeriodEndDate", "DocumentFiscalYearFocus", "DocumentFiscalPeriodFocus",
    "EntityFilerCategory", "AmendmentFlag", "EntityRegistrantName", "CurrentFiscalYearEndDate")}
_GEN = re.compile(r"<!--\s*([^>]*?(?:Created|Generated|created|generated)[^>]*?)\s*-->")
_COPY = re.compile(r"Copyright\s+(\d{4})")


def filing_props(query: str, fdir: str) -> dict:
    sec = X.split_sections(query)
    inst = sec.get("instance", "") or ""
    p = {"us_gaap_year": D17.us_gaap_year(query)}
    for k, rx in _DEI.items():
        m = rx.search(inst)
        p[k] = m.group(1).strip() if m else None
    head = ""
    d = Path(fdir)
    for f in sorted(d.glob("*.xsd")) + sorted(d.glob("*_pre.xml")):
        try:
            head = f.read_text(encoding="utf-8", errors="replace")[:3000]
        except OSError:
            continue
        if head:
            break
    g = _GEN.search(head)
    c = _COPY.search(head)
    p["software"] = g.group(1) if g else None
    p["copyright_year"] = int(c.group(1)) if c else None
    m = re.search(r"xmlns:dei=\"http://xbrl\.sec\.gov/dei/([^\"]+)\"", inst[:20000])
    p["dei_ns"] = m.group(1) if m else None
    m = re.search(r"xmlns:srt=\"http://fasb\.org/srt/([^\"]+)\"", inst[:20000])
    p["srt_ns"] = m.group(1) if m else None
    return p


# --------------------------------------------------------------------------- #
# Records
# --------------------------------------------------------------------------- #


def rec17(f: dict, local) -> dict:
    per = f["period"]
    return {
        "re": f["rule_element"], "c": f["concept"], "p": [per["start"], per["end"], per["instant"]],
        "t": f["total"], "m": f["member_sum"], "td": [[local(a), local(b)] for a, b in f["total_dims"]],
        "role": f["statement_role"], "ax": local(f["axis"]), "d2": local(f.get("dim2")) if f.get("dim2") else None,
        "sm": local(f.get("sub_member")) if f.get("sub_member") else None, "n": len(f["members"]),
        "mem": [[local(a), b] for a, b in f["members"]][:12], "exc": f.get("exception"),
    }


def run_0117(mod, variants: dict, query: str, fdir: str) -> dict:
    fl = mod.load_filing(query, fdir)
    out = {}
    for name, opts in variants.items():
        out[name] = [rec17(f, mod.local) for f in mod._all_findings(fl, opts, None)]
    return out, fl


def run_0126(query: str, fdir: str) -> list:
    mat = D26.load_material(query, fdir)
    evals, statuses = D26.evaluate(mat)
    orig = D26.statement_cube_uris
    try:
        D26.statement_cube_uris = lambda m: set()  # no L32 cube skip
        evals_nc, _ = D26.evaluate(mat)
    finally:
        D26.statement_cube_uris = orig
    cube_roles = sorted(orig(mat))
    recs = {}

    def key(ev):
        pf = ev.parent_fact
        return (ev.role, ev.parent, pf.context_id if pf else None, str(pf.value) if pf else None, str(ev.addend),
                str(ev.fs_decimals))

    for tag, evs in (("faithful", evals), ("no_cube_skip", evals_nc)):
        for ev in evs:
            if ev.parent_fact is None or ev.addend is None or ev.tolerance is None:
                continue
            k = key(ev)
            r = recs.get(k)
            if r is None:
                pf = ev.parent_fact
                s, e, i = pf.period
                r = {"role": ev.role, "c": ev.parent, "p": [s, e, i], "e": D26._plain(pf.value),
                     "calc": D26._plain(ev.addend), "n_add": ev.n_addends, "n_ch": len(ev.children),
                     "cube_role": ev.role in cube_roles, "fires": {}, "alt_calc": {}}
                recs[k] = r
            if tag == "faithful":
                r["fires"]["faithful"] = ev.fires
                for ak, av in ev.fires_alt.items():
                    r["fires"]["alt_" + ak] = av
                for ak, av in ev.alt_addends.items():
                    r["alt_calc"]["alt_" + ak] = D26._plain(av)
            else:
                r["fires"]["no_cube_skip"] = ev.fires
    out = [r for r in recs.values() if any(r["fires"].values())]
    return out, mat


def run_0015(query: str, fdir: str):
    try:
        ld = D15._load(query, fdir, False)
    except D15.IncompleteInstanceError:
        ld = D15._load(query, fdir, True)
    recs = []
    for r in D15._scan(ld, D15.DEFAULT_VERSION, include_rejected=True):
        v = r.get("value")
        if v is None or not (v < 0) or r.get("rejected") in ("nil", "no-unit", "non-numeric"):
            continue
        key = D15._qname(r["concept"], ld.nsmap, ld.ext_ns)
        listed = [ver for ver in VERSIONS if D15._active_rows(key, ver)]
        reasons = D15.exclusion_reasons([tuple(d) for d in r["dims"]], ld.nsmap, ld.ext_ns)
        per = r["period"]
        recs.append({"c": r["concept"], "key": list(key), "p": [per["start"], per["end"], per["instant"]],
                     "e": r["extracted"], "calc": r["calculated"], "dims": r["dims"], "listed": listed,
                     "reasons": reasons, "pos": r["pos"], "dup": r["duplicates"]})
    return recs, ld


# --------------------------------------------------------------------------- #
# Worker
# --------------------------------------------------------------------------- #


def compute_filing(task):
    split, filing, fdir, cases = task  # cases: [(cid, entry)]
    t0 = time.time()
    out = {"filing": filing, "split": split, "fdir": fdir, "cases": [c for c, _ in cases], "errors": []}
    try:
        e0 = cases[0][1]
        if split == "practice":
            query = C.read_practice_query(e0)
        elif split == "test":
            # The test release ships statement-scoped instances that still end in </xbrl>, so the
            # modules would take them as complete.  Rebuild the hybrid query in memory exactly as
            # the dev hybrid was built: complete instance from the filing, released linkbases.
            from claude_agent.task3_query import assemble_for_case
            q0 = C.read_query(C.TEST_RELEASE, e0)
            query = assemble_for_case({"id": cases[0][0], "query": q0}, filings_dir=C.DEV_FILINGS, mode="hybrid") or q0
            out["test_query_rebuilt"] = query is not q0
        else:
            query = C.read_query(C.DEV_HYBRID, e0)
        out["props"] = filing_props(query, fdir)
        # 0117 CLOSED
        out["f17c"], flC = run_0117(D17, closed_variants(), query, fdir)
        present = {f.concept for f in flC.facts}
        qk = {}
        for cid, e in cases:
            concept = e["concept"]
            if concept not in present:
                alts = [c for c in present if D17.local(c) == D17.local(concept)]
                if len(alts) == 1:
                    concept = alts[0]
            qk[cid] = {"c17": concept, "p": e["period"]}
        # 0117 OPEN
        O = C.load_open_module()
        out["f17o"], _ = run_0117(O, open_variants(O), query, fdir)
        # 0126
        out["f26"], mat = run_0126(query, fdir)
        for cid, e in cases:
            qk[cid]["p26"] = [D26._norm_date(x) for x in e["period"]]
        # 0015
        out["f15"], ld = run_0015(query, fdir)
        for cid, e in cases:
            qk[cid]["k15"] = list(D15._qname(e["concept"], ld.nsmap, ld.ext_ns))
            qk[cid]["p15"] = [D15._norm_date(x) for x in e["period"]]
        out["qk"] = qk
    except Exception as exc:  # noqa: BLE001
        out["errors"].append(f"{type(exc).__name__}: {exc}\n{traceback.format_exc()[-2000:]}")
    out["seconds"] = round(time.time() - t0, 1)
    return out


def tasks_for(split: str):
    idx = {"practice": C.practice_index, "dev": C.dev_index, "test": C.test_index}[split]()
    groups = {}
    for cid, e in sorted(idx.items()):
        groups.setdefault(e["filing"], []).append((cid, e))
    tasks = []
    for filing, cases in sorted(groups.items()):
        fdir = cases[0][1]["fdir"]
        tasks.append((split, filing, fdir, cases))
    return tasks


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="all", choices=["practice", "dev", "test", "all"])
    ap.add_argument("--workers", type=int, default=10)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--only", action="append", help="filing name(s) to run")
    args = ap.parse_args(argv)
    C.SWEEP_OUT.mkdir(parents=True, exist_ok=True)
    splits = ["practice", "dev"] if args.split == "all" else [args.split]
    for split in splits:
        tasks = tasks_for(split)
        if args.only:
            tasks = [t for t in tasks if t[1] in set(args.only)]
        if args.limit:
            tasks = tasks[: args.limit]
        out_path = C.SWEEP_OUT / (f"raw_{split}.jsonl" if not (args.limit or args.only) else f"raw_{split}_partial.jsonl")
        t0 = time.time()
        n = 0
        with open(out_path, "w") as fh, cf.ProcessPoolExecutor(max_workers=args.workers) as ex:
            futs = [ex.submit(compute_filing, t) for t in tasks]
            for fut in cf.as_completed(futs):
                r = fut.result()
                fh.write(json.dumps(r, default=str) + "\n")
                n += 1
                if r["errors"]:
                    print("ERROR", r["filing"], r["errors"][0][:300], flush=True)
                if n % 25 == 0:
                    print(f"  {split}: {n}/{len(tasks)} filings, {round(time.time() - t0)}s", flush=True)
        print(f"{split}: {n} filings -> {out_path} ({round(time.time() - t0)}s)", flush=True)


if __name__ == "__main__":
    main()
