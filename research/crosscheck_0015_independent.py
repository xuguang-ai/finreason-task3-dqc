#!/usr/bin/env python3
"""Independent re-implementation of DQC_US_0015, used to cross-check claude_agent/dqc/dqc_0015.py.

It shares NO code and NO transcribed constants with dqc_0015.py or task3_xbrl.py:
  * $NON_NEG_ITEMS is read from DQC_US_0015__DQC_0015_ListOfElements.xlsx directly (not from the
    generated dqc_0015_items.json), by header name; a row is listed at release V when
    originalReleaseVersion <= V and it has no removalRelease <= V. Its QName family is the
    union of the "namespace" column and the prefix of the qualified name in the "Deprecated"
    column (no prefix = us-gaap).
  * The exclusion sets are read from DQC_US_0015__DQC_0015_MemberExclusions.xlsx. The namespaces
    are taken from the prefixes that the commented-out literals in lib_2026_constant-us-gaap.xule
    give (srt: for the ConsolidatedEntitiesAxis pair after the 2018 SRT move). The explicit 2026
    additions (`+ set(...)`) are parsed out of the active constant definitions in that file.
  * The instance is parsed with xml.etree, with in-scope namespace declarations tracked per
    element (QName values resolved against their own element's scope), Clark QNames.
  * Question, sections, duplicate elimination, unit filter and exclusions are written afresh.

    python3 crosscheck_0015_independent.py [--version 29]     # practice + dev, prints agreement

Used by validate_0015.py (``crosscheck()``).
"""
from __future__ import annotations

import argparse
import collections
import hashlib
import io
import json
import re
import sys
import xml.etree.ElementTree as ET
from decimal import Decimal, InvalidOperation
from pathlib import Path

HERE = Path(__file__).resolve().parent
ELEMENTS_XLSX = HERE / "DQC_US_0015__DQC_0015_ListOfElements.xlsx"
MEMBERS_XLSX = HERE / "DQC_US_0015__DQC_0015_MemberExclusions.xlsx"
CONSTANTS_XULE = HERE / "lib_2026_constant-us-gaap.xule"

XBRLI = "http://www.xbrl.org/2003/instance"
XBRLDI = "http://xbrl.org/2006/xbrldi"
LINK = "http://www.xbrl.org/2003/linkbase"
XSI_NIL = "{http://www.w3.org/2001/XMLSchema-instance}nil"
NON_FACT_NS = {XBRLI, XBRLDI, LINK}
INF = float("inf")


# --------------------------------------------------------------------------- #
# Constants from the published sources
# --------------------------------------------------------------------------- #


def load_items():
    """{(family, local): [(added, removed_or_None), ...]} from the ListOfElements sheet."""
    import openpyxl

    wb = openpyxl.load_workbook(ELEMENTS_XLSX, read_only=True, data_only=True)
    rows = list(wb["DQC_0015 NonNeg"].iter_rows(values_only=True))
    hdr = {h: i for i, h in enumerate(rows[1]) if isinstance(h, str)}
    i_add, i_id, i_rm = hdr["originalReleaseVersion"], hdr["ruleElementID"], hdr["removalRelease"]
    i_ns, i_name, i_qual = hdr["namespace"], hdr["elementName"], hdr["Deprecated"]
    items = collections.defaultdict(list)
    for r in rows[2:]:
        if r[i_id] is None or r[i_name] is None:
            continue
        local = str(r[i_name]).strip()
        fams = {str(r[i_ns]).strip()}
        qual = r[i_qual]
        fams.add(str(qual).split(":", 1)[0].strip() if isinstance(qual, str) and ":" in qual else "us-gaap")
        added = int(r[i_add])
        removed = None if r[i_rm] in (None, "") else int(r[i_rm])
        for fam in fams:
            items[(fam, local)].append((added, removed))
    return dict(items)


def listed(items, key, version):
    return any(a <= version and (rm is None or version < rm) for a, rm in items.get(key, ()))


def _active_xule(text):
    """The .xule text with /* ... */ and /** ... **/ comment blocks removed."""
    return re.sub(r"/\*.*?\*/", "", text, flags=re.S)


def _constant_body(active, name):
    m = re.search(r"constant\s+\$" + re.escape(name) + r"\s*=(.*?)(?=\n\s*constant\s+\$|\Z)", active, re.S)
    return m.group(1) if m else ""


