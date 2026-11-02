#!/usr/bin/env python3
"""Independent cross-check of claude_agent/dqc/dqc_0126.py (review 2026-10-08).

Re-implements DQC_US_0126 from src_2026_DQC_0126.xule with ElementTree (QName-based, quote-agnostic,
XULE default duplicate-fact elimination), sharing no parsing code with dqc_0126/task3_xbrl, and compares
the fired (extracted, calculated) pairs for the questioned concept/period on practice (vs gold) and dev.
Result on 2026-10-08: practice 330/330 identical, gold 101/101, 0 false positives; dev 680/680 identical.
Usage: python3 crosscheck_0126_independent.py
"""
import xml.etree.ElementTree as ET
import re, glob, os
from collections import defaultdict, Counter
from decimal import Decimal, ROUND_HALF_EVEN, localcontext, InvalidOperation

XLINK = "{http://www.w3.org/1999/xlink}"
LINK = "{http://www.xbrl.org/2003/linkbase}"
XBRLI = "{http://www.xbrl.org/2003/instance}"
XBRLDI = "{http://xbrl.org/2006/xbrldi}"
XSI = "{http://www.w3.org/2001/XMLSchema-instance}"
XS = "{http://www.w3.org/2001/XMLSchema}"
INF = float("inf")

def q(v, d):
    if d == INF: return v
    with localcontext() as c:
        c.prec = 200
        return v.quantize(Decimal(1).scaleb(-int(d)), rounding=ROUND_HALF_EVEN)

def nsmap_of(path):
    ns = {}
    for ev, (p, u) in ET.iterparse(path, events=("start-ns",)):
        ns.setdefault(p, u)
    return ns

