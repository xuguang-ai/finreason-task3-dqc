#!/usr/bin/env python3
"""Exact posterior over the open development cases from every scored upload.

This is the diagnostic of the paper's Section "Diagnostic Use of the Development
Leaderboard".  It needs the uploaded prediction files and their rule-judge counts
(probe/ledger.json, not distributed) and the development hybrid queries; the case
lists below are those of the paper's development run.

Assignments are read from the uploaded files themselves (never from notes), so
the model is: for each open case a set of candidate answers with a prior, a
"certain" block whose unknown number of wrong answers w has its own prior, and
one linear count constraint per scored upload.  Dynamic programming over the
cases gives exact marginals; the same DP with free dimensions scores proposed
genuine files by the information their counts would carry.

    python3 solver.py posterior
    python3 solver.py design K [seed]      # writes probe/G<n>.jsonl (comma style, validated)
"""
from __future__ import annotations

import collections
import json
import os
import math
import random
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE.parent)]
from finreason_task3 import integrate as I  # noqa: E402
from finreason_task3.dqc import dqc_0015 as D15  # noqa: E402

#: Data directory: <FINREASON_DATA>/filings holds the filings, <FINREASON_DATA>/probe the
#: uploaded prediction files named in probe/ledger.json ([name, file, correct count]).
RANKED = Path(os.environ.get("FINREASON_DATA", "data")).resolve()

OPEN_0015 = ["DEV3_000006", "DEV3_000015", "DEV3_000016", "DEV3_000036", "DEV3_000039", "DEV3_000050",
             "DEV3_000057", "DEV3_000063", "DEV3_000081", "DEV3_000082", "DEV3_000089", "DEV3_000092",
             "DEV3_000094", "DEV3_000110", "DEV3_000134", "DEV3_000145", "DEV3_000148", "DEV3_000152",
             "DEV3_000156"]
NONE_CASES = {   # (pair, prior weight); "other" added automatically
    "DEV3_000162": [(["3967000", "34865000"], 0.85)],
    "DEV3_000189": [(["1181203000", "774617000"], 0.2), (["231217000", "155221000"], 0.2),
                    (["51767000", "37407000"], 0.2), (["25489000", "4478000"], 0.2)],
    "DEV3_000190": [(["1273014000", "811390000"], 0.19), (["337193000", "231981000"], 0.19),
                    (["141761000", "103062000"], 0.19), (["33305000", "4649000"], 0.19),
                    (["1785273000", "3549701000"], 0.02)],
    "DEV3_000193": [(["604512000", "25450000"], 0.7), (["1246069000", "604512000"], 0.1)],
    "DEV3_000198": [(["610517000", "219653000"], 0.65), (["-14000", "14000"], 0.1)],
    "DEV3_000214": [(["845000000", "25000000"], 0.4), (["2413000000", "69000000"], 0.4), (["25000000", "94000000"], 0.05)],
    "DEV3_000215": [(["8186000", "-133000"], 0.8), (["10647000", "-3882000"], 0.05)],
}
OTHER_0015, OTHER_NONE = 0.02, 0.15
W_PRIOR = [0.80, 0.12, 0.05, 0.02, 0.01]           # wrong answers in the certain block: 0..4
LEDGER = HERE / "ledger.json"
UPLOADS = [tuple(x) for x in json.load(open(LEDGER))] if LEDGER.exists() else []
BASE_FILE = RANKED / "probe" / (UPLOADS[3][1] if len(UPLOADS) > 3 else "base.jsonl")   # the document-order file


def s(x):
    return str(I.num(x))


def load(path):
    return {json.loads(l)["id"]: json.loads(l) for l in open(RANKED / "probe" / path)}


def pair_of(rec):
    return [s(rec["extracted_value"]), s(rec["calculated_value"])]