def _plus_set_items(body):
    """Items of every top-level ``+ set(...)`` in a constant definition."""
    out = []
    for m in re.finditer(r"\+\s*set\(", body):
        depth, i = 1, m.end()
        while depth and i < len(body):
            depth += {"(": 1, ")": -1}.get(body[i], 0)
            i += 1
        inner = body[m.end():i - 1]
        parts, depth, cur = [], 0, ""
        for ch in inner:
            if ch == "," and depth == 0:
                parts.append(cur.strip())
                cur = ""
                continue
            depth += {"(": 1, ")": -1}.get(ch, 0)
            cur += ch
        if cur.strip():
            parts.append(cur.strip())
        out.extend(parts)
    return out


def _xule_qname(item):
    """A XULE QName literal -> (family, local); unprefixed = us-gaap (the rule set's default)."""
    m = re.match(r"qname\(\s*\$EXTENSION_NS\s*,\s*'([^']+)'\s*\)", item)
    if m:
        return ("EXT", m.group(1))
    if ":" in item:
        p, l = item.split(":", 1)
        return (p.strip(), l.strip())
    return ("us-gaap", item.strip())


def load_exclusions():
    import openpyxl

    text = CONSTANTS_XULE.read_text(encoding="utf-8", errors="replace")
    # prefixes the (commented-out) 0015 literal sets give to names, e.g. srt:ConsolidatedEntitiesAxis;
    # only the 0015 block ("Constants Used for Nonneg Rules" .. "DQC_0067") is read.
    i0 = text.find("Constants Used for Nonneg Rules")
    i1 = text.find("DQC_0067", i0)
    if i0 < 0 or i1 < 0:
        raise SystemExit("0015 constant block not found in " + CONSTANTS_XULE.name)
    block = text[i0:i1]
    literal_prefix = {l: p for p, l in re.findall(r"\b(srt|us-gaap|dei):([A-Za-z]\w*)", block)}
    renamespaced = set()

    def fam_of(xlsx_ns, local):
        fam = literal_prefix.get(local, xlsx_ns)
        if fam != xlsx_ns:
            renamespaced.add((xlsx_ns, fam, local))
        return fam

    ws = openpyxl.load_workbook(MEMBERS_XLSX, data_only=True).worksheets[0]
    strings, members, axes, pairs = set(), set(), set(), collections.defaultdict(set)
    for row in list(ws.iter_rows(values_only=True))[1:]:
        test = row[4]
        if not test:
            continue
        if test.startswith("Member element name contains"):
            strings.add(str(row[7]).lower())  # "(Case insensitive)"
        elif test == "Member equals":
            members.add((fam_of(row[6], row[7]), row[7]))
        elif test == "Axis equals" and row[8] is None:
            axes.add((fam_of(row[6], row[7]), row[7]))
        elif test == "Axis equals" and row[8] == "AND member equals":
            pairs[(fam_of(row[6], row[7]), row[7])].add((fam_of(row[10], row[11]), row[11]))
    active = _active_xule(text)
    add_strings = [s.strip().strip("'\"") for s in _plus_set_items(_constant_body(active, "EXCLUDE_NON_NEG_STRING_MEMBERS"))]
    add_members = [_xule_qname(s) for s in _plus_set_items(_constant_body(active, "EXCLUDE_NON_NEG_MEMBERS"))]
    add_axes = [_xule_qname(s) for s in _plus_set_items(_constant_body(active, "EXCLUDE_NON_NEG_AXIS"))]
    strings |= {s.lower() for s in add_strings}
    members |= set(add_members)
    axes |= set(add_axes)
    return {
        "strings": strings, "members": members, "axes": axes,
        "pairs": {k: frozenset(v) for k, v in pairs.items()},
        "added_2026": {"strings": add_strings, "members": add_members, "axes": add_axes},
        "sheet_namespace_replaced_by_xule_literal": sorted(renamespaced),
    }


# --------------------------------------------------------------------------- #
# Query pieces
# --------------------------------------------------------------------------- #

_HEADERS = ("##Schema document", "##Presentation linkbase document", "##Calculation linkbase document",
            "##Definition linkbase document", "##Label linkbase document", "##Instance document",
            "##US GAAP Taxonomy")


def section(query, header):
    i = query.find(header)
    if i < 0:
        return None
    start = i + len(header)
    nxt = [query.find(h, start) for h in _HEADERS if query.find(h, start) >= 0]
    q1 = query.find("Question1:", start)
    ends = [x for x in nxt + ([q1] if q1 >= 0 else []) if x > start]
    return query[start:min(ends) if ends else len(query)].strip()


def question(query):
    m = None
    for m in re.finditer(r"Question1:\s*What's the reported value of\s+(\S+)\s+in the Instance document\s+for the period\s+"
                         r"(\d{4}-\d{2}-\d{2})(?:\s+to\s+(\d{4}-\d{2}-\d{2}))?", query):
        pass
    if m is None:
        return None
    concept = m.group(1).rstrip("?.,")
    if m.group(3):
        return concept, (m.group(2), m.group(3), None)
    return concept, (None, None, m.group(2))