class Filing:
    def __init__(self, fdir):
        self.fdir = fdir
        f = lambda suf: (sorted(glob.glob(os.path.join(fdir, "*" + suf))) or [None])[0]
        self.xsd = f(".xsd"); self.inst = f("_htm.xml") or next((p for p in sorted(glob.glob(os.path.join(fdir, "*.xml"))) if not re.search(r"_(cal|def|lab|pre)\.xml$", p)), None)
        self.cal = f("_cal.xml"); self.pre = f("_pre.xml"); self.dfn = f("_def.xml")
        self._schema(); self._instance(); self._linkbases()

    def _schema(self):
        self.role_def = {}; self.ext_ids = {}; self.tns = None
        root = ET.parse(self.xsd).getroot()
        self.tns = root.get("targetNamespace")
        for rt in root.iter(LINK + "roleType"):
            d = rt.find(LINK + "definition")
            self.role_def[rt.get("roleURI")] = (d.text or "").strip() if d is not None else None
        for el in root.iter(XS + "element"):
            if el.get("id") and el.get("name"):
                self.ext_ids[el.get("id")] = (self.tns, el.get("name"), el.get("{http://www.xbrl.org/2003/instance}periodType"))

    def concept_of_href(self, href):
        file, frag = href.split("#", 1)
        base = os.path.basename(file)
        if base == os.path.basename(self.xsd) or not file.startswith("http"):
            t = self.ext_ids.get(frag)
            if t: return (t[0], t[1])
        # standard taxonomy: us-gaap-2024.xsd -> namespace from instance with same family/year
        m = re.match(r"([a-z-]+?)-(\d{4})", base)
        pre, local = frag.split("_", 1) if "_" in frag else (None, frag)
        if m:
            fam, yr = m.group(1), m.group(2)
            for p, u in self.ns.items():
                if u.rstrip("/").endswith("/%s/%s" % (fam, yr)) or u.rstrip("/").endswith("/%s-%s" % (fam, yr)):
                    return (u, local)
        if pre in self.ns: return (self.ns[pre], local)
        return ("?" + (pre or ""), local)

    def _instance(self):
        self.ns = nsmap_of(self.inst)
        root = ET.parse(self.inst).getroot()
        self.contexts = {}; self.units = {}
        for c in root.iter(XBRLI + "context"):
            ent = c.find(XBRLI + "entity"); ident = ent.find(XBRLI + "identifier")
            dims = len(list(c.iter(XBRLDI + "explicitMember"))) + len(list(c.iter(XBRLDI + "typedMember")))
            per = c.find(XBRLI + "period")
            s = per.find(XBRLI + "startDate"); e = per.find(XBRLI + "endDate"); i = per.find(XBRLI + "instant")
            norm = lambda x: x.text.strip()[:10] if x is not None else None
            self.contexts[c.get("id")] = dict(entity=(ident.get("scheme"), ident.text.strip()), dims=dims,
                                              period=(norm(s), norm(e), norm(i)))
        for u in root.iter(XBRLI + "unit"):
            def resolve(m):
                t = m.text.strip(); p, l = t.split(":", 1) if ":" in t else ("", t)
                return "{%s}%s" % (self.ns.get(p, p), l)
            div = u.find(XBRLI + "divide")
            if div is not None:
                num = tuple(sorted(resolve(m) for m in div.find(XBRLI + "unitNumerator").iter(XBRLI + "measure")))
                den = tuple(sorted(resolve(m) for m in div.find(XBRLI + "unitDenominator").iter(XBRLI + "measure")))
            else:
                num = tuple(sorted(resolve(m) for m in u.iter(XBRLI + "measure"))); den = ()
            self.units[u.get("id")] = (num, den)
        self.facts = []
        pos = 0
        for el in root:
            cref = el.get("contextRef")
            if cref is None: continue
            pos += 1
            tag = el.tag; ns_, local = tag[1:].split("}")
            nil = el.get(XSI + "nil") in ("true", "1")
            ctx = self.contexts.get(cref)
            if ctx is None: continue
            uref = el.get("unitRef")
            dec = el.get("decimals")
            decv = None if dec is None else (INF if dec.strip() == "INF" else int(dec))
            val = None
            if not nil and uref is not None:
                try: val = Decimal((el.text or "").strip())
                except InvalidOperation: val = None
            self.facts.append(dict(concept=(ns_, local), nil=nil, ctx=ctx, cref=cref, unit=self.units.get(uref) if uref else None,
                                   numeric=uref is not None, dec=decv, value=val, text=(el.text or ""), pos=pos))
        # XULE index_model default duplicate elimination
        groups = defaultdict(list); order = []
        for f in self.facts:
            k = (f["concept"], f["ctx"]["period"], f["unit"], f["ctx"]["entity"], f["cref"] if f["ctx"]["dims"] else "")
            if k not in groups: order.append(k)
            saved = groups[k]; match = False
            for idx, s in enumerate(saved):
                if f["numeric"]:
                    if s["value"] is None or f["value"] is None:
                        same = (s["value"] is None and f["value"] is None)
                    else:
                        sd = s["dec"] if s["dec"] is not None else INF; fd = f["dec"] if f["dec"] is not None else INF
                        md = min(sd, fd)
                        same = (s["value"] if sd == md else q(s["value"], md)) == (f["value"] if fd == md else q(f["value"], md))
                    if same:
                        match = True
                        if (f["dec"] if f["dec"] is not None else INF) > (s["dec"] if s["dec"] is not None else INF): saved[idx] = f
                else:
                    if s["text"] == f["text"]: match = True
            if not match: saved.append(f)
        self.dfacts = [f for k in order for f in groups[k]]
        self.nondim = defaultdict(list)
        for f in self.dfacts:
            if f["numeric"] and not f["nil"] and f["value"] is not None and f["ctx"]["dims"] == 0:
                self.nondim[f["concept"]].append(f)
        dei = [f for f in self.facts if f["concept"][1] == "DocumentPeriodEndDate"]
        self.dei = None
        if dei:
            s, e, i = dei[0]["ctx"]["period"]
            self.dei = (s, e if e else i)
        self.has_ch11 = any(f["concept"][1] == "ReorganizationUnderChapter11OfUSBankruptcyCodeDisclosureTextBlock" for f in self.facts)

    def _links(self, path, linktag, arctag):
        out = defaultdict(list)
        if not path: return out
        root = ET.parse(path).getroot()
        for link in root.iter(LINK + linktag):
            role = link.get(XLINK + "role")
            locs = {}
            for loc in link.iter(LINK + "loc"):
                locs[loc.get(XLINK + "label")] = self.concept_of_href(loc.get(XLINK + "href"))
            for arc in link.iter(LINK + arctag):
                out[role].append((arc.get(XLINK + "arcrole"), locs.get(arc.get(XLINK + "from")), locs.get(arc.get(XLINK + "to")),
                                  arc.get("weight"), arc.get("use"), arc.get("priority")))
        return out

    def _linkbases(self):
        pre = self._links(self.pre, "presentationLink", "presentationArc")
        self.pres_roles = {r for r, arcs in pre.items() if any(a[0].endswith("/parent-child") for a in arcs)}
        cal = self._links(self.cal, "calculationLink", "calculationArc")
        self.calc = {}
        for r, arcs in cal.items():
            ch = defaultdict(list)
            prohib = {(a[1], a[2]) for a in arcs if a[0].endswith("summation-item") and a[4] == "prohibited"}
            for ar, fr, to, w, use, pr in arcs:
                if not ar.endswith("summation-item") or use == "prohibited" or (fr, to) in prohib: continue
                wt = Decimal(w if w else "1")
                if (to, wt) not in ch[fr]: ch[fr].append((to, wt))
            if ch: self.calc[r] = ch
        dfn = self._links(self.dfn, "definitionLink", "definitionArc")
        self.cubes = defaultdict(set)
        for r, arcs in dfn.items():
            for ar, fr, to, *_ in arcs:
                if ar.endswith("/all") or ar.endswith("/notAll"): self.cubes[r].add(to)

