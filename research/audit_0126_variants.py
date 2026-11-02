#!/usr/bin/env python3
"""Variant audit of claude_agent/dqc/dqc_0126.py against XULE details it does not model (review 2026-10-08).

Does not modify the module; re-runs its evaluate() with patched Material and reports, for practice and dev:

  dedup      XULE default duplicate-fact elimination (consistent duplicates dropped, the more precise kept)
  cubes      quote-agnostic has-hypercube detection (X.parse_definition only reads double-quoted attributes)
  alt        cases whose firing depends on the unobservable readings (fires_alt) or on half-up rounding
  expand     fired findings where the old task3_solver grandchild expansion would change the sum
  siblings   which faithful module fires per dev case (0126 / 0015 / 0117), and overlaps

Results on 2026-10-08:
  dedup: 0 changed question evaluations (practice 0/330, dev 0/680)
  cubes: cube-role set incomplete in 1 practice and 56 dev cases' filings; 0 changed answers
  alt: practice DEV_000329 (all_children_counted); dev DEV3_000226/227/228 (min_child_decimals),
       DEV3_000666 (all_children_counted); 0 rounding-mode flips
  expand: practice 0; dev 10 (DEV3_000392/395/400/406/409/413/465/466/605/666), of which
          DEV3_000466/605/666 would not fire at all under expansion
  siblings: dev 464 0126-only, 162 0015-only, 47 0117-only, 0 overlaps, 7 none

Usage: python3 audit_0126_variants.py [dedup|cubes|alt|expand|siblings ...]   (default: all)
"""
from __future__ import annotations

import copy
import json
import re
import sys
from collections import Counter, defaultdict
from decimal import ROUND_HALF_EVEN, ROUND_HALF_UP, Decimal, localcontext

sys.path.insert(0, "/Users/xai/Desktop/FinReason/claude-agent-sdk-benchmark")
from claude_agent import task3_xbrl as X  # noqa: E402
from claude_agent.dqc import dqc_0126 as D  # noqa: E402

ROOT = "/Users/xai/Desktop/FinReason/"
PRACTICE = ROOT + "dsh/task3_inputs.jsonl"
DEV = ROOT + "task3_source_data/ranked/development_inputs_hybrid_v0928.jsonl"
INF = float("inf")


def jl(p):
    return [json.loads(line) for line in open(p, encoding="utf-8") if line.strip()]


def rnd(v: Decimal, d, mode=ROUND_HALF_EVEN) -> Decimal:
    if d == INF:
        return v
    with localcontext() as c:
        c.prec = 200
        return v.quantize(Decimal(1).scaleb(-int(d)), rounding=mode)


def dedup_nondim(nondim):
    """XULE index_model default: same aspects + equal value after rounding to the lower decimals
    -> keep one fact (the more precise); inconsistent duplicates are all kept."""
    out = {}
    for concept, facts in nondim.items():
        groups, order = defaultdict(list), []
        for f in facts:
            k = (f.period, f.unit, f.entity)
            if k not in groups:
                order.append(k)
            saved, match = groups[k], False
            fd = INF if f.decimals is None else f.decimals
            for i, s in enumerate(saved):
                sd = INF if s.decimals is None else s.decimals
                md = min(sd, fd)
                if (s.value if sd == md else rnd(s.value, md)) == (f.value if fd == md else rnd(f.value, md)):
                    match = True
                    if fd > sd:
                        saved[i] = f
            if not match:
                saved.append(f)
        out[concept] = sorted((f for k in order for f in groups[k]), key=lambda f: f.pos)
    return out


_A = re.compile(r"([\w:.-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')")


def _aa(s):
    return {m.group(1): (m.group(2) if m.group(2) is not None else m.group(3)) for m in _A.finditer(s)}


def hypercube_roles_q(text):
    """Quote-agnostic has-hypercube (all/notAll) detection: role -> {hypercube concept}."""
    out = {}
    for a, body in D._link_blocks(text or "", "definitionLink"):
        role, locs = a.get("xlink:role", ""), {}
        for lm in re.finditer(r"<(?:link:)?loc\b(?P<a>[^>]*?)/?>", body, re.S):
            la = _aa(lm.group("a"))
            if "xlink:label" in la and "xlink:href" in la:
                locs[la["xlink:label"]] = X.href_to_concept(la["xlink:href"])
        for am in re.finditer(r"<(?:link:)?definitionArc\b(?P<a>[^>]*?)/?>", body, re.S):
            aa = _aa(am.group("a"))
            if aa.get("xlink:arcrole", "").rsplit("/", 1)[-1] in ("all", "notAll"):
                to = locs.get(aa.get("xlink:to", ""))
                if to:
                    out.setdefault(role, set()).add(to)
    return out


def question_findings(mat):
    q = mat.question
    evals, statuses = D.evaluate(mat, concept=q.concept)
    fs = D._dedupe([ev.to_finding(mat) for ev in evals if ev.fires and D._question_matches(ev, q)])
    return sorted((Decimal(f["extracted"]), Decimal(f["calculated"])) for f in fs), evals


