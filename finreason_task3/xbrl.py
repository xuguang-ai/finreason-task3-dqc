"""Parsing utilities for FinReason Task 3 (Financial Audit Verification) queries.

Each Task 3 ``query`` string is a prompt preamble followed by seven ``##`` sections
(Schema, Presentation, Calculation, Definition, Label, Instance, US GAAP Taxonomy)
and two trailing questions.  This module ONLY parses; it never decides an answer.

Empirical findings on the 332-case public dev set that shape the design
(every number comes from running the analysis scripts on public_dev_inputs.jsonl):

* **Hard truncation at 32,767 characters (Excel cell limit).**  Every section is
  cut at 32,767 chars; 178/332 Instance sections and 210/332 Label sections are
  exactly that length and are therefore *not well-formed XML* (185 Instance
  sections fail ``lxml.etree.fromstring``; only 147 end with ``</xbrl>``).
  63/332 Instance sections contain zero facts (59 are cut *inside the context
  list*).  Hence all parsing here is regex-based and tolerant of a dangling,
  half-written last element (41 cases end with a fact whose closing tag is cut
  mid-name, e.g. ``58013000</us-gaap:SharesOut``).
* **The target fact is often simply gone.**  For 113/332 cases the gold
  extracted number does not occur anywhere in the query text.  Callers must
  treat "not found" as a real, frequent outcome, not a parser bug.
* **Schema section may be the literal string ``None``** (120/332).  Other
  sections are never ``None`` but may be an empty self-closing linkbase.
* **Instance uses the default namespace** (``<xbrl xmlns="http://www.xbrl.org/2003/instance">``,
  so ``<context>``, ``<period>``, ``<startDate>`` are unprefixed) in 332/332 cases;
  dimensional members are ``<xbrldi:explicitMember dimension="...">member</...>``.
  Contexts always precede facts (273/273 cases with facts).  9,124/10,803
  contexts carry dimensions; per case there is never more than ONE
  dimension-free context for the questioned period (297 cases have exactly 1,
  35 have 0).
* **Duplicate facts**: 18/176 cases have 2-3 facts for the same concept and the
  same dimension-free context; 17 agree, 1 (DEV_000014) differs by rounding
  (``7000000.0`` decimals=-5 vs ``6995000`` decimals=-3).
* **Fact values** are plain: 14,574 numeric facts, 0 with thousands separators,
  0 with ``scale``/``sign`` attributes (those are inline-XBRL only), 2,760 start
  with ``-``, 652 contain a decimal point; 855/15,568 facts are ``xsi:nil``.
* **Question wording**: duration = ``for the period 2021-09-01 to 2021-11-30``
  (222 cases); instant = ``for the period 2022-12-31`` (110 cases; a single
  date, *not* "as of").  Concept prefix is ``us-gaap`` in 321 cases, ``srt`` in
  2, filer-specific in 9.
* **Calculation linkbase**: at most ONE ``calculationLink`` per case (244 have
  1, 88 have 0) so a concept never appears under two roles.  Arcs are
  ``<link:calculationArc>`` (229 cases) or unprefixed ``<calculationArc>`` (1).
  ``xlink:from/to`` are locator labels resolved via
  ``xlink:href="...xsd#prefix_LocalName"`` (5,211 locators, 0 unresolved arcs).
  Weights are exactly ``1`` (3,747) or ``-1`` (1,021).  102/332 sections have
  no arc at all.  The questioned concept is a calculation *parent* in 131 cases
  (0015: 4, 0117: 25, 0126: 102); 74.9% of its children (721/962 arcs) have a
  dimension-free fact for the questioned period.
* **US GAAP Taxonomy section** is plain text with one ``[Concept Core]`` block
  (323/332) and several ``[Concept Relations]`` blocks (Presentation /
  Calculation / Definition / References).  The ``Calculation:`` block
  (297/332) lists ``- As Parent:`` children (211) and ``- As Child:`` parents
  (286) with ``weight`` and ``role`` — standard-taxonomy relationships, the only
  calculation source when the filer's linkbase has no arc for the concept.  But
  in 84/86 such cases none of those standard children has a fact in the instance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

__all__ = [
    "SECTION_HEADERS",
    "SECTION_KEYS",
    "Question",
    "Context",
    "Fact",
    "InstanceDoc",
    "CalcArc",
    "TaxonomyInfo",
    "split_sections",
    "parse_question",
    "parse_instance",
    "parse_calculation",
    "parse_calculation_arcs",
    "DefinitionLink",
    "parse_definition",
    "hypercube_axis_members",
    "domain_member_children",
    "parse_taxonomy",
    "href_to_concept",
    "find_target_facts",
]

# --------------------------------------------------------------------------- #
# Sections
# --------------------------------------------------------------------------- #

SECTION_HEADERS: Tuple[str, ...] = (
    "##Schema document",
    "##Presentation linkbase document",
    "##Calculation linkbase document",
    "##Definition linkbase document",
    "##Label linkbase document",
    "##Instance document",
    "##US GAAP Taxonomy",
)
SECTION_KEYS: Tuple[str, ...] = (
    "schema",
    "presentation",
    "calculation",
    "definition",
    "label",
    "instance",
    "taxonomy",
)
_HDR_TO_KEY = dict(zip(SECTION_HEADERS, SECTION_KEYS))

# Sections are cut at the Excel cell limit.  A section of exactly this length is
# almost certainly truncated (and thus not well-formed XML).
EXCEL_CELL_LIMIT = 32767

_QUESTION_SPLIT = re.compile(r"\n\s*Question1:", re.M)


def split_sections(query: str) -> Dict[str, str]:
    """Split a Task 3 query into its parts.

    Returns a dict with keys ``preamble``, the seven ``SECTION_KEYS`` and
    ``question`` (the text from ``Question1:`` to the end).  Section bodies are
    stripped.  A body equal to ``"None"`` is kept verbatim so callers can detect
    it (``parse_*`` helpers treat it as empty).

    Findings: all 332 dev cases contain all seven headers, in this fixed order,
    each on its own line.  The question tail lives *inside* the last section's
    text, so it is separated here.
    """
    positions = []
    for hdr in SECTION_HEADERS:
        m = re.search(r"^" + re.escape(hdr) + r"[ \t]*$", query, re.M)
        if m:
            positions.append((m.start(), m.end(), hdr))
    positions.sort()
    out: Dict[str, str] = {k: "" for k in SECTION_KEYS}
    out["preamble"] = query[: positions[0][0]].strip() if positions else ""
    out["question"] = ""
    for i, (start, end, hdr) in enumerate(positions):
        stop = positions[i + 1][0] if i + 1 < len(positions) else len(query)
        body = query[end:stop]
        if i == len(positions) - 1:
            qm = _QUESTION_SPLIT.search(body)
            if qm:
                out["question"] = body[qm.start() :].strip()
                body = body[: qm.start()]
        out[_HDR_TO_KEY[hdr]] = body.strip()
    if not out["question"]:
        qm = _QUESTION_SPLIT.search(query)
        if qm:
            out["question"] = query[qm.start() :].strip()
    return out


def _is_missing(section: str) -> bool:
    return not section or section.strip() in ("", "None", "null")


# --------------------------------------------------------------------------- #
# Question
# --------------------------------------------------------------------------- #


@dataclass
class Question:
    concept: str  #: e.g. ``us-gaap:PaymentsToAcquirePropertyPlantAndEquipment``
    period_type: str  #: ``"duration"`` or ``"instant"``
    start: Optional[str]  #: ISO date for duration, else ``None``
    end: Optional[str]  #: ISO date for duration, else ``None``
    instant: Optional[str]  #: ISO date for instant, else ``None``
    q1: str
    q2: str

    @property
    def prefix(self) -> str:
        return self.concept.split(":", 1)[0] if ":" in self.concept else ""

    @property
    def local_name(self) -> str:
        return self.concept.split(":", 1)[-1]

    @property
    def period_key(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        """``(start, end, instant)`` — same shape as :attr:`Context.period_key`."""
        return (self.start, self.end, self.instant)


_Q1_RE = re.compile(
    r"Question1:\s*What's the reported value of\s+(?P<concept>\S+)\s+in the Instance document"
    r"\s+for the period\s+(?P<d1>\d{4}-\d{2}-\d{2})(?:\s+to\s+(?P<d2>\d{4}-\d{2}-\d{2}))?\s*\?",
    re.S,
)
_Q2_RE = re.compile(r"Question2:(?P<q2>.*?)(?:\n\s*Answer:|\Z)", re.S)


def parse_question(query: str) -> Question:
    """Extract concept and period from the trailing Question1/Question2.

    Findings: matches 332/332 dev cases; 222 are durations
    (``for the period A to B``), 110 are instants written as
    ``for the period B`` (a single date — no "as of" wording).

    Raises ``ValueError`` if Question1 cannot be located.
    """
    tail = query[-4000:]
    m = _Q1_RE.search(tail)
    if not m:
        raise ValueError("Question1 not found / unrecognised format")
    q1_full = re.search(r"Question1:.*?\?", tail, re.S).group(0)
    q2m = _Q2_RE.search(tail)
    q2 = ("Question2:" + q2m.group("q2")).strip() if q2m else ""
    concept = m.group("concept").rstrip("?.,")
    d1, d2 = m.group("d1"), m.group("d2")
    if d2:
        return Question(concept, "duration", d1, d2, None, q1_full, q2)
    return Question(concept, "instant", None, None, d1, q1_full, q2)


# --------------------------------------------------------------------------- #
# Instance document
# --------------------------------------------------------------------------- #


@dataclass
class Context:
    id: str
    start: Optional[str] = None
    end: Optional[str] = None
    instant: Optional[str] = None
    #: ``[(dimension, member), ...]`` from explicitMember; typedMember gives
    #: ``(dimension, "<typed>...")``.  Empty list == no dimensions.
    dims: List[Tuple[str, str]] = field(default_factory=list)
    entity: Optional[str] = None
    complete: bool = True  #: False if the closing </context> was truncated away

    @property
    def period_type(self) -> str:
        return "instant" if self.instant else ("duration" if self.start or self.end else "forever")

    @property
    def period_key(self) -> Tuple[Optional[str], Optional[str], Optional[str]]:
        return (self.start, self.end, self.instant)

    @property
    def has_dims(self) -> bool:
        return bool(self.dims)


@dataclass
class Fact:
    concept: str  #: ``prefix:LocalName`` exactly as written in the instance
    context_ref: str
    value: Optional[str]  #: raw text, stripped; ``None`` for xsi:nil
    unit_ref: Optional[str] = None
    decimals: Optional[str] = None
    precision: Optional[str] = None
    scale: Optional[str] = None  #: only present in inline XBRL; expected None
    sign: Optional[str] = None  #: only present in inline XBRL; expected None
    nil: bool = False
    id: Optional[str] = None
    attrs: Dict[str, str] = field(default_factory=dict)
    pos: int = -1  #: character offset inside the instance section
    #: True only for :attr:`InstanceDoc.dangling_fact` (element cut by truncation;
    #: ``value`` may be incomplete or None).
    truncated: bool = False


@dataclass
class InstanceDoc:
    contexts: Dict[str, Context]
    facts: List[Fact]
    units: Dict[str, str]
    #: True when the closing ``</xbrl>`` is present (147/332 in dev).
    complete: bool
    #: Raw text of a dangling fact element cut off by truncation, if any.
    dangling_tail: str = ""
    #: Best-effort parse of ``dangling_tail`` (``truncated=True``).  Its value
    #: is only trustworthy when the closing tag had started (``</prefix:Na``).
    dangling_fact: Optional[Fact] = None
    length: int = 0

    def facts_for(self, concept: str) -> List[Fact]:
        return [f for f in self.facts if f.concept == concept]


_CTX_RE = re.compile(r"<(?:xbrli:)?context\b[^>]*\bid=\"([^\"]*)\"[^>]*>(.*?)</(?:xbrli:)?context>", re.S)
_CTX_OPEN_RE = re.compile(r"<(?:xbrli:)?context\b[^>]*\bid=\"([^\"]*)\"[^>]*>", re.S)
_START_RE = re.compile(r"<(?:xbrli:)?startDate>\s*([^<\s]+)\s*</")
_END_RE = re.compile(r"<(?:xbrli:)?endDate>\s*([^<\s]+)\s*</")
_INSTANT_RE = re.compile(r"<(?:xbrli:)?instant>\s*([^<\s]+)\s*</")
_EXPL_RE = re.compile(r"<xbrldi:explicitMember\b[^>]*\bdimension=\"([^\"]*)\"[^>]*>\s*([^<\s]+)\s*</")
_TYPED_RE = re.compile(r"<xbrldi:typedMember\b[^>]*\bdimension=\"([^\"]*)\"[^>]*>(.*?)</xbrldi:typedMember>", re.S)
_IDENT_RE = re.compile(r"<(?:xbrli:)?identifier\b[^>]*>\s*([^<\s]+)\s*</")
_UNIT_RE = re.compile(r"<(?:xbrli:)?unit\b[^>]*\bid=\"([^\"]*)\"[^>]*>(.*?)</(?:xbrli:)?unit>", re.S)
_MEASURE_RE = re.compile(r"<(?:xbrli:)?measure>\s*([^<\s]+)\s*</")

# A fact is any element whose start tag carries contextRef.  Prefixes may contain
# digits/hyphens (``us-gaap``); local names start with a letter.
_FACT_RE = re.compile(
    r"<(?P<tag>[A-Za-z_][\w.-]*:[A-Za-z_][\w.-]*)(?P<attrs>\s[^<>]*?\bcontextRef=\"[^\"]*\"[^<>]*?)"
    r"(?:/>|>(?P<body>.*?)</(?P=tag)\s*>)",
    re.S,
)
_ATTR_RE = re.compile(r"([\w:.-]+)\s*=\s*\"([^\"]*)\"")
# A trailing fact element with no matching end tag: either the start tag itself
# is cut, or the start tag closed and the body/end tag is cut.
_DANGLING_RE = re.compile(
    r"<(?P<tag>[A-Za-z_][\w.-]*:[A-Za-z_][\w.-]*)(?P<attrs>\s[^<>]*\bcontextRef=\"[^<>]*?)"
    r"(?:>(?P<body>[^<]*)(?P<endtag><[^>]*)?)?$",
    re.S,
)


def _parse_context_body(cid: str, body: str, complete: bool) -> Context:
    ctx = Context(id=cid, complete=complete)
    m = _START_RE.search(body)
    if m:
        ctx.start = m.group(1)
    m = _END_RE.search(body)
    if m:
        ctx.end = m.group(1)
    m = _INSTANT_RE.search(body)
    if m:
        ctx.instant = m.group(1)
    m = _IDENT_RE.search(body)
    if m:
        ctx.entity = m.group(1)
    for dm in _EXPL_RE.finditer(body):
        ctx.dims.append((dm.group(1), dm.group(2)))
    for dm in _TYPED_RE.finditer(body):
        ctx.dims.append((dm.group(1), "<typed>" + re.sub(r"\s+", " ", dm.group(2)).strip()))
    return ctx


def parse_instance(query_or_section: str) -> InstanceDoc:
    """Parse contexts, units and facts out of the Instance section.

    Accepts either the full query or just the instance section text.  Pure
    regex, so it survives truncation: complete contexts/facts are returned, a
    context whose closing tag is missing is returned with ``complete=False``
    (its period/dims may be partial), and a half-written trailing fact is
    exposed as ``InstanceDoc.dangling_tail``.

    Findings on dev: fact values are plain XML text (no thousands separators;
    negative sign is a leading ``-``); ``decimals`` is present on all 14,574
    numeric facts; ``scale``/``sign`` attributes (inline XBRL) never occur;
    855 ``xsi:nil="true"`` facts exist and have no text.  Facts of a TextBlock
    concept may contain escaped HTML — kept verbatim as ``value``.  The parsed
    facts plus ``dangling_fact`` account for every ``contextRef=`` occurrence in
    332/332 cases; 95 cases end in a dangling fact (41 with the closing tag cut
    mid-name, e.g. ``58013000</us-gaap:SharesOut``, whose value is therefore
    complete; 4 are a >30k-char escaped-HTML TextBlock cut mid-body).
    """
    text = query_or_section
    if "##Instance document" in text:
        text = split_sections(text)["instance"]
    if _is_missing(text):
        return InstanceDoc({}, [], {}, False, "", None, 0)

    contexts: Dict[str, Context] = {}
    last_end = 0
    for m in _CTX_RE.finditer(text):
        contexts[m.group(1)] = _parse_context_body(m.group(1), m.group(2), True)
        last_end = m.end()
    # dangling (truncated) context: an open tag after the last closed context
    tail = text[last_end:]
    dm = _CTX_OPEN_RE.search(tail)
    while dm:
        cid = dm.group(1)
        nxt = _CTX_OPEN_RE.search(tail, dm.end())
        body = tail[dm.end() : nxt.start() if nxt else len(tail)]
        if cid not in contexts:
            contexts[cid] = _parse_context_body(cid, body, False)
        dm = nxt

    units: Dict[str, str] = {}
    for m in _UNIT_RE.finditer(text):
        measures = _MEASURE_RE.findall(m.group(2))
        units[m.group(1)] = "/".join(measures) if measures else m.group(2).strip()

    facts: List[Fact] = []
    for m in _FACT_RE.finditer(text):
        attrs = dict(_ATTR_RE.findall(m.group("attrs")))
        body = m.group("body")
        nil = attrs.get("xsi:nil", "").lower() == "true"
        value = None if (body is None or nil) else body.strip()
        facts.append(
            Fact(
                concept=m.group("tag"),
                context_ref=attrs.get("contextRef", ""),
                value=value,
                unit_ref=attrs.get("unitRef"),
                decimals=attrs.get("decimals"),
                precision=attrs.get("precision"),
                scale=attrs.get("scale"),
                sign=attrs.get("sign"),
                nil=nil,
                id=attrs.get("id"),
                attrs=attrs,
                pos=m.start(),
            )
        )
    complete = bool(re.search(r"</(?:xbrli:)?xbrl>\s*$", text))
    dangling = ""
    dangling_fact: Optional[Fact] = None
    if not complete:
        last_fact_end = facts[-1].pos + 1 if facts else 0
        # No length cap: a truncated TextBlock fact can span >30k chars (4 dev cases).
        rest = text[last_fact_end:]
        dm2 = _DANGLING_RE.search(rest)
        if dm2 and (not facts or dm2.start() + len(text) - len(rest) > facts[-1].pos):
            dangling = dm2.group(0)
            attrs = dict(_ATTR_RE.findall(dm2.group("attrs") or ""))
            body = dm2.group("body")
            # value is only complete if the end tag had started
            value = body.strip() if (body is not None and dm2.group("endtag")) else None
            dangling_fact = Fact(
                concept=dm2.group("tag"),
                context_ref=attrs.get("contextRef", ""),
                value=value,
                unit_ref=attrs.get("unitRef"),
                decimals=attrs.get("decimals"),
                id=attrs.get("id"),
                attrs=attrs,
                pos=len(text) - len(rest) + dm2.start(),
                truncated=True,
            )
    return InstanceDoc(contexts, facts, units, complete, dangling, dangling_fact, len(text))


def find_target_facts(
    doc: InstanceDoc, question: Question, *, require_no_dims: bool = True
) -> List[Tuple[Fact, Context]]:
    """Return ``(fact, context)`` pairs for the question's concept and period.

    Period matching is exact string equality on ISO dates.  With
    ``require_no_dims`` (default) only contexts without any dimension are
    returned — these are the "reported" statement-level values.  Facts whose
    contextRef is unknown (context truncated away) are skipped.
    """
    out: List[Tuple[Fact, Context]] = []
    for f in doc.facts:
        if f.concept != question.concept:
            continue
        ctx = doc.contexts.get(f.context_ref)
        if ctx is None:
            continue
        if ctx.period_key != question.period_key:
            continue
        if require_no_dims and ctx.has_dims:
            continue
        out.append((f, ctx))
    return out


# --------------------------------------------------------------------------- #
# Calculation linkbase
# --------------------------------------------------------------------------- #


@dataclass
class CalcArc:
    parent: str
    child: str
    weight: float
    role: str
    order: Optional[float] = None
    #: Raw locator labels (useful when a label could not be resolved).
    from_label: str = ""
    to_label: str = ""


_CALC_LINK_RE = re.compile(
    r"<(?:link:)?calculationLink\b(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</(?:link:)?calculationLink>)",
    re.S,
)
_CALC_LINK_OPEN_RE = re.compile(r"<(?:link:)?calculationLink\b(?P<attrs>[^>]*?)>", re.S)
_LOC_RE = re.compile(r"<(?:link:)?loc\b(?P<attrs>[^>]*?)/?>", re.S)
_ARC_RE = re.compile(r"<(?:link:)?calculationArc\b(?P<attrs>[^>]*?)/?>", re.S)


def href_to_concept(href: str) -> str:
    """``foo-20211231.xsd#us-gaap_Revenues`` -> ``us-gaap:Revenues``.

    Element ids follow the ``prefix_LocalName`` convention; the first underscore
    separates prefix from local name (verified: every locator in the dev set
    resolves to a fact-style ``prefix:LocalName`` this way).
    """
    frag = href.split("#", 1)[-1]
    if "_" in frag:
        p, n = frag.split("_", 1)
        return f"{p}:{n}"
    return frag


def _parse_calc_link_body(role: str, body: str, arcs: List[CalcArc], unresolved: List[dict]) -> None:
    locs: Dict[str, str] = {}
    for lm in _LOC_RE.finditer(body):
        a = dict(_ATTR_RE.findall(lm.group("attrs")))
        if "xlink:label" in a and "xlink:href" in a:
            locs[a["xlink:label"]] = href_to_concept(a["xlink:href"])
    for am in _ARC_RE.finditer(body):
        a = dict(_ATTR_RE.findall(am.group("attrs")))
        arcrole = a.get("xlink:arcrole", "")
        if arcrole and not arcrole.endswith("summation-item"):
            continue
        fl, tl = a.get("xlink:from", ""), a.get("xlink:to", "")
        parent, child = locs.get(fl), locs.get(tl)
        try:
            weight = float(a.get("weight", "1"))
        except ValueError:
            weight = 1.0
        try:
            order = float(a["order"]) if "order" in a else None
        except ValueError:
            order = None
        if parent is None or child is None:
            unresolved.append({"role": role, "from": fl, "to": tl, "attrs": a})
            continue
        arcs.append(CalcArc(parent, child, weight, role, order, fl, tl))


def parse_calculation_arcs(query_or_section: str) -> Tuple[List[CalcArc], List[dict], bool]:
    """Low-level: return ``(arcs, unresolved_arcs, complete)``.

    ``complete`` is False when the closing ``</link:linkbase>`` (or a
    self-closing ``<link:linkbase .../>``, 88/332) is missing — truncated in
    exactly 1/332 dev cases (DEV_000241, 51 arcs still recovered).  Truncated
    trailing ``calculationLink`` blocks are parsed as far as they go.
    """
    text = query_or_section
    if "##Calculation linkbase document" in text:
        text = split_sections(text)["calculation"]
    arcs: List[CalcArc] = []
    unresolved: List[dict] = []
    if _is_missing(text):
        return arcs, unresolved, False
    last_end = 0
    for m in _CALC_LINK_RE.finditer(text):
        a = dict(_ATTR_RE.findall(m.group("attrs")))
        role = a.get("xlink:role", "")
        if m.group("body"):
            _parse_calc_link_body(role, m.group("body"), arcs, unresolved)
        last_end = m.end()
    # dangling last link (truncation)
    tail = text[last_end:]
    om = _CALC_LINK_OPEN_RE.search(tail)
    if om and not om.group(0).endswith("/>"):
        a = dict(_ATTR_RE.findall(om.group("attrs")))
        _parse_calc_link_body(a.get("xlink:role", ""), tail[om.end() :], arcs, unresolved)
    complete = bool(re.search(r"</(?:link:)?linkbase>\s*$", text)) or bool(
        re.search(r"<(?:link:)?linkbase\b[^>]*/>\s*$", text)
    )
    return arcs, unresolved, complete


def parse_calculation(query_or_section: str) -> Dict[str, List[Tuple[str, float, str]]]:
    """Return ``{parent_concept: [(child_concept, weight, role), ...]}``.

    Concept names are ``prefix:LocalName`` (same spelling as instance facts).
    The same parent may appear under several roles (different statements /
    notes) — entries are kept per role, in document order, so callers can pick
    a role.  Duplicate ``(child, weight, role)`` triples are removed.

    Findings on dev: 230/332 calculation sections contain at least one arc;
    weights are exactly ``1`` or ``-1``; every locator label resolved.
    """
    arcs, _unresolved, _complete = parse_calculation_arcs(query_or_section)
    out: Dict[str, List[Tuple[str, float, str]]] = {}
    seen = set()
    for arc in arcs:
        key = (arc.parent, arc.child, arc.weight, arc.role)
        if key in seen:
            continue
        seen.add(key)
        out.setdefault(arc.parent, []).append((arc.child, arc.weight, arc.role))
    return out


# --------------------------------------------------------------------------- #
# Definition linkbase (hypercubes / dimension members)
# --------------------------------------------------------------------------- #


@dataclass
class DefinitionLink:
    role: str
    title: str
    #: ``[(arcrole_short, from_concept, to_concept)]`` with arcrole_short one of
    #: ``all`` / ``notAll`` / ``hypercube-dimension`` / ``dimension-domain`` /
    #: ``domain-member`` / ``dimension-default``.  Unresolvable locators give ``None``.
    arcs: List[Tuple[str, Optional[str], Optional[str]]] = field(default_factory=list)
    complete: bool = True

    @property
    def is_statement(self) -> bool:
        """Heuristic: a primary financial statement role (not a parenthetical)."""
        t = f"{self.title} {self.role}"
        return "tatement" in t and "arenthetical" not in t


_DEF_LINK_RE = re.compile(
    r"<(?:link:)?definitionLink\b(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</(?:link:)?definitionLink>)",
    re.S,
)
_DEF_LINK_OPEN_RE = re.compile(r"<(?:link:)?definitionLink\b(?P<attrs>[^>]*?)>", re.S)
_DEF_ARC_RE = re.compile(r"<(?:link:)?definitionArc\b(?P<attrs>[^>]*?)/?>", re.S)


def _parse_def_link_body(attrs: dict, body: str, complete: bool) -> DefinitionLink:
    link = DefinitionLink(role=attrs.get("xlink:role", ""), title=attrs.get("xlink:title", ""), complete=complete)
    locs: Dict[str, str] = {}
    for lm in _LOC_RE.finditer(body):
        a = dict(_ATTR_RE.findall(lm.group("attrs")))
        if "xlink:label" in a and "xlink:href" in a:
            locs[a["xlink:label"]] = href_to_concept(a["xlink:href"])
    for am in _DEF_ARC_RE.finditer(body):
        a = dict(_ATTR_RE.findall(am.group("attrs")))
        arcrole = a.get("xlink:arcrole", "").rsplit("/", 1)[-1]
        link.arcs.append((arcrole, locs.get(a.get("xlink:from", "")), locs.get(a.get("xlink:to", ""))))
    return link


def parse_definition(query_or_section: str) -> List[DefinitionLink]:
    """Parse every ``definitionLink`` of the Definition linkbase section.

    Regex-based like the rest of the module; a trailing link whose closing tag
    was truncated away is still returned (``complete=False``) with the arcs
    recovered so far.  Findings on dev: 196/332 sections contain at least one
    link; arcroles seen are domain-member (5,470), hypercube-dimension (414),
    dimension-domain (414), dimension-default (412), all (203); 66 cases have
    a link whose title mentions a Statement.
    """
    text = query_or_section
    if "##Definition linkbase document" in text:
        text = split_sections(text)["definition"]
    out: List[DefinitionLink] = []
    if _is_missing(text):
        return out
    last_end = 0
    for m in _DEF_LINK_RE.finditer(text):
        a = dict(_ATTR_RE.findall(m.group("attrs")))
        out.append(_parse_def_link_body(a, m.group("body") or "", True))
        last_end = m.end()
    om = _DEF_LINK_OPEN_RE.search(text, last_end)
    if om and not om.group(0).endswith("/>"):
        a = dict(_ATTR_RE.findall(om.group("attrs")))
        out.append(_parse_def_link_body(a, text[om.end() :], False))
    return out


def hypercube_axis_members(links: List[DefinitionLink], *, statement_only: bool = True) -> Dict[str, set]:
    """``{axis: {member, ...}}`` reachable via dimension-domain + domain-member arcs.

    With ``statement_only`` only links whose :attr:`DefinitionLink.is_statement`
    is true contribute (the members a filer actually puts on the face of a
    statement).  Members of the same axis from several links are unioned.
    """
    axes: Dict[str, set] = {}
    for link in links:
        if statement_only and not link.is_statement:
            continue
        dom: Dict[str, set] = {}
        children: Dict[str, set] = {}
        for arcrole, f, t in link.arcs:
            if not f or not t:
                continue
            if arcrole == "dimension-domain":
                dom.setdefault(f, set()).add(t)
            elif arcrole == "domain-member":
                children.setdefault(f, set()).add(t)
        for axis, doms in dom.items():
            members = axes.setdefault(axis, set())
            stack = list(doms)
            seen = set()
            while stack:
                d = stack.pop()
                for c in children.get(d, ()):
                    if c not in seen:
                        seen.add(c)
                        members.add(c)
                        stack.append(c)
    return axes


def domain_member_children(
    links: List[DefinitionLink], *, statement_only: bool = False
) -> Dict[str, set]:
    """``{member: {direct child member, ...}}`` from ``domain-member`` arcs.

    Why this matters for DQC_0117: a filer may put both an aggregate member and
    the members it aggregates on the same axis — AEP reports
    ``AlternativeandOtherMember`` alongside its own children
    ``AlternativeMember`` and ``OtherRevenuesMember``.  Summing every member of
    the axis then double-counts, which is exactly how three practice cases
    (DEV_000128/140/141) are lost.  Callers can use this map to drop members
    that are parents of other members present in the same period.

    Note this is a *structural* signal only.  It does not identify reconciling
    members such as ``UnallocatedAndOtherSegmentsMember``, which are leaves
    here yet still excluded from the gold sum in DEV_000137/142/143 — that
    distinction is semantic and has to come from elsewhere.
    """
    out: Dict[str, set] = {}
    for link in links:
        if statement_only and not link.is_statement:
            continue
        for arcrole, f, t in link.arcs:
            if arcrole == "domain-member" and f and t:
                out.setdefault(f, set()).add(t)
    return out


# --------------------------------------------------------------------------- #
# US GAAP Taxonomy (plain text)
# --------------------------------------------------------------------------- #


@dataclass
class TaxonomyInfo:
    concept: Optional[str]
    label: Optional[str] = None
    type: Optional[str] = None
    balance: Optional[str] = None  #: ``debit`` / ``credit`` / None
    period_type: Optional[str] = None  #: ``duration`` / ``instant``
    abstract: Optional[bool] = None
    documentation: Optional[str] = None
    #: Standard-taxonomy calc children: ``[(child, weight, role), ...]``
    calc_children: List[Tuple[str, float, str]] = field(default_factory=list)
    #: Standard-taxonomy calc parents: ``[(parent, weight, role), ...]``
    calc_parents: List[Tuple[str, float, str]] = field(default_factory=list)
    #: Presentation entries: ``[(role, path, preferred_label), ...]``
    presentation: List[Tuple[str, str, Optional[str]]] = field(default_factory=list)
    has_core: bool = False
    has_calc_block: bool = False


_TAX_CORE_RE = re.compile(r"\[Concept Core\]\s*\nID:\s*(?P<id>\S+)\s*\n(?P<body>.*?)(?=\n\[Concept|\Z)", re.S)
_TAX_CALC_CHILD_RE = re.compile(r"^\s*child=(?P<c>\S+)\s*\|\s*weight=(?P<w>-?[\d.]+)\s*\|\s*role=(?P<r>\S+)", re.M)
_TAX_CALC_PARENT_RE = re.compile(r"^\s*parent=(?P<c>\S+)\s*\|\s*weight=(?P<w>-?[\d.]+)\s*\|\s*role=(?P<r>\S+)", re.M)
_TAX_PRES_RE = re.compile(
    r"^- Role:\s*(?P<role>\S+)\s*\n\s*Path:\s*(?P<path>.*?)\s*\n(?:\s*PreferredLabel:\s*(?P<pl>\S+))?",
    re.M,
)


def parse_taxonomy(query_or_section: str) -> TaxonomyInfo:
    """Parse the plain-text ``##US GAAP Taxonomy`` section.

    Findings on dev: 323/332 have a ``[Concept Core]`` block (the 9 without are
    filer-specific extension concepts absent from the standard taxonomy);
    297/332 have a ``Calculation:`` block, 211 list ``As Parent`` children and
    286 list ``As Child`` parents.  Weights are ``1``/``-1``.
    """
    text = query_or_section
    if "##US GAAP Taxonomy" in text:
        text = split_sections(text)["taxonomy"]
    info = TaxonomyInfo(concept=None)
    if _is_missing(text):
        return info
    ids = re.findall(r"^ID:\s*(\S+)\s*$", text, re.M)
    if ids:
        info.concept = ids[0]
    cm = _TAX_CORE_RE.search(text)
    if cm:
        info.has_core = True
        body = cm.group("body")
        lm = re.search(r"^Label:\s*(.*)$", body, re.M)
        info.label = lm.group(1).strip() if lm else None
        tm = re.search(r"^Type:\s*(\S+)\s*\|\s*Balance:\s*(\S+)\s*\|\s*PeriodType:\s*(\S+)\s*\|\s*Abstract:\s*(\S+)", body, re.M)
        if tm:
            info.type = tm.group(1)
            info.balance = None if tm.group(2) == "None" else tm.group(2)
            info.period_type = None if tm.group(3) == "None" else tm.group(3)
            info.abstract = tm.group(4) == "True"
        dm = re.search(r"^Documentation:\s*\n(.*?)(?=\n\s*\n|\nProvenance:|\Z)", body, re.S | re.M)
        info.documentation = dm.group(1).strip() if dm else None
    # Calculation block(s)
    for cb in re.finditer(r"^Calculation:\s*\n(?P<body>.*?)(?=^Provenance:|^\[Concept|\Z)", text, re.S | re.M):
        info.has_calc_block = True
        body = cb.group("body")
        parent_part, child_part = "", ""
        ap = body.find("- As Parent:")
        ac = body.find("- As Child:")
        if ap >= 0:
            parent_part = body[ap : ac if (ac > ap) else len(body)]
        if ac >= 0:
            child_part = body[ac : ap if (ap > ac) else len(body)]
        for m in _TAX_CALC_CHILD_RE.finditer(parent_part):
            info.calc_children.append((m.group("c"), float(m.group("w")), m.group("r")))
        for m in _TAX_CALC_PARENT_RE.finditer(child_part):
            info.calc_parents.append((m.group("c"), float(m.group("w")), m.group("r")))
    for pb in re.finditer(r"^Presentation:\s*\n(?P<body>.*?)(?=^Provenance:|^\[Concept|\Z)", text, re.S | re.M):
        for m in _TAX_PRES_RE.finditer(pb.group("body")):
            info.presentation.append((m.group("role"), m.group("path").strip(), m.group("pl")))
    return info