SOI = {"ScheduleOfInvestmentsTable","SummaryOfInvestmentHoldingsTable","InvestmentsSoldNotYetPurchasedTable","OpenOptionContractsWrittenTable","OpenFuturesContractTable","OpenForwardForeignCurrencyContractTable","OpenSwapContractTable"}
PRES_X = ("parenthetical","equity","deficit","stockholders","capital","investment","change","shareholder","convertible","preferred","temporaryequity","redeemable","netproceedsfromallsources","membersinterest","membershipinterest","highlights","employee","ebp")
CUBE_X = ("parenthetical","equity","deficit","stockholders","capital","investment","changes","shareholder","convertible","preferred","temporaryequity","redeemable","netproceedsfromallsources","membersinterest")

def evaluate(fl, concept_filter=None):
    """Return list of findings dicts: role, concept, period, extracted, calculated, fires, n, children."""
    cube_uris = set()
    for r, hcs in fl.cubes.items():
        d = fl.role_def.get(r)
        if not d or "- Statement -" not in d: continue
        if any(t in r.lower() for t in CUBE_X): continue
        if "schedule iii" in d.lower() or "schedule iv" in d.lower(): continue
        if all(h is not None and h[1] in SOI and "us-gaap" in h[0] for h in hcs): continue
        cube_uris.add(r)
    res = []
    for r in sorted(fl.pres_roles):
        d = fl.role_def.get(r)
        if not d or "- Statement -" not in d: continue
        if any(t in r.lower() for t in PRES_X): continue
        if any(t in d.lower() for t in ("schedule iii","schedule iv","net worth")): continue
        if r in cube_uris: continue
        net = fl.calc.get(r)
        if not net: continue
        parents = list(net.keys())
        decs = [f["dec"] for p in parents for f in fl.nondim.get(p, [])]
        if not decs: continue
        cnt = Counter(decs); top = max(cnt.values()); cands = [k for k, v in cnt.items() if v == top]
        fsd = cands[0]
        for p in parents:
            if concept_filter and p != concept_filter: continue
            pf_all = fl.nondim.get(p, [])
            if not pf_all: continue
            ptype = "instant" if pf_all[0]["ctx"]["period"][2] else "duration"
            ds, de = fl.dei if fl.dei else (None, None)
            for pf in pf_all:
                s, e, i = pf["ctx"]["period"]
                cur = (i == de) if ptype == "instant" else (s == ds and e == de and i is None)
                if not cur or pf["dec"] != fsd: continue
                align = (pf["ctx"]["period"], pf["unit"], pf["ctx"]["entity"])
                comps = []
                for c, w in net[p]:
                    cs = [f for f in fl.nondim.get(c, []) if (f["ctx"]["period"], f["unit"], f["ctx"]["entity"]) == align]
                    pick = next((f for f in cs if f["dec"] == fsd), None) or next((f for f in cs if f["dec"] is not None and f["dec"] >= fsd), None) or next((f for f in cs if f["dec"] is not None and f["dec"] < fsd), None)
                    comps.append((c, w, pick))
                used = [(c, w, f) for c, w, f in comps if f is not None]
                if not used: continue
                if fl.has_ch11 and any(c[1] == "LiabilitiesSubjectToCompromise" for c, _, _ in comps): continue
                addend = sum((w * f["value"] for _, w, f in used), Decimal(0))
                d1 = pf["dec"]
                tol = Decimal(0) if d1 == INF else Decimal(10) ** int(-d1) * (len(used) + 1)
                fires = abs(q(pf["value"], d1) - q(addend, d1)) > tol
                res.append(dict(role=r, concept=p, period=pf["ctx"]["period"], extracted=pf["value"], calculated=addend,
                                fires=fires, n=len(used), nchildren=len(comps), fsd=fsd, tie=len(cands) > 1))
    return res