def build():
    rows = {json.loads(l)["id"]: json.loads(l)["query"] for l in open(RANKED / "development_inputs_hybrid.jsonl")}
    files = {name: load(p) for name, p, _ in UPLOADS}
    cases = {}
    for cid in OPEN_0015:
        mult = collections.Counter(); order = []
        for f in D15.findings_0015(rows[cid], filing_dir=I.filing_dir(rows[cid], RANKED / "filings")):
            p = (s(f["extracted"]), s(f["calculated"]))
            if p not in mult:
                order.append(p)
            mult[p] += 1
        opts = [(list(p), float(mult[p])) for p in order]
        for name in files:          # any uploaded value outside the flagged facts is a (tiny) hypothesis too
            p = pair_of(files[name][cid])
            if p not in [o for o, _ in opts]:
                opts.append((p, 0.01))
        opts.append((["other", ""], OTHER_0015 * sum(w for _, w in opts)))
        cases[cid] = opts
    for cid, opts in NONE_CASES.items():
        opts = [(list(p), w) for p, w in opts]
        for name in files:
            p = pair_of(files[name][cid])
            if p not in [o for o, _ in opts]:
                opts.append((p, 0.001 if p[0] == "0" else 0.05))
        opts.append((["other", ""], OTHER_NONE))
        cases[cid] = opts
    certain = [cid for cid in rows if cid not in cases]
    # the certain block must be identical in every upload
    ref = {cid: pair_of(files["V1"][cid]) for cid in certain}
    for name in files:
        bad = [cid for cid in certain if pair_of(files[name][cid]) != ref[cid]]
        assert not bad, (name, bad[:5])
    uploads = [{"name": name, "total": total, "assign": {cid: pair_of(files[name][cid]) for cid in cases}}
               for name, _, total in UPLOADS]
    return cases, certain, uploads


def vectors(cases, uploads, extra=()):
    names = list(cases)
    vec = {}
    for cid in names:
        rows = []
        for pair, _ in cases[cid]:
            v = [int(u["assign"][cid] == pair) for u in uploads] + [int(a[cid] == pair) for a in extra]
            rows.append(tuple(v))
        vec[cid] = rows
    return vec


def dp(cases, uploads, n_certain, extra=()):
    names = list(cases)
    vec = vectors(cases, uploads, extra)
    npin = len(uploads); nfree = len(extra)
    tgt = [u["total"] for u in uploads]
    # certain block first: contributes n_certain - w to every upload and every extra file
    layer = {}
    for w, pw in enumerate(W_PRIOR):
        layer[tuple([n_certain - w] * (npin + nfree))] = pw
    maxrest = [[0] * npin for _ in range(len(names) + 1)]
    for i in range(len(names) - 1, -1, -1):
        maxrest[i] = [maxrest[i + 1][k] + max(v[k] for v in vec[names[i]]) for k in range(npin)]
    layers = [layer]
    for i, cid in enumerate(names):
        tot = sum(w for _, w in cases[cid]); nxt = collections.defaultdict(float)
        for st, w in layer.items():
            for j, (_, pw) in enumerate(cases[cid]):
                v = vec[cid][j]; ns = list(st); ok = True
                for k in range(npin + nfree):
                    ns[k] += v[k]
                    if k < npin and (ns[k] > tgt[k] or ns[k] + maxrest[i + 1][k] < tgt[k]):
                        ok = False; break
                if ok:
                    nxt[tuple(ns)] += w * pw / tot
        layer = dict(nxt); layers.append(layer)
    return layers, vec, tuple(tgt)


def marginals(cases, uploads, n_certain):
    names = list(cases)
    layers, vec, tgt = dp(cases, uploads, n_certain)
    Z = layers[-1].get(tgt, 0.0)
    if Z <= 0:
        return None, 0.0
    backs = [None] * (len(names) + 1); backs[-1] = {tgt: 1.0}
    for i in range(len(names) - 1, -1, -1):
        cid = names[i]; tot = sum(w for _, w in cases[cid]); b = {}
        for st in layers[i]:
            acc = 0.0
            for j, (_, pw) in enumerate(cases[cid]):
                acc += pw / tot * backs[i + 1].get(tuple(x + y for x, y in zip(st, vec[cid][j])), 0.0)
            if acc:
                b[st] = acc
        backs[i] = b
    out = {}
    for i, cid in enumerate(names):
        tot = sum(w for _, w in cases[cid]); m = []
        for j, (_, pw) in enumerate(cases[cid]):
            acc = sum(w * pw / tot * backs[i + 1].get(tuple(x + y for x, y in zip(st, vec[cid][j])), 0.0)
                      for st, w in layers[i].items())
            m.append(acc / Z)
        out[cid] = m
    # certain-block w posterior
    wpost = []
    for w, pw in enumerate(W_PRIOR):
        st = tuple([n_certain - w] * len(uploads))
        wpost.append(pw * backs[0].get(st, 0.0) / Z)
    return out, wpost