def entry_point_ns(schema_text, filing_dir, instance_text):
    for text in ([schema_text] if schema_text else []):
        m = re.search(r"<(?:\w[\w.-]*:)?schema\b[^>]*?targetNamespace=[\"']([^\"']+)", text, re.S)
        if m:
            return m.group(1)
    if filing_dir:
        ref = re.search(r"schemaRef\b[^>]*?href=[\"']([^\"']+)", instance_text)
        if ref:
            p = Path(filing_dir) / ref.group(1).split("/")[-1]
            if p.is_file():
                m = re.search(r"<(?:\w[\w.-]*:)?schema\b[^>]*?targetNamespace=[\"']([^\"']+)", p.read_text(errors="replace"), re.S)
                if m:
                    return m.group(1)
    return None


# --------------------------------------------------------------------------- #
# Instance (xml.etree, scoped namespaces)
# --------------------------------------------------------------------------- #


def family(uri, ext_ns):
    m = re.match(r"https?://(?:fasb\.org|xbrl\.sec\.gov)/([^/]+)/", uri or "")
    if m:
        return m.group(1)
    if ext_ns is None or uri == ext_ns:
        return "EXT"
    return "OTHER:" + (uri or "")


def parse(instance_text):
    text = re.sub(r"^\s*<\?xml[^>]*\?>", "", instance_text, count=1)
    scope_of, stack, pending, root = {}, [{}], {}, None
    for ev, obj in ET.iterparse(io.BytesIO(text.encode("utf-8")), events=("start-ns", "start", "end")):
        if ev == "start-ns":
            pending[obj[0]] = obj[1]
        elif ev == "start":
            if pending:
                sc = dict(stack[-1])
                sc.update(pending)
                pending = {}
            else:
                sc = stack[-1]
            stack.append(sc)
            scope_of[obj] = sc
            if root is None:
                root = obj
        else:
            stack.pop()

    def res(qn, el):
        qn = (qn or "").strip()
        p, l = qn.split(":", 1) if ":" in qn else ("", qn)
        return scope_of[el].get(p), l

    contexts = {}
    for c in root.iter(f"{{{XBRLI}}}context"):
        ident = c.find(f"{{{XBRLI}}}entity/{{{XBRLI}}}identifier")
        per = c.find(f"{{{XBRLI}}}period")
        period = tuple((per.findtext(f"{{{XBRLI}}}{t}") or "").strip() or None for t in ("startDate", "endDate", "instant"))
        dims = []
        for m in c.iter(f"{{{XBRLDI}}}explicitMember"):
            dims.append(("explicit", res(m.get("dimension"), m), res(m.text, m)))
        for m in c.iter(f"{{{XBRLDI}}}typedMember"):
            dims.append(("typed", res(m.get("dimension"), m), ET.tostring(m, encoding="unicode")))
        contexts[c.get("id")] = {"period": period, "entity": (ident.get("scheme"), (ident.text or "").strip()), "dims": dims}
    units = {}
    for u in root.iter(f"{{{XBRLI}}}unit"):
        num = u.find(f"{{{XBRLI}}}divide/{{{XBRLI}}}unitNumerator")
        den = u.find(f"{{{XBRLI}}}divide/{{{XBRLI}}}unitDenominator")
        if num is not None:
            units[u.get("id")] = (tuple(sorted(res(m.text, m) for m in num.iter(f"{{{XBRLI}}}measure"))),
                                  tuple(sorted(res(m.text, m) for m in den.iter(f"{{{XBRLI}}}measure"))))
        else:
            units[u.get("id")] = (tuple(sorted(res(m.text, m) for m in u.iter(f"{{{XBRLI}}}measure"))), ())
    facts = []
    for el in root.iter():
        if not isinstance(el.tag, str) or not el.tag.startswith("{"):
            continue
        uri, local = el.tag[1:].split("}", 1)
        if uri in NON_FACT_NS or el.get("contextRef") is None:
            continue
        facts.append({"uri": uri, "local": local, "cref": el.get("contextRef"), "unit": el.get("unitRef"),
                      "decimals": el.get("decimals"), "nil": (el.get(XSI_NIL) or "").strip().lower() in ("true", "1"),
                      "text": (el.text or "").strip(), "id": el.get("id")})
    return {"nsmap": scope_of[root], "contexts": contexts, "units": units, "facts": facts}


# --------------------------------------------------------------------------- #
# The rule
# --------------------------------------------------------------------------- #


