"""DQC_US_0117 -- Financial Statement Tables Dimensional Cross Check.

A re-implementation of the official XULE rule
``task3_source_data/dqc_rules/src_2026_DQC_0117.xule``.  The 2024, 2025 and
2026 rule files are identical apart from two blank lines (``diff -w`` after
stripping CR); line numbers below are lines of the 2026 file.

XULE semantics this module relies on
------------------------------------
* ``[...]`` is a CLOSED factset: a fact carrying a non-default dimension that
  the filter does not name is excluded.  ``{...}`` is open.  Evidence in the
  sources: (a) l.222 reads ``$TotalDefault = [... @$dim = $SubMember]`` and is
  summed against l.233 ``[... @$dim = $SubMember @$Dim2Dimension = *]``; were
  ``[...]`` open, every two-dimension fact would be its own total and 10093
  would fire on every two-dimension split; (b) lib_functions.xule
  getDimensionSums (l.758-768) has to name ``@$COUNTERPARTY_DIMENSION``
  explicitly to reach facts that carry srt:CounterpartyNameAxis.
* Aspects a factset neither filters nor covers (concept, period, unit, entity)
  are its alignment.  Aggregates (``list``, ``set``, ``all``, ``max``, ``sum``)
  are computed per alignment and read at the alignment of the total; an
  alignment without a group gets the aggregate's default (empty list / set,
  ``all`` -> true).  This is the only reading under which the notes guard
  (l.71, 76-81) acts per total, which the 2023+ practice gold requires: if the
  first-evaluated aggregate's alignments drove the iteration instead, the
  notes / parenthetical aggregates would block 69 of the 74 gold-consistent
  2023+ findings (review_0117_alignment_probe.py, "H2").

Rule element 9574 -- one axis (l.11-161)
---------------------------------------
``$drs_roles`` (l.22): one entry per cube of ``$STATEMENT_CUBES``
(lib_2026_constant.xule l.177-194: role definition contains ``- Statement -``;
role URI free of parenthetical / equity / deficit / stockholders / capital /
investment / changes / shareholder / convertible / preferred /
temporaryequity / redeemable / netproceedsfromallsources / membersinterest;
definition free of schedule iii / iv; table not a schedule of investments).
Only cubes exist, so only statements defined with a hypercube are checked.
For every dimension of such a cube whose local name is in the fixed list
(l.38):

1. ``$members`` (l.39) = every DRS descendant of the axis in the role,
   ``$domain`` (l.41) = its dimension-domain targets, ``$member_descendants``
   (l.84) = members minus domain.
2. ``$TotalDefault`` (l.74, closed): a non-nil monetary fact of the role's
   cubes with NO dimension except the axis at a domain member (in practice:
   dimension-free), instant or with the DocumentType fact's duration
   (l.30-31).  XULE iterates every such fact; its alignment is (concept,
   period, unit, entity).
3. ``$SubTotalExists`` (l.49-62).  The members are those found on
   multi-dimension facts AT THE TOTAL'S ALIGNMENT (``list(...)`` at l.49 is
   aligned), not over the whole role.  Inside ``set(for $SubMember ...
   exists([...]))`` the factset of a member is evaluated on its own: a member
   with facts yields ``true`` at each alignment where it has one; a member
   whose factset is empty everywhere yields an unaligned ``false``.  At the
   total's alignment ``all(...)`` therefore sees ``true`` if any member has an
   aligned subtotal; else the unaligned ``false`` if some member has no
   subtotal fact anywhere in the role; else no group, i.e. ``all``'s default
   ``true``.  That is ``Options.subtotal_guard="aggregate"`` (default).
   Evidence: ``"strict"`` (every member needs an aligned subtotal, the
   comment's intent) is contradicted by practice DEV_000172/173 (SAH: at that
   alignment Class A appears only on [Class A x RetainedEarnings] and has
   one-dimension facts only at other alignments, yet the finding is gold).
   ``"any"`` (no member with an aligned subtotal -> skip) needs "a total whose
   alignment has no group is skipped"; DEV_000173 refutes that for the notes
   and parenthetical aggregates (its alignment has multi-dimension facts,
   notes and parenthetical facts with the axis exist only at other
   alignments, and it is gold).  ``"off"`` ignores ``exists``' unaligned
   ``false``.  Measured over every concept and period of the practice and dev
   filings: "aggregate" and "off" never differ; "any" differs only by 3
   cash-flow findings in the DEV3_000215 filing (Insurance segment reported
   only with ConsolidatedEntitiesAxis; none is a questioned concept);
   "strict" drops SAH's two practice golds and the same pattern in SAH's 2025
   dev filing.
4. Parenthetical guard (l.65-67, 86) and notes guard (l.71, 76-81, 86), both
   closed factsets aligned with the total: skip when a non-nil fact carrying
   only the axis sits in a parenthetical statement cube, or in a
   ``- Disclosure -`` cube unless its largest value exceeds the total.
5. Member facts (l.88-93, closed): for every member below the domain, its
   aligned one-dimension fact unless one of its ancestors (domain excluded)
   has one -- only the highest reported level is summed.  None -> no finding
   (l.95).
6. FASB 606 exceptions for RevenueFromContractWithCustomer{Ex,In}cluding
   AssessedTax on srt:ProductOrServiceAxis (l.112-137), otherwise
   ``tolerance_for_decimals_comp($member_sums, $TotalDefault, $min_decimals,
   2)`` (lib_functions.xule l.209-248).  ``$bs_cubes[1]`` is the role's
   "first" statement cube; XULE set order is unspecified, the module takes
   file order and flags ``exception_order_sensitive`` when another statement
   cube of the role would change the outcome.

Rule element 10093 -- two axes (l.163-274, CheckSubTotalExists l.279-292)
------------------------------------------------------------------------
At the alignment of a total ``[@$dim = s]`` (closed: exactly that one
dimension, l.222) that has two-dimension monetary facts carrying D = s
(l.196-208): Dim2 = ``first`` of the other dimensions on those facts
(l.210-212; a set, so when there are several every candidate is evaluated and
the finding says ``dim2_ambiguous``), the >2-dimension subtotal check
(l.214-216, same ``subtotal_guard`` readings as 9574), the closed notes
guard on {D = s, Dim2 = *} (l.219-230), Dim2 not LegalEntityAxis (l.232), and
the sum of the closed two-dimension facts {D = s, Dim2 = *} aligned on
concept / period / unit / entity (l.233).  Its totals always carry D, so its
findings are returned only with ``all_alignments=True``.

Which rule version produced the gold (measured on practice, not read)
---------------------------------------------------------------------
Only the 2024-2026 rule files are on disk.  ``era="2026"`` (the default) is
the source.  ``LEGACY`` (no notes guard, no parenthetical guard, no 606
exceptions) and ``era="auto"`` (LEGACY for us-gaap <= 2022) were FITTED on the
46 practice 0117 cases of the 2021/2022 taxonomies (45 curated + DEV_000117)
and are scored on the same cases: their practice numbers are in-sample, not
estimates.  Practice also suggests the cut-off is the production DQC release
at filing time rather than the taxonomy year (NCMI's FY2022 10-K needs LEGACY,
MLP's 2023 Q2 10-Q needs 2026; Southern Co.'s FY2021 10-K ran without the
duration filter, AEP / OII / PRK FY2021 10-Ks with it); the filing date is not
in the case.  Dev (us-gaap 2023/2024/2025/2026 = 13/334/279/54) and test
(2/403/240/35) contain no us-gaap <= 2022 filing: ``"auto"`` equals
``"2026"`` on every one of them.

What this module can and cannot observe
---------------------------------------
* The DTS: with ``filing_dir`` (``<stem>.xsd`` roleTypes, ``_def`` and ``_cal``
  linkbases of the complete filing) statement, parenthetical and notes cubes
  are classified exactly as the rule does.  Without it only the released,
  statement-scoped sections exist: a released role counts as a statement only
  when the released Schema section defines it with ``- Statement -``
  (``assume_released_statements=True`` restores the old "assume statement"),
  and notes / parenthetical cubes outside the released roles are invisible, so
  those guards are blind.  No practice or dev case needs this mode (every one
  has its filing).  Measured anyway: on dev both settings equal the full-DTS
  result on 678/680 cases and fire additionally on DEV3_000190 / DEV3_000193
  (blind notes guard); on practice every 0117 case -- and only those -- has an
  empty released Schema section (119/119 vs 0/211), so 0117 fires there only
  with ``assume_released_statements=True`` (2026: 92 fire, 89 gold).
* ``notAll`` (negative) hypercubes are not built: no practice or dev filing
  has a single notAll arc (only arcroleRef declarations).
* ``is-monetary``: from the fact's unit (single ``iso4217`` measure).  All 47
  dev totals that fire are monetaryItemType concepts (42 typed in the
  released taxonomy section, 5 extension concepts in the filing's .xsd).
* ``applicable_form`` and ``effectiveDate`` read CSVs from GitHub at run time
  (not on disk): the rule is assumed applicable.
* ``$member_sums.decimals`` is taken as ``$min_decimals`` capped at 5 (XULE
  propagates decimals through ``sum``; identical unless a member has
  decimals > 5).
* Duplicate facts are seen once (most precise kept); 13 of the 47 firing dev
  cases have duplicates among the total / member facts, all value-consistent.
* XULE emits the message once per statement CUBE carrying the axis
  (``$drs_roles`` holds the cube, l.22-23); the module evaluates each role
  once and reports that count as ``n_messages``.  It is 1 for every finding
  on practice and dev, and no finding there is ``exception_order_sensitive``
  or (10093, notes guard on) ``dim2_ambiguous``.
"""