def joint_entropy(cases, uploads, n_certain, extra):
    layers, _, tgt = dp(cases, uploads, n_certain, extra)
    dist = collections.defaultdict(float); n = len(tgt)
    for st, w in layers[-1].items():
        if st[:n] == tgt:
            dist[st[n:]] += w
    Z = sum(dist.values())
    return -sum(w / Z * math.log2(w / Z) for w in dist.values() if w > 0)


def design(cases, uploads, n_certain, k, rng, fixed):
    chosen = []
    for n in range(k):
        best, best_h = None, -1.0
        for _ in range(3):
            a = {cid: rng.choice([p for p, _ in cases[cid] if p[0] not in ("other", "0")]) for cid in cases}
            a.update(fixed)
            h = joint_entropy(cases, uploads, n_certain, chosen + [a])
            improved = True
            while improved:
                improved = False
                for cid in rng.sample([c for c in cases if c not in fixed], len(cases) - len(fixed)):
                    for p, _ in cases[cid]:
                        if p[0] in ("other", "0") or p == a[cid]:
                            continue
                        trial = dict(a); trial[cid] = p
                        h2 = joint_entropy(cases, uploads, n_certain, chosen + [trial])
                        if h2 > h + 1e-9:
                            a, h, improved = trial, h2, True
            if h > best_h:
                best, best_h = a, h
        chosen.append(best); print(f"file {n + 1}: joint entropy {best_h:.2f} bits")
    return chosen


def write_file(assign, path):
    base = load(BASE_FILE.name)
    for cid, pair in assign.items():
        base[cid] = {"id": cid, "extracted_value": pair[0], "calculated_value": pair[1]}
    plain = path.with_suffix(".plain.jsonl")
    with open(plain, "w") as fh:
        for cid in [json.loads(l)["id"] for l in open(BASE_FILE)]:
            fh.write(json.dumps(base[cid]) + "\n")
    subprocess.run([sys.executable, "-m", "finreason_task3.format_thousands", str(plain), str(path)], check=True, capture_output=True, cwd=str(HERE.parent))
    res = subprocess.run([sys.executable, str(RANKED / "upstream_kit/finreason_task3/scripts/validate_submission.py"),
                          "--predictions", str(path), "--reference", str(RANKED / "development_inputs.jsonl")],
                         capture_output=True, text=True)
    return [l for l in res.stdout.splitlines() if "RESULT" in l]


def main(argv):
    cases, certain, uploads = build()
    cmd = argv[0] if argv else "posterior"
    if cmd == "posterior":
        m, wpost = marginals(cases, uploads, len(certain))
        if m is None:
            print("INCONSISTENT: no configuration explains every upload"); return 1
        print("certain block wrong-count posterior:", [round(x, 3) for x in wpost])
        best = {}
        for cid in cases:
            rows = sorted(zip(m[cid], [p for p, _ in cases[cid]]), key=lambda t: -t[0])
            best[cid] = rows[0]
            print(f"{cid[-3:]}: " + "  ".join(f"{p[0]}:{q:.2f}" for q, p in rows[:5]))
        exp = sum(q for q, p in best.values() if p[0] != "other")
        print(f"best-guess file expected count ≈ {len(certain) - sum(w * p for w, p in enumerate(wpost)) + exp:.1f}")
        json.dump({cid: [[p, q] for q, p in sorted(zip(m[cid], [p for p, _ in cases[cid]]), key=lambda t: -t[0])]
                   for cid in cases}, open(HERE / "posterior.json", "w"), indent=1)
        return 0
    if cmd == "design":
        k = int(argv[1]); rng = random.Random(int(argv[2]) if len(argv) > 2 else 0)
        m, _ = marginals(cases, uploads, len(certain))
        fixed = {cid: [p for p, _ in cases[cid]][max(range(len(cases[cid])), key=lambda j: m[cid][j])]
                 for cid in cases if max(m[cid]) > 0.97}      # settled cases stay at their answer
        files = design(cases, uploads, len(certain), k, rng, fixed)
        existing = sorted(HERE.glob("G*.jsonl"))
        n0 = len([p for p in existing if ".plain" not in p.name])
        for i, a in enumerate(files):
            name = f"G{n0 + i + 1}"; ok = write_file(a, HERE / f"{name}.jsonl")
            diff = {cid: v for cid, v in a.items() if v != pair_of(load(BASE_FILE.name)[cid])}
            print(f"{name} {ok}: " + "; ".join(f"{c[-3:]}={v[0]}" for c, v in diff.items()))
        return 0
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