def cases(which):
    for name, path in (("practice", PRACTICE), ("dev", DEV)):
        if which and name not in which:
            continue
        for r in jl(path):
            fdir = D.find_filing_dir(r["query"])
            yield name, r, fdir, D.load_material(r["query"], fdir)


def audit_dedup(which=None):
    changed = Counter()
    for name, r, fdir, mat in cases(which):
        p0, e0 = question_findings(mat)
        m2 = copy.copy(mat)
        m2.nondim = dedup_nondim(mat.nondim)
        p1, e1 = question_findings(m2)
        sig = lambda es: sorted((e.role, str(e.fs_decimals), e.fires, str(e.addend), e.skip_reason) for e in es)
        if p0 != p1 or sig(e0) != sig(e1):
            changed[name] += 1
            print("  dedup changes", r["id"], p0, "->", p1)
    print("dedup: changed question evaluations", dict(changed) or 0)


def audit_cubes(which=None):
    incomplete, changed = Counter(), Counter()
    for name, r, fdir, mat in cases(which):
        sec = X.split_sections(r["query"])
        cubes = hypercube_roles_q(D._read(D._filing_file(fdir, "_def.xml")))
        for role, h in hypercube_roles_q(sec.get("definition", "")).items():
            cubes.setdefault(role, set()).update(h)
        if set(cubes) != set(mat.cubes):
            incomplete[name] += 1
        p0, _ = question_findings(mat)
        m2 = copy.copy(mat)
        m2.cubes = cubes
        p1, _ = question_findings(m2)
        if p0 != p1:
            changed[name] += 1
            print("  cube fix changes", r["id"], p0, "->", p1)
    print("cubes: cases whose cube-role set is incomplete", dict(incomplete), "| changed answers", dict(changed) or 0)


def audit_alt(which=None):
    for name, r, fdir, mat in cases(which):
        q = mat.question
        evals, _ = D.evaluate(mat, concept=q.concept)
        for ev in evals:
            if ev.addend is None or ev.parent_fact is None or not D._question_matches(ev, q) or ev.tolerance is None:
                continue
            for k, v in ev.fires_alt.items():
                if v != ev.fires:
                    print(f"  alt {name} {r['id']} {k}: main={ev.fires} alt={v} parent={ev.parent_fact.value} "
                          f"addend={ev.addend} n={ev.n_addends}/{len(ev.children)}")
            d = ev.decimals_used
            if d is not None and d != INF:
                up = abs(rnd(ev.parent_fact.value, d, ROUND_HALF_UP) - rnd(ev.addend, d, ROUND_HALF_UP)) > ev.tolerance
                if up != ev.fires:
                    print(f"  rounding-mode flip {name} {r['id']}")


def _expand(mat, net, child, align, depth=0, seen=()):
    if depth > 4 or child in seen or child not in net.children:
        return None
    tot, found = Decimal(0), 0
    for c, w in net.children[child]:
        cs = [f for f in mat.nondim.get(c, []) if f.alignment == align]
        v = cs[0].value if cs else _expand(mat, net, c, align, depth + 1, seen + (child,))
        if v is not None:
            tot, found = tot + w * v, found + 1
    return tot if found else None


def audit_expand(which=None):
    for name, r, fdir, mat in cases(which):
        q = mat.question
        evals, _ = D.evaluate(mat, concept=q.concept)
        for ev in evals:
            if not ev.fires or not D._question_matches(ev, q):
                continue
            net, extra, k = mat.calc[ev.role], Decimal(0), 0
            for c, w, f in ev.children:
                if f is None:
                    v = _expand(mat, net, c, ev.parent_fact.alignment)
                    if v is not None:
                        extra, k = extra + w * v, k + 1
            if k:
                new = ev.addend + extra
                fires = D.tolerance_for_decimals(ev.parent_fact.value, ev.parent_fact.decimals, new, None,
                                                 ev.n_addends + k + 1)[0]
                print(f"  expand {name} {r['id']} faithful={ev.addend} expanded={new} fires_if_expanded={fires}")


def audit_siblings(which=None):
    from claude_agent.dqc import dqc_0015 as D15, dqc_0117 as D17
    part = Counter()
    for r in jl(DEV):
        fdir = D.find_filing_dir(r["query"])
        key = (bool(D.findings_0126(r["query"], fdir)), bool(D15.findings_0015(r["query"], fdir)),
               bool(D17.findings_0117(r["query"], fdir)))
        part[key] += 1
        if not any(key):
            print("  no faithful module fires:", r["id"])
    print("siblings (0126, 0015, 0117) -> cases:", dict(part))


if __name__ == "__main__":
    todo = sys.argv[1:] or ["dedup", "cubes", "alt", "expand", "siblings"]
    for t in todo:
        print(f"== {t}")
        {"dedup": audit_dedup, "cubes": audit_cubes, "alt": audit_alt, "expand": audit_expand,
         "siblings": audit_siblings}[t]()