def _dec(d):
    d = (d or "").strip()
    if not d or d == "INF":
        return INF
    try:
        return int(d)
    except ValueError:
        return INF


def _eq(v1, d1, v2, d2):
    m = min(d1, d2)
    a = v1 if d1 == INF else round(v1, int(m))
    b = v2 if d2 == INF else round(v2, int(m))
    return a == b


def exempt(dims, excl, ext_ns):
    if not dims:
        return False
    explicit = [((family(a[0], ext_ns), a[1]), (family(m[0], ext_ns), m[1])) for kind, a, m in dims if kind == "explicit"]
    every_axis = [(family(a[0], ext_ns), a[1]) for kind, a, _ in dims]
    if any(s in m[1].lower() for _, m in explicit for s in excl["strings"]):
        return True
    if any(m in excl["members"] for _, m in explicit):
        return True
    if any(a in excl["axes"] for a in every_axis):
        return True
    by_axis = dict(explicit)
    return any(by_axis.get(ax) in mems for ax, mems in excl["pairs"].items())


def run(parsed, items, excl, ext_ns, version, concept=None, period=None):
    """Flagged facts: [(family, local), period, value, sorted dims, fact id]; one per duplicate set."""
    groups, kept = {}, []
    for f in parsed["facts"]:
        key = (family(f["uri"], ext_ns), f["local"])
        if concept is not None and key != concept:
            continue
        ctx = parsed["contexts"].get(f["cref"])
        if ctx is None or (period is not None and ctx["period"] != period):
            continue
        if f["nil"] or not (f["unit"] or "").strip():
            continue
        try:
            v = Decimal(f["text"])
        except InvalidOperation:
            continue
        if not v.is_finite():
            continue
        dims_key = frozenset(((family(a[0], ext_ns), a[1]), (family(m[0], ext_ns), m[1]) if kind == "explicit" else m)
                             for kind, a, m in ctx["dims"])
        aspects = (key, ctx["period"], ctx["entity"], parsed["units"].get(f["unit"], f["unit"]), dims_key)
        d = _dec(f["decimals"])
        for e in groups.setdefault(aspects, []):
            if _eq(v, d, e["v"], e["d"]):
                if d > e["d"]:
                    e.update(v=v, d=d, f=f)
                break
        else:
            e = {"v": v, "d": d, "f": f, "ctx": ctx, "key": key}
            groups[aspects].append(e)
            kept.append(e)
    out = []
    for e in kept:
        if not e["v"] < 0 or not listed(items, e["key"], version):
            continue
        if exempt(e["ctx"]["dims"], excl, ext_ns):
            continue
        dims = sorted((a[1], m[1] if isinstance(m, tuple) else "<typed>") for _, a, m in e["ctx"]["dims"])
        out.append((e["key"], e["ctx"]["period"], e["v"], tuple(dims), e["f"]["id"]))
    return out


def case_findings(query, items, excl, version, filing_dir=None, parsed_cache=None):
    """(question-level findings, filing-level findings) for one Task 3 query."""
    inst = section(query, "##Instance document")
    key = hashlib.md5(inst.encode()).hexdigest()
    if parsed_cache is not None and key in parsed_cache:
        parsed = parsed_cache[key]
    else:
        parsed = parse(inst)
        if parsed_cache is not None:
            parsed_cache.clear()
            parsed_cache[key] = parsed
    ext_ns = entry_point_ns(section(query, "##Schema document"), filing_dir, inst)
    q = question(query)
    concept = None
    if q:
        p, _, l = q[0].rpartition(":")
        concept = (family(parsed["nsmap"].get(p), ext_ns), l)
    qf = run(parsed, items, excl, ext_ns, version, concept, q[1]) if q else []
    return qf, (lambda: run(parsed, items, excl, ext_ns, version)), key


def main() -> int:
    sys.path.insert(0, str(HERE))
    import validate_0015 as V  # paths and filing lookup only

    ap = argparse.ArgumentParser()
    ap.add_argument("--version", type=int, default=29)
    args = ap.parse_args()
    items, excl = load_items(), load_exclusions()
    print("2026 additions parsed from the .xule:", excl["added_2026"])
    for split, path in (("practice", V.PRACTICE_INPUTS), ("dev", V.DEV_INPUTS)):
        n = fired = 0
        for line in open(path):
            r = json.loads(line)
            qf, _, _ = case_findings(r["query"], items, excl, args.version, V.filing_dir(r["query"], split))
            n += 1
            fired += bool(qf)
        print(split, "cases", n, "fire", fired)
    return 0


if __name__ == "__main__":
    sys.exit(main())