from __future__ import annotations

import functools
import html
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

from .. import xbrl as X

__all__ = [
    "TARGET_AXES",
    "Options",
    "FAITHFUL",
    "LEGACY",
    "findings_0117",
    "fires_0117",
    "options_for",
    "us_gaap_year",
    "load_filing",
    "locate_filing_dir",
    "statement_roles",
    "released_role_profile",
    "released_statement_target_roles",
    "Filing",
]

# --------------------------------------------------------------------------- #
# Constants from the rule source
# --------------------------------------------------------------------------- #

#: l.38 (9574) and l.188 (10093): the axes the rule sums along, by local name.
TARGET_AXES: Tuple[str, ...] = (
    "StatementClassOfStockAxis",
    "ProductOrServiceAxis",
    "PropertyPlantAndEquipmentByTypeAxis",
    "LongtermDebtTypeAxis",
    "RelatedPartyTransactionsByRelatedPartyAxis",
    "StatementBusinessSegmentsAxis",
    "LimitedPartnersCapitalAccountByClassAxis",
    "PartnerTypeOfPartnersCapitalAccountAxis",
    "FiniteLivedIntangibleAssetsByMajorClassAxis",
    "FinancialInstrumentAxis",
    "InformationByCategoryOfDebtSecurityAxis",
)
_TARGET_SET = frozenset(TARGET_AXES)

#: lib_2026_constant.xule l.177-194, role URI substrings (lower-cased) that
#: exclude a statement cube.
_STATEMENT_URI_EXCLUDE: Tuple[str, ...] = (
    "parenthetical",
    "equity",
    "deficit",
    "stockholders",
    "capital",
    "investment",
    "changes",
    "shareholder",
    "convertible",
    "preferred",
    "temporaryequity",
    "redeemable",
    "netproceedsfromallsources",
    "membersinterest",
)
_STATEMENT_DESC_EXCLUDE: Tuple[str, ...] = ("schedule iii", "schedule iv")
_SOI_TABLES = frozenset(
    {
        "ScheduleOfInvestmentsTable",
        "SummaryOfInvestmentHoldingsTable",
        "InvestmentsSoldNotYetPurchasedTable",
        "OpenOptionContractsWrittenTable",
        "OpenFuturesContractTable",
        "OpenForwardForeignCurrencyContractTable",
        "OpenSwapContractTable",
    }
)

_REV_606 = frozenset(
    {
        "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax",
        "us-gaap:RevenueFromContractWithCustomerIncludingAssessedTax",
    }
)
_INF = float("inf")

_SUBTOTAL_MODES = ("aggregate", "off", "any", "strict")


@dataclass(frozen=True)
class Options:
    """Switches over the 2026 logic.  ``Options()`` is the 2026 rule.

    The non-default settings exist so the validator can measure which guard
    the practice gold is consistent with; they are not tuning knobs.
    """

    #: l.71, 76-81, 86: skip unless no notes fact carries the axis, or the
    #: largest one exceeds the total.
    notes_guard: bool = True
    #: l.65-67: skip when a parenthetical statement fact carries the axis.
    parenthetical_guard: bool = True
    #: l.112-137: the two FASB 606 revenue exceptions.
    revenue_exceptions: bool = True
    #: l.49-62 ``$SubTotalExists`` / l.279-292 ``CheckSubTotalExists``, over
    #: the members seen on multi-dimension facts at the total's alignment:
    #: ``"aggregate"`` (default, the aggregation reading in the module notes) =
    #: false only when no member has an aligned subtotal and some member has
    #: no subtotal fact at any alignment; ``"off"`` = always true; ``"any"`` /
    #: ``"strict"`` = at least one / every member has an aligned subtotal.
    subtotal_guard: str = "aggregate"
    #: l.30-31 / l.74: only instants and durations equal to the document period.
    period_filter: bool = True
    #: A fact is "in" a cube only if each of its members is declared under the
    #: axis in that cube (XBRL Dimensions validity).  False = axis membership only.
    member_validity: bool = True
    #: Run rule element 10093 as well.
    include_10093: bool = True
    #: tolerance_for_decimals_comp factor (the rule passes 2).
    tolerance_factor: int = 2
    #: Name carried on every finding.
    label: str = "custom"

    def __post_init__(self) -> None:
        if self.subtotal_guard not in _SUBTOTAL_MODES:
            raise ValueError(f"subtotal_guard must be one of {_SUBTOTAL_MODES}, not {self.subtotal_guard!r}")


#: The 2026 source (identical to 2024 and 2025).
FAITHFUL = Options(label="2026")

#: FITTED, not read: the rule as it behaved on the practice filings that use
#: the 2021/2022 us-gaap taxonomies (no 2021-2023 rule file is on disk).  On
#: those 46 practice cases the gold is reproduced only without the notes guard,
#: the parenthetical guard and the 606 revenue exceptions; the duration filter
#: is present.  Its practice score is in-sample.  Never selected for dev/test
#: (all on us-gaap 2023+).
LEGACY = Options(notes_guard=False, parenthetical_guard=False, revenue_exceptions=False, label="legacy-2022")

#: Highest us-gaap taxonomy year handled with LEGACY by ``era="auto"``.
LEGACY_MAX_TAXONOMY_YEAR = 2022

# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

_ATTR_RE = re.compile(r"([\w:.-]+)\s*=\s*\"([^\"]*)\"|([\w:.-]+)\s*=\s*'([^']*)'")