def main():
    import sys, json, time
    sys.path.insert(0, "/Users/xai/Desktop/FinReason/claude-agent-sdk-benchmark")
    from claude_agent import task3_xbrl as X
    from claude_agent.dqc import dqc_0126 as D
    from decimal import Decimal
    ROOT = "/Users/xai/Desktop/FinReason/"
    def jl(p): return [json.loads(l) for l in open(p) if l.strip()]
    def N(s): return Decimal(str(s).replace(",","").strip())
    gold = {r["id"]: r for r in jl(ROOT+"task3_source_data/curated/public_dev_curated.jsonl")}
    cache = {}
    out = {}
    t0 = time.time()
    for name, path in (("practice", ROOT+"dsh/task3_inputs.jsonl"), ("dev", ROOT+"task3_source_data/ranked/development_inputs_hybrid_v0928.jsonl")):
        stats = {"cases": 0, "indep_fires": 0, "module_fires": 0, "agree_pairs": 0, "disagree": []}
        if name == "practice": stats.update(gold_hit_indep=0, gold_hit_mod=0, fp_indep=0)
        for r in jl(path):
            qy = r["query"]; fdir = D.find_filing_dir(qy)
            qq = X.parse_question(qy)
            if fdir is None: stats["disagree"].append((r["id"], "no filing dir")); continue
            key = str(fdir)
            try:
                fl = cache.get(key) or Filing(str(fdir)); cache[key] = fl
            except Exception as e:
                stats["disagree"].append((r["id"], "parse error %r" % e)); continue
            # map question concept prefix:local -> (ns, local)
            pre, loc = qq.concept.split(":", 1)
            cq = (fl.ns.get(pre), loc)
            res = [x for x in evaluate(fl, cq) if x["fires"]]
            per = qq.period_key
            res = [x for x in res if (x["period"] == (per[0], per[1], None) if per[2] is None else x["period"][2] == per[2])]
            ip = sorted({(x["extracted"], x["calculated"]) for x in res})
            mp = sorted({(N(f["extracted"]), N(f["calculated"])) for f in D.findings_0126(qy, fdir)})
            stats["cases"] += 1
            stats["indep_fires"] += bool(ip); stats["module_fires"] += bool(mp)
            if ip == mp: stats["agree_pairs"] += 1
            else: stats["disagree"].append((r["id"], [tuple(map(str,p)) for p in ip], [tuple(map(str,p)) for p in mp]))
            if name == "practice":
                a = gold[r["id"]]["answer"]; g = (N(a["extracted_value"]), N(a["calculated_value"]))
                if r["dqc_id"] == "DQC_US_0126":
                    stats["gold_hit_indep"] += g in ip; stats["gold_hit_mod"] += g in mp
                elif ip: stats["fp_indep"] += 1
        out[name] = stats
        print(name, {k: v for k, v in stats.items() if k != "disagree"}, "disagreements:", len(stats["disagree"]))
        for d in stats["disagree"][:30]: print("   ", d)
    print("secs", time.time() - t0)


if __name__ == '__main__':
    main()