def _attrs(s: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for m in _ATTR_RE.finditer(s or ""):
        if m.group(1) is not None:
            out[m.group(1)] = m.group(2)
        else:
            out[m.group(3)] = m.group(4)
    return out


def _attr_local(a: Dict[str, str], local: str) -> Optional[str]:
    """Attribute value by local name, whatever prefix the filer bound it to."""
    if local in a:
        return a[local]
    for k, v in a.items():
        if k.rsplit(":", 1)[-1] == local:
            return v
    return None


def local(name: Optional[str]) -> str:
    return (name or "").split(":", 1)[-1]


def _dec(text: Optional[str]) -> Optional[Decimal]:
    if text is None:
        return None
    t = text.strip().replace(",", "")
    if not t:
        return None
    try:
        d = Decimal(t)
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def _decimals(text: Optional[str]) -> Optional[float]:
    if text is None:
        return None
    t = text.strip()
    if t.upper() == "INF":
        return _INF
    try:
        return float(int(t))
    except ValueError:
        return None


def _date(s: Optional[str]) -> Optional[date]:
    if not s:
        return None
    try:
        return date.fromisoformat(s.strip()[:10])
    except ValueError:
        return None


def fmt(d: Decimal) -> str:
    """Plain decimal string without exponent; integral values without '.0'."""
    if d == d.to_integral_value():
        return str(d.quantize(Decimal(1)))
    s = format(d.normalize(), "f")
    return s


# --------------------------------------------------------------------------- #
# DTS: role types, definition and calculation linkbases
# --------------------------------------------------------------------------- #

_ROLETYPE_RE = re.compile(
    r"<(?:[\w-]+:)?roleType\b(?P<attrs>[^>]*)>(?P<body>.*?)</(?:[\w-]+:)?roleType>", re.S
)
_DEFINITION_RE = re.compile(r"<(?:[\w-]+:)?definition\b[^>]*>(.*?)</(?:[\w-]+:)?definition>", re.S)
_ELEMENT_RE = re.compile(r"<(?:xs:|xsd:)?element\b(?P<attrs>[^>]*?)/?>", re.S)
_TARGET_NS_RE = re.compile(r"\btargetNamespace\s*=\s*\"([^\"]+)\"")
_XMLNS_RE = re.compile(r"\bxmlns:([\w.-]+)\s*=\s*\"([^\"]+)\"")
_LINK_RE_TMPL = (
    r"<(?:[\w-]+:)?{tag}\b(?P<attrs>[^>]*?)(?:/>|>(?P<body>.*?)</(?:[\w-]+:)?{tag}\s*>)"
)
_LINK_OPEN_TMPL = r"<(?:[\w-]+:)?{tag}\b(?P<attrs>[^>]*?)>"
_LOC_RE = re.compile(r"<(?:[\w-]+:)?loc\b(?P<attrs>[^>]*?)/?>", re.S)


def parse_role_types(xsd_text: str) -> Dict[str, str]:
    """``{roleURI: definition}`` from the schema's ``link:roleType`` elements."""
    out: Dict[str, str] = {}
    for m in _ROLETYPE_RE.finditer(xsd_text or ""):
        a = _attrs(m.group("attrs"))
        uri = a.get("roleURI")
        if not uri:
            continue
        dm = _DEFINITION_RE.search(m.group("body"))
        out[uri] = html.unescape(dm.group(1)).strip() if dm else ""
    return out


@dataclass
class DefArc:
    arcrole: str  #: short arcrole: all / notAll / hypercube-dimension / dimension-domain / domain-member / dimension-default
    frm: str
    to: str
    order: float
    target_role: Optional[str]
    usable: bool
    closed: bool
    context_element: Optional[str]


def _iter_links(text: str, tag: str) -> Iterable[Tuple[Dict[str, str], str]]:
    """Yield ``(attrs, body)`` for every extended link ``tag``; a trailing link
    whose end tag was truncated away is yielded with the body that remains."""
    link_re = re.compile(_LINK_RE_TMPL.format(tag=tag), re.S)
    open_re = re.compile(_LINK_OPEN_TMPL.format(tag=tag), re.S)
    last = 0
    for m in link_re.finditer(text or ""):
        yield _attrs(m.group("attrs")), m.group("body") or ""
        last = m.end()
    om = open_re.search(text or "", last)
    if om and not om.group(0).endswith("/>"):
        yield _attrs(om.group("attrs")), text[om.end():]


class _Names:
    """Resolve linkbase locators to the ``prefix:LocalName`` spelling the
    instance uses.

    Standard-taxonomy element ids follow ``prefix_LocalName``; extension ids are
    looked up in the filing's own schema (id -> name) and given the prefix the
    instance binds to the schema's targetNamespace.
    """

    def __init__(self, xsd_text: str = "", instance_head: str = ""):
        self.ext_ids: Dict[str, str] = {}
        self.ext_prefix: Optional[str] = None
        if xsd_text:
            for m in _ELEMENT_RE.finditer(xsd_text):
                a = _attrs(m.group("attrs"))
                if "id" in a and "name" in a:
                    self.ext_ids[a["id"]] = a["name"]
            tm = _TARGET_NS_RE.search(xsd_text)
            ns = tm.group(1) if tm else None
            if ns and instance_head:
                for p, u in _XMLNS_RE.findall(instance_head):
                    if u == ns:
                        self.ext_prefix = p
                        break

    def concept(self, href: str) -> str:
        frag = href.split("#", 1)[-1]
        schema = href.split("#", 1)[0]
        is_std = schema.startswith("http") or "/" in schema
        if not is_std and frag in self.ext_ids and self.ext_prefix:
            return f"{self.ext_prefix}:{self.ext_ids[frag]}"
        return X.href_to_concept(href)


_SHORT_ARCROLE = {
    "all": "all",
    "notAll": "notAll",
    "hypercube-dimension": "hypercube-dimension",
    "dimension-domain": "dimension-domain",
    "domain-member": "domain-member",
    "dimension-default": "dimension-default",
}


def parse_definition_arcs(text: str, names: _Names) -> Dict[str, List[DefArc]]:
    """``{role: [DefArc...]}``, links of the same role merged (one base set).

    Prohibiting arcs (``use="prohibited"``) remove the equivalent arc.
    """
    out: Dict[str, List[DefArc]] = defaultdict(list)
    prohibited: Set[Tuple[str, str, str, str]] = set()
    arc_re = re.compile(r"<(?:[\w-]+:)?definitionArc\b(?P<attrs>[^>]*?)/?>", re.S)
    for la, body in _iter_links(text, "definitionLink"):
        role = la.get("xlink:role", "") or _attr_local(la, "role") or ""
        locs: Dict[str, List[str]] = defaultdict(list)
        for lm in _LOC_RE.finditer(body):
            a = _attrs(lm.group("attrs"))
            lab = a.get("xlink:label") or _attr_local(a, "label")
            href = a.get("xlink:href") or _attr_local(a, "href")
            if lab and href:
                locs[lab].append(names.concept(href))
        for am in arc_re.finditer(body):
            a = _attrs(am.group("attrs"))
            arcrole = (a.get("xlink:arcrole") or _attr_local(a, "arcrole") or "").rsplit("/", 1)[-1]
            short = _SHORT_ARCROLE.get(arcrole)
            if short is None:
                continue
            fl = a.get("xlink:from") or _attr_local(a, "from") or ""
            tl = a.get("xlink:to") or _attr_local(a, "to") or ""
            try:
                order = float(a.get("order", "1"))
            except ValueError:
                order = 1.0
            usable = (_attr_local(a, "usable") or "true").strip().lower() not in ("false", "0")
            closed = (_attr_local(a, "closed") or "false").strip().lower() in ("true", "1")
            for f in locs.get(fl, []):
                for t in locs.get(tl, []):
                    if (a.get("use") or "").lower() == "prohibited":
                        prohibited.add((role, short, f, t))
                        continue
                    out[role].append(
                        DefArc(short, f, t, order, _attr_local(a, "targetRole"), usable, closed,
                               _attr_local(a, "contextElement"))
                    )
    if prohibited:
        for role in list(out):
            out[role] = [x for x in out[role] if (role, x.arcrole, x.frm, x.to) not in prohibited]
    return dict(out)


def parse_calc_children(text: str, names: _Names) -> Dict[str, Dict[str, List[Tuple[str, float]]]]:
    """``{role: {parent: [(child, weight), ...]}}`` from a calculation linkbase."""
    out: Dict[str, Dict[str, List[Tuple[str, float]]]] = defaultdict(lambda: defaultdict(list))
    arc_re = re.compile(r"<(?:[\w-]+:)?calculationArc\b(?P<attrs>[^>]*?)/?>", re.S)
    for la, body in _iter_links(text, "calculationLink"):
        role = la.get("xlink:role", "") or _attr_local(la, "role") or ""
        locs: Dict[str, List[str]] = defaultdict(list)
        for lm in _LOC_RE.finditer(body):
            a = _attrs(lm.group("attrs"))
            lab = a.get("xlink:label") or _attr_local(a, "label")
            href = a.get("xlink:href") or _attr_local(a, "href")
            if lab and href:
                locs[lab].append(names.concept(href))
        for am in arc_re.finditer(body):
            a = _attrs(am.group("attrs"))
            arcrole = a.get("xlink:arcrole") or _attr_local(a, "arcrole") or ""
            if arcrole and not arcrole.endswith("summation-item"):
                continue
            if (a.get("use") or "").lower() == "prohibited":
                continue
            try:
                w = float(a.get("weight", "1"))
            except ValueError:
                w = 1.0
            for f in locs.get(a.get("xlink:from") or _attr_local(a, "from") or "", []):
                for t in locs.get(a.get("xlink:to") or _attr_local(a, "to") or "", []):
                    out[role][f].append((t, w))
    return {r: dict(v) for r, v in out.items()}


@dataclass
class Cube:
    """One XULE cube: a hypercube reached by has-hypercube arcs in ``role``."""

    role: str
    description: str
    hypercube: str
    closed: bool
    primary: Set[str] = field(default_factory=set)
    dims: List[str] = field(default_factory=list)
    #: dimension -> its dimension-domain targets (``$domain``)
    domain: Dict[str, Set[str]] = field(default_factory=dict)
    #: dimension -> every DRS descendant (domain included; ``$members``)
    members: Dict[str, Set[str]] = field(default_factory=dict)
    #: dimension -> usable descendants (what a context may carry)
    usable: Dict[str, Set[str]] = field(default_factory=dict)
    #: dimension -> member -> domain-member parents
    parents: Dict[str, Dict[str, Set[str]]] = field(default_factory=dict)

    @property
    def is_statement(self) -> bool:
        """``$STATEMENT_CUBES`` membership (lib_2026_constant.xule l.177-194)."""
        if "- Statement -" not in self.description:
            return False
        uri = self.role.lower()
        if any(s in uri for s in _STATEMENT_URI_EXCLUDE):
            return False
        d = self.description.lower()
        if any(s in d for s in _STATEMENT_DESC_EXCLUDE):
            return False
        return local(self.hypercube) not in _SOI_TABLES

    @property
    def is_parenthetical(self) -> bool:
        """``$STATEMENT_PARENTHETICAL_CUBES`` (lib_2026_constant.xule l.196-197)."""
        return "- Statement -" in self.description and "parenthetical" in self.role.lower()

    @property
    def is_notes(self) -> bool:
        """``$NOTES_CUBES`` (lib_2026_constant.xule l.420)."""
        return "- Disclosure -" in self.description

    def ancestors(self, dim: str, member: str) -> Set[str]:
        """``navigate dimensions domain-member ancestors`` within this DRS."""
        par = self.parents.get(dim, {})
        seen: Set[str] = set()
        stack = list(par.get(member, ()))
        while stack:
            p = stack.pop()
            if p in seen:
                continue
            seen.add(p)
            stack.extend(par.get(p, ()))
        return seen


def build_cubes(arcs_by_role: Dict[str, List[DefArc]], role_desc: Dict[str, str]) -> List[Cube]:
    """Every (role, hypercube) reached by an ``all`` arc, as XULE's ``taxonomy().cubes``.

    targetRole is honoured on every consecutive arc.  ``notAll`` (negative)
    cubes are not built: no practice or dev filing contains a notAll arc.
    """
    by_role_from: Dict[Tuple[str, str, str], List[DefArc]] = defaultdict(list)
    for role, arcs in arcs_by_role.items():
        for a in arcs:
            by_role_from[(role, a.arcrole, a.frm)].append(a)
    cubes: Dict[Tuple[str, str], Cube] = {}
    for role, arcs in arcs_by_role.items():
        for a in arcs:
            if a.arcrole != "all":
                continue
            key = (role, a.to)
            cube = cubes.get(key)
            if cube is None:
                cube = Cube(role=role, description=role_desc.get(role, ""), hypercube=a.to, closed=a.closed)
                cubes[key] = cube
                hd_role = a.target_role or role
                for hd in sorted(by_role_from.get((hd_role, "hypercube-dimension", a.to), []), key=lambda x: x.order):
                    dim = hd.to
                    if dim in cube.domain:
                        continue
                    cube.dims.append(dim)
                    dd_role = hd.target_role or hd_role
                    doms: Set[str] = set()
                    members: Set[str] = set()
                    usable: Set[str] = set()
                    parents: Dict[str, Set[str]] = defaultdict(set)
                    stack: List[Tuple[str, str]] = []
                    for dd in by_role_from.get((dd_role, "dimension-domain", dim), []):
                        doms.add(dd.to)
                        members.add(dd.to)
                        if dd.usable:
                            usable.add(dd.to)
                        stack.append((dd.to, dd.target_role or dd_role))
                    seen: Set[Tuple[str, str]] = set()
                    while stack:
                        node, r = stack.pop()
                        if (node, r) in seen:
                            continue
                        seen.add((node, r))
                        for dm in by_role_from.get((r, "domain-member", node), []):
                            members.add(dm.to)
                            if dm.usable:
                                usable.add(dm.to)
                            parents[dm.to].add(node)
                            stack.append((dm.to, dm.target_role or r))
                    cube.domain[dim] = doms
                    cube.members[dim] = members
                    cube.usable[dim] = usable
                    cube.parents[dim] = dict(parents)
            # primary items: the 'all' source and its domain-member descendants in this role
            stack2 = [(a.frm, role)]
            seen2: Set[Tuple[str, str]] = set()
            while stack2:
                node, r = stack2.pop()
                if (node, r) in seen2:
                    continue
                seen2.add((node, r))
                cube.primary.add(node)
                for dm in by_role_from.get((r, "domain-member", node), []):
                    stack2.append((dm.to, dm.target_role or r))
    return list(cubes.values())


def dimension_defaults(arcs_by_role: Dict[str, List[DefArc]]) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for arcs in arcs_by_role.values():
        for a in arcs:
            if a.arcrole == "dimension-default":
                out.setdefault(a.frm, a.to)
    return out


# --------------------------------------------------------------------------- #
# Instance
# --------------------------------------------------------------------------- #


@dataclass(frozen=True)
class F:
    """A numeric fact with the aspects XULE aligns on."""

    concept: str
    value: Optional[Decimal]  #: None for xsi:nil
    decimals: Optional[float]
    unit: str
    monetary: bool
    period: Tuple[Optional[str], Optional[str], Optional[str]]  #: (start, end, instant)
    days: Optional[int]
    entity: Optional[str]
    dims: Tuple[Tuple[str, str], ...]  #: sorted (dimension, member)
    pos: int

    @property
    def nil(self) -> bool:
        return self.value is None

    def dim(self, d: str) -> Optional[str]:
        for k, v in self.dims:
            if k == d:
                return v
        return None

    @property
    def a4(self) -> tuple:
        """XULE alignment once dimensions are named, covered or closed away:
        concept, period, unit, entity."""
        return (self.concept, self.period, self.unit, self.entity)

    def align(self, *covered: str) -> tuple:
        """Full aspect key: every aspect except the covered dimensions."""
        return (
            self.concept,
            self.period,
            self.unit,
            self.entity,
            tuple((k, v) for k, v in self.dims if k not in covered),
        )


def _period_days(start: Optional[str], end: Optional[str], instant: Optional[str]) -> Optional[int]:
    if instant:
        return 0
    s, e = _date(start), _date(end)
    if s is None or e is None:
        return None
    # Arelle/XULE store a date-only endDate as the following midnight.
    return (e - s).days + 1


def _is_monetary_unit(unit: str) -> bool:
    if not unit or "/" in unit:
        return False
    return unit.split(":", 1)[0].lower() == "iso4217"


def facts_from_instance(doc: X.InstanceDoc) -> Tuple[List[F], Optional[F]]:
    """Numeric facts (nil kept) and the DocumentType fact (value None)."""
    out: List[F] = []
    doc_type: Optional[F] = None
    for f in doc.facts:
        ctx = doc.contexts.get(f.context_ref)
        if ctx is None:
            continue
        days = _period_days(ctx.start, ctx.end, ctx.instant)
        dims = tuple(sorted(ctx.dims))
        if local(f.concept) == "DocumentType" and doc_type is None:
            doc_type = F(f.concept, None, None, "", False, ctx.period_key, days, ctx.entity, dims, f.pos)
            continue
        if f.unit_ref is None:
            continue  # not numeric
        unit = doc.units.get(f.unit_ref, "")
        if f.nil:
            value = None
        else:
            value = _dec(f.value)
            if value is None:
                continue
        out.append(
            F(f.concept, value, _decimals(f.decimals), unit, _is_monetary_unit(unit), ctx.period_key, days,
              ctx.entity, dims, f.pos)
        )
    return out, doc_type


def _dedupe(facts: Sequence[F]) -> List[F]:
    """One fact per full aspect set: XULE sees duplicate facts once; when they
    disagree the most precise is kept."""
    best: Dict[tuple, F] = {}
    order: List[tuple] = []
    for f in facts:
        k = f.align()
        cur = best.get(k)
        if cur is None:
            best[k] = f
            order.append(k)
            continue
        fd = -_INF if f.decimals is None else f.decimals
        cd = -_INF if cur.decimals is None else cur.decimals
        if cur.nil and not f.nil:
            best[k] = f
        elif not f.nil and fd > cd:
            best[k] = f
    return [best[k] for k in order]


# --------------------------------------------------------------------------- #
# Filing (DTS + facts)
# --------------------------------------------------------------------------- #


@dataclass(eq=False)
class Filing:
    cubes: List[Cube]
    defaults: Dict[str, str]
    calc: Dict[str, Dict[str, List[Tuple[str, float]]]]
    facts: List[F]
    doc_type: Optional[F]
    source: str  #: "filing" (complete DTS) or "released" (query sections only)
    released_roles: Set[str] = field(default_factory=set)
    #: roleURI -> roleType definition (what ``drs-role.description`` reads)
    role_desc: Dict[str, str] = field(default_factory=dict)
    _by_concept: Dict[str, List[F]] = field(default_factory=dict, repr=False)
    _cube_cache: Dict[tuple, object] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        idx: Dict[str, List[F]] = defaultdict(list)
        for f in self.facts:
            idx[f.concept].append(f)
        self._by_concept = dict(idx)

    # ---- cube membership ------------------------------------------------- #
    def in_cube(self, f: F, cube: Cube, opts: Options) -> bool:
        """XULE ``@cube``: concept is a primary item; every fact dimension is a
        cube dimension carrying a usable member; every other cube dimension has a
        default."""
        if f.concept not in cube.primary:
            return False
        fd = dict(f.dims)
        for d, m in fd.items():
            if d not in cube.domain:
                if cube.closed:
                    return False
                continue
            if opts.member_validity and not m.startswith("<typed>") and m not in cube.usable.get(d, ()):
                return False
        for d in cube.dims:
            if d not in fd and d not in self.defaults:
                return False
        return True

    def cube_facts(self, cube: Cube, opts: Options) -> Tuple[F, ...]:
        key = ("cube", id(cube), opts.member_validity)
        hit = self._cube_cache.get(key)
        if hit is None:
            hit = tuple(sorted(
                (f for c in cube.primary for f in self._by_concept.get(c, ()) if self.in_cube(f, cube, opts)),
                key=lambda f: f.pos,
            ))
            self._cube_cache[key] = hit
        return hit  # type: ignore[return-value]


def _instance_head(text: str) -> str:
    i = text.find("<context")
    j = text.find("<xbrli:context")
    cut = min([k for k in (i, j) if k >= 0], default=4000)
    return text[: max(cut, 0) or 4000]


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _filing_files(filing_dir: Path) -> Dict[str, Path]:
    out: Dict[str, Path] = {}
    for p in filing_dir.iterdir():
        n = p.name
        if n.endswith("_def.xml"):
            out["def"] = p
        elif n.endswith("_cal.xml"):
            out["cal"] = p
        elif n.endswith("_htm.xml"):
            out["ins"] = p
        elif n.endswith(".xsd"):
            out["xsd"] = p
    return out


@functools.lru_cache(maxsize=8)
def _load_dts(filing_dir: str, instance_head: str):
    files = _filing_files(Path(filing_dir))
    xsd = _read(files["xsd"]) if "xsd" in files else ""
    names = _Names(xsd, instance_head)
    role_desc = parse_role_types(xsd)
    arcs = parse_definition_arcs(_read(files["def"]), names) if "def" in files else {}
    calc = parse_calc_children(_read(files["cal"]), names) if "cal" in files else {}
    return build_cubes(arcs, role_desc), dimension_defaults(arcs), calc, role_desc


@functools.lru_cache(maxsize=4)
def _load_instance_file(path: str):
    return facts_from_instance(X.parse_instance(_read(Path(path))))


def _released_roles(sections: Dict[str, str]) -> Set[str]:
    roles: Set[str] = set()
    for k in ("presentation", "calculation", "definition"):
        for m in re.finditer(r"<(?:[\w-]+:)?(?:presentation|calculation|definition)Link\b[^>]*?xlink:role=[\"']([^\"']+)[\"']",
                             sections.get(k, "") or ""):
            roles.add(m.group(1))
    return roles


@functools.lru_cache(maxsize=2)
def _instance_from_query(instance_text: str):
    doc = X.parse_instance(instance_text)
    return doc, facts_from_instance(doc)


_FILING_CACHE: Dict[tuple, Filing] = {}


def load_filing(query: str, filing_dir: Optional[Union[str, Path]] = None, *,
                assume_released_statements: bool = False) -> Filing:
    """Cached :func:`build_filing` (cases of one filing share the object)."""
    sections = X.split_sections(query)
    inst = sections.get("instance", "")
    key = (str(filing_dir) if filing_dir else None, len(inst), hash(inst), frozenset(_released_roles(sections)),
           bool(assume_released_statements))
    hit = _FILING_CACHE.get(key)
    if hit is None:
        if len(_FILING_CACHE) >= 3:
            _FILING_CACHE.pop(next(iter(_FILING_CACHE)))
        hit = build_filing(query, filing_dir, assume_released_statements=assume_released_statements)
        _FILING_CACHE[key] = hit
    return hit


def build_filing(query: str, filing_dir: Optional[Union[str, Path]] = None, *,
                 assume_released_statements: bool = False) -> Filing:
    """Build the DTS and fact list for one case.

    With ``filing_dir`` the complete schema/definition/calculation files are used
    (exact statement / parenthetical / notes classification).  The facts come
    from the query's Instance when it is complete, else from ``<stem>_htm.xml``.
    Without it only the released sections exist; a released role is a statement
    only if the released Schema section defines it so (lib_2026_constant.xule
    l.177 reads the role definition), unless ``assume_released_statements``.
    """
    sections = X.split_sections(query)
    inst_text = sections.get("instance", "")
    doc, (facts, doc_type) = _instance_from_query(inst_text)
    released = _released_roles(sections)
    fdir = Path(filing_dir) if filing_dir else None
    if fdir is not None and fdir.is_dir():
        files = _filing_files(fdir)
        if not doc.complete and "ins" in files:
            facts, doc_type = _load_instance_file(str(files["ins"]))
        cubes, defaults, calc, role_desc = _load_dts(str(fdir), _instance_head(inst_text))
        return Filing(cubes, defaults, calc, _dedupe(facts), doc_type, "filing", released, dict(role_desc))
    # Released, statement-scoped sections only.
    schema = sections.get("schema", "")
    schema = "" if schema.strip() in ("", "None", "null") else schema
    names = _Names(schema, _instance_head(inst_text))
    role_desc = parse_role_types(schema)
    arcs = parse_definition_arcs(sections.get("definition", ""), names)
    if assume_released_statements:
        for role in arcs:
            if not role_desc.get(role):
                role_desc[role] = "- Statement - (assumed: released section)"
    cubes = build_cubes(arcs, role_desc)
    calc = parse_calc_children(sections.get("calculation", ""), names)
    return Filing(cubes, dimension_defaults(arcs), calc, _dedupe(facts), doc_type, "released", released, role_desc)


# --------------------------------------------------------------------------- #
# tolerance_for_decimals_comp (lib_functions.xule l.209-248)
# --------------------------------------------------------------------------- #


def tolerance_for_decimals_comp(left: Decimal, left_decimals: Optional[float], right: Decimal,
                                right_decimals: Optional[float], min_decimals: Optional[float],
                                factor: int = 2) -> bool:
    """True when the two values differ by more than the decimals tolerance."""
    if min_decimals is None:
        min_adj: float = 5
    elif min_decimals == _INF:
        min_adj = 5
    else:
        min_adj = 5 if min_decimals > 5 else min_decimals
    ld = min_adj if (left_decimals is None or left_decimals == _INF) else left_decimals
    rd = min_adj if (right_decimals is None or right_decimals == _INF) else right_decimals
    t1 = ld if ld < rd else rd
    if t1 == _INF:
        return abs(left - right) > 0
    t1i = int(t1)
    tol = Decimal(10) ** (-t1i) * factor
    return abs(round(left, t1i) - round(right, t1i)) > tol


# --------------------------------------------------------------------------- #
# The rule
# --------------------------------------------------------------------------- #


def _summation_descendants(calc_role: Dict[str, List[Tuple[str, float]]], top: str) -> Set[str]:
    """``navigate summation-item descendants from top role R returns set target-name``."""
    seen: Set[str] = set()
    stack = [c for c, _ in calc_role.get(top, [])]
    while stack:
        c = stack.pop()
        if c in seen:
            continue
        seen.add(c)
        stack.extend(ch for ch, _ in calc_role.get(c, []))
    return seen


@dataclass
class RoleView:
    """A statement drs-role as XULE's factsets and navigations see it.

    ``@cube.drs-role = R`` admits a fact that is in *any* cube of role R, and
    ``navigate dimensions ... drs-role R`` walks every DRS arc of that role, so
    the role's hypercubes are merged here.  ``$drs_roles`` (l.22) iterates the
    role's statement cubes one by one; the message count is kept per axis.
    """

    role: str
    description: str
    cubes: List[Cube]
    #: target-axis candidates in order: dimensions of the role's statement cubes
    dims: List[str]
    #: the role's ``$STATEMENT_CUBES`` members, file order (``$bs_cubes``, l.112)
    stmt_cubes: List[Cube]

    def domain(self, dim: str) -> Set[str]:
        out: Set[str] = set()
        for c in self.cubes:
            out |= c.domain.get(dim, set())
        return out

    def members(self, dim: str) -> Set[str]:
        out: Set[str] = set()
        for c in self.cubes:
            out |= c.members.get(dim, set())
        return out

    def ancestors(self, dim: str, member: str) -> Set[str]:
        out: Set[str] = set()
        for c in self.cubes:
            if dim in c.parents:
                out |= c.ancestors(dim, member)
        return out

    def n_messages(self, dim: str) -> int:
        """How many ``$drs_roles`` entries (statement cubes) iterate ``dim``."""
        return sum(1 for c in self.stmt_cubes if dim in c.domain)


def statement_roles(fl: Filing) -> List[RoleView]:
    """``$drs_roles`` (l.22) grouped by drs-role."""
    order: List[str] = []
    stmt: Dict[str, List[Cube]] = defaultdict(list)
    for c in fl.cubes:
        if c.is_statement:
            if c.role not in stmt:
                order.append(c.role)
            stmt[c.role].append(c)
    out: List[RoleView] = []
    for role in order:
        dims: List[str] = []
        for c in stmt[role]:
            for d in c.dims:
                if d not in dims:
                    dims.append(d)
        all_cubes = [c for c in fl.cubes if c.role == role]
        out.append(RoleView(role, stmt[role][0].description, all_cubes, dims, list(stmt[role])))
    return out


def _role_facts(fl: Filing, rv: RoleView, opts: Options) -> Tuple[F, ...]:
    key = ("role", rv.role, opts.member_validity)
    hit = fl._cube_cache.get(key)  # type: ignore[arg-type]
    if hit is None:
        seen: Dict[int, F] = {}
        for c in rv.cubes:
            for f in fl.cube_facts(c, opts):
                seen.setdefault(id(f), f)
        hit = tuple(sorted(seen.values(), key=lambda f: f.pos))
        fl._cube_cache[key] = hit  # type: ignore[index]
    return hit  # type: ignore[return-value]


def _other_cube_facts(fl: Filing, dim: str, opts: Options) -> Tuple[Dict[tuple, List[F]], Dict[tuple, List[F]]]:
    """l.65 / l.71 ``[nonils @cube in $STATEMENT_PARENTHETICAL_CUBES / $NOTES_CUBES
    @$dim = *]`` (closed: the axis is the fact's only dimension), keyed by the
    alignment (concept, period, unit, entity)."""
    key = ("other", dim, opts.member_validity)
    hit = fl._cube_cache.get(key)  # type: ignore[arg-type]
    if hit is None:
        paren: Dict[tuple, List[F]] = defaultdict(list)
        notes: Dict[tuple, List[F]] = defaultdict(list)
        seen_p: Set[int] = set()
        seen_n: Set[int] = set()
        for other in fl.cubes:
            if not (other.is_parenthetical or other.is_notes) or dim not in other.domain:
                continue
            for f in fl.cube_facts(other, opts):
                if f.nil or len(f.dims) != 1 or f.dims[0][0] != dim:
                    continue
                if other.is_parenthetical and id(f) not in seen_p:
                    seen_p.add(id(f))
                    paren[f.a4].append(f)
                if other.is_notes and id(f) not in seen_n:
                    seen_n.add(id(f))
                    notes[f.a4].append(f)
        hit = (dict(paren), dict(notes))
        fl._cube_cache[key] = hit  # type: ignore[index]
    return hit  # type: ignore[return-value]


def _notes_pairs(fl: Filing, dim: str, dim2: str, opts: Options) -> Dict[Tuple[str, tuple], List[F]]:
    """l.219 ``[nonils @cube in $NOTES_CUBES @$dim = s @$Dim2Dimension = *]``
    (closed: exactly those two dimensions), keyed by (s, alignment)."""
    key = ("notes2", dim, dim2, opts.member_validity)
    hit = fl._cube_cache.get(key)  # type: ignore[arg-type]
    if hit is None:
        out: Dict[Tuple[str, tuple], List[F]] = defaultdict(list)
        seen: Set[int] = set()
        for other in fl.cubes:
            if not other.is_notes or dim not in other.domain or dim2 not in other.domain:
                continue
            for f in fl.cube_facts(other, opts):
                if f.nil or len(f.dims) != 2 or id(f) in seen:
                    continue
                s = f.dim(dim)
                if s is None or f.dim(dim2) is None:
                    continue
                seen.add(id(f))
                out[(s, f.a4)].append(f)
        hit = dict(out)
        fl._cube_cache[key] = hit  # type: ignore[index]
    return hit  # type: ignore[return-value]


def _period_ok(t: F, doc_days: Optional[int], opts: Options) -> bool:
    if not opts.period_filter:
        return True
    return t.days == 0 or (doc_days is not None and t.days == doc_days)


def _subtotal_ok(have: List[bool], anywhere: List[bool], mode: str) -> bool:
    """``all(set(for $m in members exists([...])))`` under the chosen reading.

    ``have[i]``: member i has an aligned subtotal fact; ``anywhere[i]``: the
    factset of member i is non-empty at some alignment.  "aggregate": the
    aligned ``true`` values form the total's group (-> true); a member whose
    factset is empty everywhere makes ``exists`` return an unaligned ``false``,
    which is all the total sees when it has no group (-> false); otherwise the
    total has no value and gets ``all``'s default (-> true)."""
    if mode == "off" or not have:
        return True
    if mode == "strict":
        return all(have)
    if mode == "any":
        return any(have)
    return any(have) or all(anywhere)


def _is_srt_product_axis(dim: str) -> bool:
    return local(dim) == "ProductOrServiceAxis" and dim.split(":", 1)[0] == "srt"


def _rev606(prim: Set[str], member_sum: Decimal, total: Decimal, fl: Filing, role: str, tol) -> Tuple[str, bool]:
    """l.114-134 for one candidate ``$bs_cube``: (exception name, fires)."""
    if "us-gaap:NoninterestIncome" in prim:  # l.116-123
        return "noninterest-income", tol() and member_sum > total
    if member_sum < total and "us-gaap:Revenues" in prim:  # l.125-131
        comps = _summation_descendants(fl.calc.get(role, {}), "us-gaap:Revenues")
        if len(comps) > 1 and comps & _REV_606:
            return "revenues-calc-includes-606", False
        return "revenues-calc-lacks-606", tol()
    return "606-without-noninterest-income", tol()  # l.132-134


def _rule_9574(fl: Filing, rv: RoleView, dim: str, opts: Options, want: Optional[Tuple[str, tuple]]) -> List[dict]:
    facts = _role_facts(fl, rv, opts)
    dom = rv.domain(dim)
    member_desc = rv.members(dim) - dom  # l.84
    default = fl.defaults.get(dim)
    doc_days = fl.doc_type.days if fl.doc_type is not None else None

    # Closed one-dimension factsets [@$dim = m] keyed by (m, alignment); nil kept
    # (l.59 has no nonils).  l.49/54: members of the axis on non-nil monetary
    # facts with the axis and more than one dimension, per alignment.
    one: Dict[Tuple[str, tuple], List[F]] = defaultdict(list)
    multi_members: Dict[tuple, Set[str]] = defaultdict(set)
    for f in facts:
        m = f.dim(dim)
        if m is None:
            continue
        if len(f.dims) == 1:
            one[(m, f.a4)].append(f)
        elif not f.nil and f.monetary:
            multi_members[f.a4].add(m)
    # l.59 factset non-empty at some alignment (monetary, nil kept)
    one_anywhere = {m for (m, _a), fs in one.items() if any(f.monetary for f in fs)}

    paren: Dict[tuple, List[F]] = {}
    notes: Dict[tuple, List[F]] = {}
    if opts.parenthetical_guard or opts.notes_guard:
        paren, notes = _other_cube_facts(fl, dim, opts)

    out: List[dict] = []
    for t in facts:
        # $TotalDefault (l.74): closed [nonils @cube.drs-role = R @$dim in $domain
        # where monetary and duration ok] -- no dimension but the axis at a domain member
        if t.nil or not t.monetary:
            continue
        if t.dims:
            if len(t.dims) != 1 or t.dims[0][0] != dim or t.dims[0][1] not in dom:
                continue
        elif default is None or default not in dom:
            continue
        if not _period_ok(t, doc_days, opts):
            continue
        if want is not None and (t.concept, t.period) != want:
            continue
        A = t.a4

        # l.49-62 $SubTotalExists at this alignment
        subs = multi_members.get(A)
        if subs and opts.subtotal_guard != "off":
            have = [any(f.monetary for f in one.get((s, A), ())) for s in sorted(subs)]
            anywhere = [s in one_anywhere for s in sorted(subs)]
            if not _subtotal_ok(have, anywhere, opts.subtotal_guard):
                continue
        # l.65-67 parenthetical guard
        if opts.parenthetical_guard and paren.get(A):
            continue
        # l.71, 76-81 notes guard: run only if no notes fact, or the largest exceeds the total
        if opts.notes_guard and notes.get(A):
            if not (max(f.value for f in notes[A]) > t.value):
                continue

        # l.88-93 member facts, highest reported level only
        members: List[F] = []
        for m in sorted(member_desc):
            anc = rv.ancestors(dim, m) - dom
            if any(not f.nil and f.monetary for a in anc for f in one.get((a, A), ())):
                continue
            mf = [f for f in one.get((m, A), ()) if not f.nil and f.monetary]
            if mf:
                members.append(mf[0])
        if not members:  # l.95
            continue
        member_sum = sum((f.value for f in members), Decimal(0))
        decs = [f.decimals for f in members if f.decimals is not None]
        min_dec = min(decs) if decs else None

        def tol() -> bool:
            return tolerance_for_decimals_comp(member_sum, None, t.value, t.decimals, min_dec, opts.tolerance_factor)

        exception = None
        order_sensitive = False
        if opts.revenue_exceptions and t.concept in _REV_606 and _is_srt_product_axis(dim) and rv.stmt_cubes:
            # l.112-115: $bs_cubes[1] -- first statement cube of the role (file order here)
            outcomes = [_rev606(c.primary, member_sum, t.value, fl, rv.role, tol) for c in rv.stmt_cubes]
            exception, fires = outcomes[0]
            order_sensitive = len({o[1] for o in outcomes}) > 1
        else:
            fires = tol()
        if fires:
            fd = _finding("9574", rv, dim, t, members, member_sum, min_dec, fl, exception, opts)
            fd["exception_order_sensitive"] = order_sensitive
            out.append(fd)
    return out


def _rule_10093(fl: Filing, rv: RoleView, dim: str, opts: Options, want: Optional[Tuple[str, tuple]]) -> List[dict]:
    facts = _role_facts(fl, rv, opts)
    doc_days = fl.doc_type.days if fl.doc_type is not None else None
    # l.196 {covered-dims nonils @$dim = * where monetary and exactly 2 dimensions}, per alignment
    two: Dict[tuple, List[F]] = defaultdict(list)
    # l.214 {covered-dims nonils @$dim = s @Dim2 = * where monetary and > 2 dimensions}
    more: Dict[Tuple[str, tuple], List[F]] = defaultdict(list)
    # l.288 closed [@$dim = s @Dim2 = ss] (nil kept), keyed (s, Dim2, ss, alignment)
    pair: Dict[Tuple[str, str, str, tuple], List[F]] = defaultdict(list)
    for f in facts:
        s = f.dim(dim)
        if s is None:
            continue
        if len(f.dims) == 2:
            k2, m2 = next((k, v) for k, v in f.dims if k != dim)
            pair[(s, k2, m2, f.a4)].append(f)
            if not f.nil and f.monetary:
                two[f.a4].append(f)
        elif len(f.dims) > 2 and not f.nil and f.monetary:
            more[(s, f.a4)].append(f)
    if not two:  # l.198
        return []
    # l.288 factset non-empty at some alignment (monetary, nil kept)
    pair_anywhere = {(s, k2, m2) for (s, k2, m2, _a), fs in pair.items() if any(f.monetary for f in fs)}
    out: List[dict] = []
    for t in facts:
        # l.222 $TotalDefault: closed [nonils @$dim = s where monetary and duration ok]
        if t.nil or not t.monetary or len(t.dims) != 1 or t.dims[0][0] != dim:
            continue
        if not _period_ok(t, doc_days, opts):
            continue
        if want is not None and (t.concept, t.period) != want:
            continue
        s = t.dims[0][1]
        A = t.a4
        d2facts = [f for f in two.get(A, ()) if f.dim(dim) == s]  # l.203-208 at this alignment
        if not d2facts:
            continue
        # l.210-212: first() of the set of other dimensions -- unordered, so every candidate
        cands = sorted({k for f in d2facts for k, _ in f.dims if k != dim})
        for dim2 in cands:
            if local(dim2) == "LegalEntityAxis":  # l.232
                continue
            # l.214-216 CheckSubTotalExists (l.279-292)
            mo = [f for f in more.get((s, A), ()) if f.dim(dim2) is not None]
            if mo and opts.subtotal_guard != "off":
                subsub = sorted({f.dim(dim2) for f in mo})
                have = [any(f.monetary for f in pair.get((s, dim2, ss, A), ())) for ss in subsub]
                anywhere = [(s, dim2, ss) in pair_anywhere for ss in subsub]
                if not _subtotal_ok(have, anywhere, opts.subtotal_guard):
                    continue
            # l.219-230 notes guard on {D = s, Dim2 = *}
            if opts.notes_guard:
                nf = _notes_pairs(fl, dim, dim2, opts).get((s, A))
                if nf and not (max(f.value for f in nf) > t.value):
                    continue
            # l.233 closed [covered-dims nonils @$dim = s @Dim2 = *]: exactly {D = s, Dim2 = m}
            members = [f for f in d2facts if f.dim(dim2) is not None]
            if not members:
                continue
            member_sum = sum((f.value for f in members), Decimal(0))
            decs = [f.decimals for f in members if f.decimals is not None]
            min_dec = min(decs) if decs else None
            if tolerance_for_decimals_comp(member_sum, None, t.value, t.decimals, min_dec, opts.tolerance_factor):
                fd = _finding("10093", rv, dim, t, members, member_sum, min_dec, fl, None, opts, member_axis=dim2)
                fd["sub_member"] = s
                fd["dim2"] = dim2
                fd["dim2_candidates"] = cands
                fd["dim2_ambiguous"] = len(cands) > 1
                out.append(fd)
    return out


def _finding(rule_element: str, rv: RoleView, dim: str, t: F, members: List[F], member_sum: Decimal,
             min_dec: Optional[float], fl: Filing, exception: Optional[str], opts: Options,
             member_axis: Optional[str] = None) -> dict:
    axis_for_members = member_axis or dim
    start, end, instant = t.period
    return {
        "rule_element": rule_element,
        "axis": dim,
        "members": [(m.dim(axis_for_members) or "", fmt(m.value)) for m in members],
        "member_sum": fmt(member_sum),
        "total": fmt(t.value),
        "statement_role": rv.role,
        "statement_description": rv.description,
        "concept": t.concept,
        "period": {"start": start, "end": end, "instant": instant},
        "total_dims": [list(d) for d in t.dims],
        "total_decimals": t.decimals,
        "min_decimals": min_dec,
        "exception": exception,
        "n_messages": rv.n_messages(dim),
        "in_released_role": rv.role in fl.released_roles,
        "dts": fl.source,
        "era": opts.label,
    }


def _all_findings(fl: Filing, opts: Options, want: Optional[Tuple[str, tuple]]) -> List[dict]:
    out: List[dict] = []
    for rv in statement_roles(fl):
        for dim in rv.dims:
            if local(dim) not in _TARGET_SET:  # l.38
                continue
            out.extend(_rule_9574(fl, rv, dim, opts, want))
            if opts.include_10093:
                out.extend(_rule_10093(fl, rv, dim, opts, want))
    return out


def _question_key(query: str, fl: Filing) -> Tuple[str, tuple]:
    q = X.parse_question(query)
    concept = q.concept
    present = {f.concept for f in fl.facts}
    if concept not in present:
        alts = [c for c in present if local(c) == local(concept)]
        if len(alts) == 1:
            concept = alts[0]
    return concept, q.period_key


_USGAAP_YEAR_RE = re.compile(r"fasb\.org/us-gaap/(\d{4})")


def us_gaap_year(query: str) -> Optional[int]:
    """Year of the us-gaap taxonomy the filing's instance imports."""
    inst = query.split("##Instance document", 1)[-1]
    m = _USGAAP_YEAR_RE.search(inst[:200000]) or _USGAAP_YEAR_RE.search(query)
    return int(m.group(1)) if m else None


def options_for(query: str, era: str = "2026") -> Options:
    """``"2026"`` (default): the source.  ``"legacy"``: the fitted LEGACY variant.
    ``"auto"``: LEGACY for filings on the 2021/2022 us-gaap taxonomies, the 2026
    rule otherwise (fitted on practice; equals ``"2026"`` on every dev/test case)."""
    if era == "2026":
        return FAITHFUL
    if era == "legacy":
        return LEGACY
    if era != "auto":
        raise ValueError(f"era must be '2026', 'legacy' or 'auto', not {era!r}")
    y = us_gaap_year(query)
    return LEGACY if (y is not None and y <= LEGACY_MAX_TAXONOMY_YEAR) else FAITHFUL


def findings_0117(query: str, filing_dir: Optional[Union[str, Path]] = None,
                  options: Optional[Options] = None, *, era: str = "2026",
                  all_alignments: bool = False, assume_released_statements: bool = False) -> List[dict]:
    """DQC_US_0117 findings for the questioned concept and period.

    Returns one dict per (statement role, axis, total fact) that fails, with
    ``axis``, ``members`` [(member, value)], ``member_sum``, ``total``,
    ``statement_role`` plus diagnostics: ``rule_element`` (9574 / 10093),
    ``total_dims`` (empty for the dimension-free total the question asks about),
    ``exception`` / ``exception_order_sensitive`` (606 branch), ``n_messages``
    (how many times XULE emits the message: once per statement cube carrying
    the axis), ``in_released_role``, ``dts`` ("filing" / "released") and
    ``era``.  Rule element 9574 findings only, unless ``all_alignments=True``,
    which adds 10093 findings (their total carries a target-axis member;
    ``sub_member``, ``dim2``, ``dim2_candidates``, ``dim2_ambiguous``).

    ``options`` overrides ``era`` (see :func:`options_for`).
    """
    opts = options if options is not None else options_for(query, era)
    fl = load_filing(query, filing_dir, assume_released_statements=assume_released_statements)
    want = _question_key(query, fl)
    res = _all_findings(fl, opts, want)
    if not all_alignments:
        res = [r for r in res if r["rule_element"] == "9574"]
    res.sort(key=lambda r: (0 if r["in_released_role"] else 1, r["rule_element"] != "9574"))
    return res


def fires_0117(query: str, filing_dir: Optional[Union[str, Path]] = None, options: Optional[Options] = None,
               *, era: str = "2026") -> bool:
    return bool(findings_0117(query, filing_dir, options, era=era))


# --------------------------------------------------------------------------- #
# Where 0117 can fire at all (cross-rule structure)
# --------------------------------------------------------------------------- #


def released_role_profile(query: str, filing_dir: Optional[Union[str, Path]] = None, *,
                          assume_released_statements: bool = False) -> List[dict]:
    """One dict per role of the released linkbase sections, classified with the
    filing's DTS: ``statement_cube`` (a drs-role of ``$STATEMENT_CUBES``; also
    the roles DQC_US_0126 skips, src_2026_DQC_0126.xule l.28-33),
    ``target_axes`` (0117 target axes on its statement cubes; 0117 can only
    report a finding in such a role), ``notes_cube``, ``parenthetical_cube``,
    ``has_cube`` and the roleType ``description``."""
    fl = load_filing(query, filing_dir, assume_released_statements=assume_released_statements)
    out: List[dict] = []
    for role in sorted(fl.released_roles):
        cubes = [c for c in fl.cubes if c.role == role]
        stmt = [c for c in cubes if c.is_statement]
        axes = sorted({local(d) for c in stmt for d in c.dims if local(d) in _TARGET_SET})
        out.append({
            "role": role,
            "description": fl.role_desc.get(role, cubes[0].description if cubes else ""),
            "has_cube": bool(cubes),
            "statement_cube": bool(stmt),
            "target_axes": axes,
            "notes_cube": any(c.is_notes for c in cubes),
            "parenthetical_cube": any(c.is_parenthetical for c in cubes),
        })
    return out


def released_statement_target_roles(query: str, filing_dir: Optional[Union[str, Path]] = None) -> List[str]:
    """Released roles in which DQC_US_0117 can report: statement cubes with a target axis.

    A hint, not a precondition: the rule constrains the role of the FINDING,
    and the released sections are not always scoped to it.  In 16 of the 120
    practice 0117 golds they are scoped elsewhere (10 Disclosure roles, 4
    roles without a cube, 2 statement cubes without a target axis: BEEP, CAPC
    x3, NCMI x8, OII x2, SCI, ONB) while the gold finding sits in a statement
    role of the same filing.  6 of the 16 are on us-gaap 2023+ and all 6 are
    reproduced by the 2026 logic (8 of 16 overall)."""
    return [p["role"] for p in released_role_profile(query, filing_dir) if p["statement_cube"] and p["target_axes"]]


# --------------------------------------------------------------------------- #
# Locating the complete filing for a case
# --------------------------------------------------------------------------- #

_SREF_RE = re.compile(r'schemaRef[^>]*href="[^"]*?([\w.-]+?-\d{8})(?:_htm)?\.xsd"')
_CIK_RE = re.compile(r'<(?:xbrli:)?identifier[^>]*scheme="http://www\.sec\.gov/CIK"[^>]*>\s*(\d+)\s*<')


def locate_filing_dir(query: str, roots: Sequence[Union[str, Path]]) -> Optional[Path]:
    """Find ``<root>/<cik10>-<stem>`` (ranked layout) or ``<root>/<form>-<stem>``
    (practice layout) for the query's schemaRef stem."""
    inst = query.split("##Instance document", 1)[-1]
    m = _SREF_RE.search(inst) or _SREF_RE.search(query)
    if not m:
        return None
    stem = m.group(1)
    km = _CIK_RE.search(inst)
    for root in roots:
        rp = Path(root)
        if not rp.is_dir():
            continue
        if km:
            d = rp / f"{km.group(1).zfill(10)}-{stem}"
            if d.is_dir():
                return d
        hits = sorted(p for p in rp.iterdir() if p.is_dir() and p.name.endswith("-" + stem))
        if len(hits) == 1:
            return hits[0]
    return None
