"""DQC_US_0126 "FS Calculation Check with Non Dimensional Data" -- the official XULE rule.

Source: ``task3_source_data/dqc_rules/src_2026_DQC_0126.xule`` (rule element 9590).  The
2024 and 2025 rule files are the same text: ``diff --strip-trailing-cr`` shows the 2025 and
2026 files identical and the 2024 file differing only by CRLF line endings and one blank
line after ``else`` (line 19).  So within the rule body nothing changes between the rule
sets that cover filings dated 2022-2026.  The constants and functions it calls exist
locally only as the 2026 library (``lib_2026_constant.xule``, ``lib_functions.xule``); see
``APPROXIMATIONS`` for what that leaves open.

What the rule does, step by step (``L`` = line in src_2026_DQC_0126.xule)
--------------------------------------------------------------------------
Fact index (XULE processor, not rule text).  Without ``--xule-include-dups`` the processor
      indexes ONE fact per group of consistent duplicates: same concept, period, unit,
      entity and dimensions, equal after rounding both values to the lower ``decimals``
      (a fact with INF decimals is compared unrounded); the more precise fact is kept and
      inconsistent duplicates are all kept.  Every factset below reads that index, so the
      module de-duplicates the dimension-free facts the same way (``xule_dedup``).
L17   ``applicable_form(rule-name())`` (lib_functions.xule 1031-1034) looks the rule up in
      rule-form-lookup.csv, which is not local.  Treated as always true: every Task 3 filing
      is a 10-K or 10-Q.
L21-23 The "current reporting period" is the PERIOD OF THE CONTEXT of the first
      ``DocumentPeriodEndDate`` fact (any dimensions, ``covered``), not its value.
      ``period.end - P1D`` only converts XULE's exclusive end-of-day datetime back to the
      calendar date, so: duration concepts must have exactly that (start, end); instant
      concepts must have instant == that end (L80-85).  Verified on practice: the question
      period equals the DEI context period in 101/101 DQC_US_0126 cases.
L28   ``$cubeURISet`` = drs-role URIs of ``$STATEMENT_CUBES`` (lib_2026_constant.xule
      177-195): hypercubes (has-hypercube ``all``/``notAll`` arcs, read quote-agnostically:
      EDGARsuite linkbases write loc/arc attributes in single quotes) whose role definition
      contains '- Statement -' and whose role URI (lower-cased) contains none of
      parenthetical, equity, deficit, stockholders, capital, investment, changes,
      shareholder, convertible, preferred, temporaryequity, redeemable,
      netproceedsfromallsources, membersinterest; description not 'schedule iii'/'iv'; and
      hypercube not one of the seven schedule-of-investments tables.
L30   ``$STATEMENT_PRES_NETWORKS`` (lib_2026_constant.xule 208-229): presentation networks
      whose role definition contains '- Statement -' and whose role URI (lower-cased)
      contains none of parenthetical, equity, deficit, stockholders, capital, investment,
      change, shareholder, convertible, preferred, temporaryequity, redeemable,
      netproceedsfromallsources, membersinterest, membershipinterest, highlights, employee,
      ebp; description (lower-cased) not containing 'schedule iii', 'schedule iv',
      'net worth'.  Note the URI is tested, not the title: "...BalanceSheets" passes,
      "...StatementsOfChangesInEquity" fails on 'change'/'equity'.  ``role.description`` is
      the roleType ``definition`` only: with a filing directory the module reads it from the
      filing's .xsd and nothing else (a role the .xsd does not define has no description and
      is not a statement); only without one does it fall back to the released Schema section
      and then the link's xlink:title (flagged ``role_definition_source``).
L32   THE "DEFINITION LINKBASE DEFINED FOR THE STATEMENT" TEST: the presentation role is
      skipped when its URI is in ``$cubeURISet``, i.e. when the definition linkbase has a
      has-hypercube arc (``all``/``notAll``) in the same extended-link role.  An empty
      ``definitionLink`` for the role, or dimension arcs without a has-hypercube arc, do not
      make it a cube.
L36   ``$calcNetworkSource``: every concept that is the source (parent) of a summation-item
      arc in the calculation network with the SAME role URI as the presentation network.
      ``include start`` adds the network roots as a none source, which L42 skips.
L38-39 ``$fs_decimals`` = most frequent ``decimals`` over all non-nil, dimension-free
      (closed factset ``[...]``), ``covered`` (any period/unit) facts of those PARENT
      concepts, after duplicate elimination.  ``most_frequent`` (lib_functions.xule 934-944)
      breaks ties through a dict keyed by count, i.e. by XULE set iteration order -- not
      observable; ties are reported.
L41-47 For every parent: its direct summation-item children in that role with weights.
L50-55 Each child's value, aligned with the parent fact (same period, unit, entity; no
      dimensions; non-nil): ``first-value(A, B, C)`` where A is the BARE FACTSET of facts
      with decimals == $fs_decimals (every such fact is a list item -- after duplicate
      elimination two can only coexist as inconsistent duplicates, flagged
      ``multi_value_children``), B = first fact with decimals >= $fs_decimals, C = first
      fact with decimals < $fs_decimals (document order stands in for XULE's unobservable
      list order), times the arc weight.  A child with no such fact contributes nothing (it
      is not an addend).  There is NO fallback to grandchildren and NO dimensional fallback
      (the comment at L48 is stale -- the code never reads members).
L57-58 ``$addend`` = sum of the addends; ``$addendNumber`` = their count.
L80-85 ``$sum2`` = the parent's non-nil, dimension-free fact in the current period WITH
      decimals == $fs_decimals.  A parent fact at any other decimals is never checked.
L88   No addend at all -> skip.
L91-93 Skip when a child is LiabilitiesSubjectToCompromise and the filing has any
      ReorganizationUnderChapter11OfUSBankruptcyCodeDisclosureTextBlock fact.
L95   Fires when ``tolerance_for_decimals($sum2, $addend, $addendNumber + 1)``
      (lib_functions.xule 163-194): d = min(decimals($sum2), decimals($addend)) with a
      missing $addend decimals replaced by $sum2's; fires iff
      |round($sum2, d) - round($addend, d)| > 10^-d * ($addendNumber + 1).

The finding's numbers: extracted = $sum2 (the parent fact), calculated = $addend.

DTS material.  XULE loads the whole DTS.  With a filing directory the module reads every
``*_pre.xml``/``*_cal.xml``/``*_def.xml``, every local linkbase the .xsd names in a
``linkbaseRef``, and the linkbases embedded in the .xsd itself (three practice filings --
glxz-20231231, bvfl-20240930, camp-20231130 -- have no separate linkbase files).

Fixes of 2026-10-08 (review of this module against the XULE source)
-------------------------------------------------------------------
1. has-hypercube arcs are read quote-agnostically (was ``xbrl.parse_definition``,
   double quotes only): 58 ranked and 1 practice EDGARsuite filings write loc/arc
   attributes in single quotes, so their cube roles were invisible.
2. roleType definitions with attributes (ThunderDome: ``<link:definition xmlns=...>``) are
   read; before, 16 practice and 2 dev cases fell back to link titles.
3. XULE's default duplicate-fact elimination (fact index), see above.
4. L53's bare factset: every fact at $fs_decimals is an addend (was: the first only).
5. With a filing directory, role descriptions come from the .xsd only (was: also the
   released Schema section and link titles).
6. Every DTS file is read: all linkbase files, linkbaseRef targets, and linkbases embedded
   in the .xsd (was: the first file per suffix only).

Measured (task3_source_data/dqc_rules/validate_0126.py, 2026-10-08, after the fixes)
------------------------------------------------------------------------------------
* Practice, 101 curated DQC_US_0126 cases: gold pair among the findings 101/101 and exactly
  one finding 101/101 in both modes ("released linkbases + complete instance", and the
  complete filing).  DEV_000273 (excluded for its typo gold 320002) gives (-32002, 32002).
  The original 332-case release alone gives 0/101: its statement-scoped instances hold no
  dei facts at all, so the current period (L21) cannot be found without the full instance.
* Practice, 229 DQC_US_0015/0117 cases: the rule fires on 0 in both modes.  Only DEV_000012
  reaches the tolerance test (its children add up exactly); the rest stop at structural
  gates (period not current, not a calc parent, non-statement or cube role).
* Filing level (the over-firing test): in the 64 practice filings that hold a released
  0126 case, ``all_findings_0126`` returns 102 findings and every one is a released 0126
  case (101 curated + DEV_000273): precision 102/102, recall 102/102.  Without the L32 cube
  skip it would be 102/124, so practice gold confirms that skip.
* DEV_000329 is the one practice case that separates the two readings of
  ``$addendNumber``: counting all 15 children gives tolerance 1,600,000 = |difference|, so
  it would not fire; counting the 14 children with values (this module) fires, as gold
  requires.
* Before/after the fixes, over 330 practice + 680 dev cases in both modes: 0 changed
  findings and 0 changed gates for the questioned concept/period; the rule fires on 464
  dev cases, one finding each.  At filing level the cube fix removes 2 false findings
  (StockholdersEquity on the single-quoted cube balance sheets of cnfn-20250930 and
  tpia-20250930); duplicate elimination drops 8,091 dimension-free facts in 143/144
  practice filings and 15,733 in 352/352 dev filings and changes no finding (nor does the
  other rounding variant of the duplicate test, nor switching it off).

Deviation of the older ``task3_solver`` 0126 branch that this module corrects: it expands a
child that has no fact through that child's own calculation children.  XULE never does
that -- the child is simply not an addend.  The branch never triggered on a practice 0126
case, so gold never tested it.  Against the best dev upload (94.12%) the faithful rule
disagrees on 14 cases: 10 calculated values (9 from no-expansion: DEV3_000392/395/400/406/
409/413/465/605/666; 1 from unit alignment: a share-count child under a USD parent is not
an addend, DEV3_000542), 3 rule switches (DEV3_000364 was answered as 0015,
DEV3_000446/466 as 0117; the rule fires on all three and neither sibling rule does), and
DEV3_000215, where the upload answered 0126 but XULE cannot fire: its income statement
carries a us-gaap:StatementTable cube (L32).  The upload's pair there (10647000, -3882000)
is exactly what this rule gives when the cube skip is ignored, which practice gold rules
out (see the filing-level numbers above).

API
---
``findings_0126(query, filing_dir=None)``
    Fired findings for the QUESTIONED concept and period, one dict per (statement role,
    parent fact)::

        {"rule": "DQC_US_0126", "rule_element_id": "9590", "role", "role_definition",
         "role_definition_source", "released_role", "concept", "period", "unit",
         "context_id", "parent_value", "parent_decimals", "children_sum",
         "children": [(concept, weight, value_or_None)],
         "children_detail": [(concept, weight, value, decimals, weighted)],
         "multi_value_children": [(concept, weight, [values])], "n_addends", "n_children",
         "fs_decimals", "fs_decimals_tied", "difference", "tolerance", "fires", "fires_alt",
         "alt_addends", "skip_reason", "calc11", "extracted", "calculated"}

    Values are exact plain strings (``Decimal`` text, no grouping commas); ``weight`` is
    "1"/"-1"; a child's ``value`` is its reported (unweighted) fact value, None when it has
    no aligned fact.  ``children_sum`` = sum of weight x value over every addend (including
    the extra values of ``multi_value_children``).  ``released_role`` marks the role the
    released query's calculation section is scoped to (findings are sorted released role
    first).  ``filing_dir`` may be ``"auto"``.
``all_findings_0126(query, filing_dir=None)``
    Every fired finding in the filing (all statement roles, all parents).
``explain_0126(query, filing_dir=None)``
    Why the questioned concept/period does or does not produce a finding: the gate that
    stops it (``gate``), the role statuses, and every evaluation (fired or not).
``load_material(query, filing_dir=None, *, dedup=True)`` / ``evaluate(mat, concept=None)``
    The two halves, for diagnostics (``dedup=False`` reproduces the pre-fix fact index).

``filing_dir`` (optional) is the complete filing directory: its ``.xsd`` (all roleType
definitions and any embedded linkbases), every presentation/calculation/definition linkbase
and the ``*_htm.xml`` instance are used, exactly as XULE sees the whole DTS.  Without it the
released sections of the query are used (statement-scoped: normally just the audited role).
``find_filing_dir(query)`` locates the directory for practice and ranked cases.
"""

from __future__ import annotations

import html
import os
import re
from collections import Counter, OrderedDict
from dataclasses import dataclass, field
from decimal import ROUND_HALF_EVEN, Decimal, InvalidOperation, localcontext
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

from .. import xbrl as X

__all__ = [
    "RULE_ID",
    "RULE_ELEMENT_ID",
    "APPROXIMATIONS",
    "STATEMENT_PRES_URI_EXCLUDES",
    "STATEMENT_PRES_DESC_EXCLUDES",
    "STATEMENT_CUBE_URI_EXCLUDES",
    "STATEMENT_CUBE_DESC_EXCLUDES",
    "SOI_TABLES",
    "Material",
    "load_material",
    "find_filing_dir",
    "dts_files",
    "parse_role_definitions",
    "calculation_networks",
    "hypercube_roles",
    "presentation_roles",
    "xule_dedup",
    "pres_network_status",
    "tolerance_for_decimals",
    "most_frequent",
    "evaluate",
    "question_findings",
    "explain_material",
    "findings_0126",
    "all_findings_0126",
    "explain_0126",
]

RULE_ID = "DQC_US_0126"
RULE_ELEMENT_ID = "9590"

# lib_2026_constant.xule 208-229 ($STATEMENT_PRES_NETWORKS), tested on role URI lower-case.
STATEMENT_PRES_URI_EXCLUDES: Tuple[str, ...] = (
    "parenthetical", "equity", "deficit", "stockholders", "capital", "investment", "change",
    "shareholder", "convertible", "preferred", "temporaryequity", "redeemable",
    "netproceedsfromallsources", "membersinterest", "membershipinterest", "highlights",
    "employee", "ebp",
)
# same constant, tested on role description lower-case.
STATEMENT_PRES_DESC_EXCLUDES: Tuple[str, ...] = ("schedule iii", "schedule iv", "net worth")
# lib_2026_constant.xule 177-195 ($STATEMENT_CUBES), drs-role URI lower-case.
STATEMENT_CUBE_URI_EXCLUDES: Tuple[str, ...] = (
    "parenthetical", "equity", "deficit", "stockholders", "capital", "investment", "changes",
    "shareholder", "convertible", "preferred", "temporaryequity", "redeemable",
    "netproceedsfromallsources", "membersinterest",
)
STATEMENT_CUBE_DESC_EXCLUDES: Tuple[str, ...] = ("schedule iii", "schedule iv")
SOI_TABLES = frozenset({
    "ScheduleOfInvestmentsTable", "SummaryOfInvestmentHoldingsTable",
    "InvestmentsSoldNotYetPurchasedTable", "OpenOptionContractsWrittenTable",
    "OpenFuturesContractTable", "OpenForwardForeignCurrencyContractTable", "OpenSwapContractTable",
})
STATEMENT_MARK = "- Statement -"

SUMMATION_ITEM_2003 = "http://www.xbrl.org/2003/arcrole/summation-item"
SUMMATION_ITEM_2023 = "https://xbrl.org/2023/arcrole/summation-item"
# XBRL Dimensions 1.0 has-hypercube arcroles ($STATEMENT_CUBES = taxonomy().cubes)
HAS_HYPERCUBE_ARCROLES = frozenset({
    "http://xbrl.org/int/dim/arcrole/all",
    "http://xbrl.org/int/dim/arcrole/notAll",
})

#: What the case material cannot show, and the choice made.
APPROXIMATIONS: Tuple[str, ...] = (
    "applicable_form (rule-form-lookup.csv, not local) is assumed true: all Task 3 filings are 10-K/10-Q.",
    "effectiveDate ($effective_dates CSV, not local) is not applied; it is message metadata, and practice "
    "gold includes findings on 2021 filings.",
    "Only the 2026 constant/function libraries are local. The 2024/2025 rule bodies are identical, but if "
    "the 2024/2025 $STATEMENT_PRES_NETWORKS/$STATEMENT_CUBES exclusion lists were shorter, a role this "
    "module excludes (e.g. URI containing 'highlights'/'employee'/'ebp'/'membershipinterest', description "
    "'net worth') could have been checked by an older rule set.",
    "Current period = the context period of the first DocumentPeriodEndDate fact in document order "
    "(XULE's fact order is not observable; all DEI facts in practice/dev share one period).",
    "$fs_decimals ties are broken by XULE set/dict iteration order, which is not observable; the module "
    "evaluates every tied candidate and marks the findings fs_decimals_tied=True.",
    "decimals($addend) is taken as undefined (a computed sum), so tolerance uses the parent's decimals; "
    "the alternative (min decimals of the addends) is reported as fires_alt['min_child_decimals'].",
    "$addendNumber counts children that have an aligned value (missing children are not list items); the "
    "alternative (all children) is reported as fires_alt['all_children_counted'].",
    "Iterations where $sum2 has no fact (parent missing, or at other decimals) produce no finding: XULE "
    "leaves the iteration unbound. Otherwise the rule would fire on every prior period.",
    "Both summation-item arcroles are navigated: 2003 and calc-1.1 (https://xbrl.org/2023/arcrole/"
    "summation-item, 66 dev/test filings, none in practice). Whether the generator's XULE build mapped "
    "'summation-item' to the 2023 arcrole is not directly observable; findings from calc-1.1 networks "
    "carry calc11=True. Indirect support: on all 35 dev cases that fire only through a calc-1.1 network, "
    "the sibling dqc_0015/dqc_0117 modules find nothing, so 0126 is the only rule left to have produced them.",
    "Duplicate facts are eliminated as the XULE processor does by default (no --xule-include-dups): per "
    "(concept, period, unit, entity), a fact equal to an indexed one after rounding both to the lower "
    "decimals (INF-decimals values unrounded) is dropped, the more precise of the two being kept; "
    "inconsistent duplicates are all kept. This is processor behaviour recalled from XuleProcessor."
    "index_model/get_decimalized_value, not rule text, and cannot be checked offline. load_material("
    "dedup=False) gives the raw index; on practice and dev both give identical findings.",
    "L53's first first-value argument is a bare factset, so every fact at $fs_decimals in the parent's "
    "alignment is an addend (only inconsistent duplicates can coexist after duplicate elimination); such "
    "findings list them in multi_value_children and give the first-value-only reading in "
    "alt_addends/fires_alt['first_value_only']. The order XULE uses for first(list(...)) in the >= and < "
    "branches is not observable; document order is used. Neither occurs in practice or dev.",
    "Equivalent duplicate arcs (same parent, child, weight) collapse to one; prohibited arcs remove the "
    "relationship (none occur in the local filings). Arcs that differ only in 'order' would be two XBRL "
    "relationships (the child counted twice); none occur in the local filings.",
    "Concepts are matched by prefix:localName as written (verified: every calc concept with facts matches "
    "an instance prefix exactly on dev).",
    "Period type of a parent comes from its own facts (instant vs duration contexts), falling back to the "
    "US GAAP Taxonomy section for the questioned concept.",
    "Units are compared as the instance's prefixed measure strings and entities by identifier text (one "
    "entity scheme per SEC filing); the Chapter 11 test counts any fact of the text-block concept, nil "
    "or not (whether XULE's default factset includes nils is not observable; no filing has such a fact).",
    "Role descriptions: with a filing directory, only the .xsd roleType definitions (XULE role.description);"
    " a role the .xsd does not define (e.g. a standard-taxonomy role) has no description here. Without a "
    "filing directory the released Schema section, then the link xlink:title, stand in (flagged "
    "role_definition_source='query_schema'/'link_title').",
)

# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #

_ATTR_RE = re.compile(r"([\w:.-]+)\s*=\s*(?:\"([^\"]*)\"|'([^']*)')")
_ROLETYPE_RE = re.compile(r"<(?:\w+:)?roleType\b(?P<attrs>[^>]*)>(?P<body>.*?)</(?:\w+:)?roleType>", re.S)
# ThunderDome schemas write <link:definition xmlns="http://www.xbrl.org/2003/linkbase">: allow attributes.
_DEFINITION_RE = re.compile(r"<(?:\w+:)?definition\b(?:\s[^>]*)?(?<!/)>(?P<d>.*?)</(?:\w+:)?definition\s*>", re.S)
_LOC_RE = re.compile(r"<(?:link:)?loc\b(?P<attrs>[^>]*?)/?>", re.S)
_DEF_ARC_RE = re.compile(r"<(?:link:)?definitionArc\b(?P<attrs>[^>]*?)/?>", re.S)
_LINKBASE_REF_RE = re.compile(r"<(?:\w+:)?linkbaseRef\b(?P<attrs>[^>]*?)/?>", re.S)
_SCHEMA_REF_RE = re.compile(r"schemaRef[^>]*href=(?:\"([^\"]+)\"|'([^']+)')")
_CIK_RE = re.compile(r"<(?:xbrli:)?identifier\b[^>]*>\s*0*(\d+)\s*</")
_CONTEXT_REF_RE = re.compile(r"\bcontextRef\s*=")

INF = float("inf")

# Filing directories for ``filing_dir="auto"``: <FINREASON_DATA>/filings (ranked phases,
# <cik10>-<stem>) and <FINREASON_DATA>/filings_practice (practice, *-<stem>).
_DATA = Path(os.environ.get("FINREASON_DATA", "data"))
PRACTICE_FILINGS = _DATA / "filings_practice"
RANKED_FILINGS = _DATA / "filings"


def _attrs(text: str) -> Dict[str, str]:
    """Attributes of a start tag, single- or double-quoted (XML does not distinguish them)."""
    return {m.group(1): (m.group(2) if m.group(2) is not None else m.group(3)) for m in _ATTR_RE.finditer(text)}


def _to_decimal(text: Optional[str]) -> Optional[Decimal]:
    if text is None:
        return None
    t = text.strip()
    if not t:
        return None
    try:
        d = Decimal(t)
    except InvalidOperation:
        return None
    return d if d.is_finite() else None


def _plain(d: Optional[Decimal]) -> Optional[str]:
    if d is None:
        return None
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "", "-") else s


def _decimals(raw: Optional[str]) -> Optional[float]:
    """XBRL ``decimals`` attribute -> number (``INF`` -> inf); missing -> None."""
    if raw is None:
        return None
    t = raw.strip()
    if t.upper() == "INF":
        return INF
    try:
        return float(int(t))
    except ValueError:
        return None


def _dec_text(d: Optional[float]) -> Optional[str]:
    if d is None:
        return None
    if d == INF:
        return "INF"
    return str(int(d))


def _norm_date(d: Optional[str]) -> Optional[str]:
    if d is None:
        return None
    d = d.strip()
    return d[:10] if re.match(r"^\d{4}-\d{2}-\d{2}T00:00:00", d) else d


def _period_key(ctx: X.Context) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    return (_norm_date(ctx.start), _norm_date(ctx.end), _norm_date(ctx.instant))


def _local(qname: str) -> str:
    return qname.split(":", 1)[-1]


# --------------------------------------------------------------------------- #
# Linkbase parsing (regex, quote-agnostic, tolerant of truncation like xbrl)
# --------------------------------------------------------------------------- #


def parse_role_definitions(xsd_text: str) -> Dict[str, str]:
    """``roleURI -> definition`` from ``link:roleType`` elements (schema text)."""
    out: Dict[str, str] = {}
    if not xsd_text or xsd_text.strip() in ("None", "null"):
        return out
    for m in _ROLETYPE_RE.finditer(xsd_text):
        a = _attrs(m.group("attrs"))
        uri = a.get("roleURI")
        dm = _DEFINITION_RE.search(m.group("body"))
        if uri and dm and uri not in out:
            out[uri] = html.unescape(dm.group("d")).strip()
    return out


def _link_blocks(text: str, link: str) -> Iterable[Tuple[Dict[str, str], str]]:
    """Yield ``(attrs, body)`` for every ``<link>`` extended link, including a truncated last one."""
    if not text or text.strip() in ("None", "null"):
        return
    open_re = re.compile(r"<(?:link:)?%s\b(?P<attrs>[^>]*?)(?P<selfclose>/?)>" % link, re.S)
    close_re = re.compile(r"</(?:link:)?%s\s*>" % link)
    pos = 0
    while True:
        m = open_re.search(text, pos)
        if not m:
            return
        a = _attrs(m.group("attrs"))
        if m.group("selfclose"):
            yield a, ""
            pos = m.end()
            continue
        c = close_re.search(text, m.end())
        if c:
            yield a, text[m.end():c.start()]
            pos = c.end()
        else:
            yield a, text[m.end():]
            return


def link_titles(text: str, link: str) -> Dict[str, str]:
    """``role -> xlink:title`` of the extended links (filers often copy the role definition there)."""
    out: Dict[str, str] = {}
    for a, _body in _link_blocks(text, link):
        role, title = a.get("xlink:role"), a.get("xlink:title")
        if role and title and role not in out:
            out[role] = html.unescape(title).strip()
    return out


def _locators(body: str) -> Dict[str, str]:
    locs: Dict[str, str] = {}
    for lm in _LOC_RE.finditer(body):
        a = _attrs(lm.group("attrs"))
        if "xlink:label" in a and "xlink:href" in a:
            locs[a["xlink:label"]] = X.href_to_concept(a["xlink:href"])
    return locs


def presentation_roles(text: str) -> Dict[str, int]:
    """``role -> number of parent-child arcs`` (a network exists only when it has arcs)."""
    arc_re = re.compile(r"<(?:link:)?presentationArc\b(?P<attrs>[^>]*?)/?>", re.S)
    out: Dict[str, int] = {}
    for a, body in _link_blocks(text, "presentationLink"):
        role = a.get("xlink:role", "")
        n = 0
        for am in arc_re.finditer(body):
            arcrole = _attrs(am.group("attrs")).get("xlink:arcrole", "")
            if arcrole.endswith("/parent-child"):
                n += 1
        out[role] = out.get(role, 0) + n
    return out


@dataclass
class CalcNetwork:
    role: str
    #: parent -> [(child, weight)], in arc document order, equivalent duplicates collapsed.
    children: "OrderedDict[str, List[Tuple[str, Decimal]]]" = field(default_factory=OrderedDict)
    arcroles: Set[str] = field(default_factory=set)

    @property
    def parents(self) -> List[str]:
        return list(self.children.keys())

    @property
    def calc11(self) -> bool:
        return SUMMATION_ITEM_2023 in self.arcroles


def calculation_networks(text: str) -> Dict[str, CalcNetwork]:
    """``role -> CalcNetwork`` from a calculation linkbase (released section or raw ``_cal.xml``).

    Links with the same role are merged (one network per role, as in a DTS); ``text`` may be
    several complete linkbase documents joined together.  Both the 2003 and the calc-1.1
    summation-item arcroles are accepted.  An arc with ``use="prohibited"`` removes the
    relationship it names.
    """
    arc_re = re.compile(r"<(?:link:)?calculationArc\b(?P<attrs>[^>]*?)/?>", re.S)
    nets: Dict[str, CalcNetwork] = {}
    prohibited: Dict[str, Set[Tuple[str, str]]] = {}
    for a, body in _link_blocks(text, "calculationLink"):
        role = a.get("xlink:role", "")
        locs = _locators(body)
        net = nets.setdefault(role, CalcNetwork(role))
        for am in arc_re.finditer(body):
            aa = _attrs(am.group("attrs"))
            arcrole = aa.get("xlink:arcrole", "")
            if not arcrole.endswith("summation-item"):
                continue
            parent, child = locs.get(aa.get("xlink:from", "")), locs.get(aa.get("xlink:to", ""))
            if parent is None or child is None:
                continue
            if aa.get("use") == "prohibited":
                prohibited.setdefault(role, set()).add((parent, child))
                continue
            try:
                weight = Decimal(aa.get("weight", "1").strip())
            except InvalidOperation:
                continue
            net.arcroles.add(arcrole)
            lst = net.children.setdefault(parent, [])
            if (child, weight) not in lst:
                lst.append((child, weight))
    for role, pairs in prohibited.items():
        net = nets.get(role)
        if not net:
            continue
        for parent, child in pairs:
            if parent in net.children:
                net.children[parent] = [(c, w) for c, w in net.children[parent] if c != child]
                if not net.children[parent]:
                    del net.children[parent]
    return {r: n for r, n in nets.items() if n.children}


def hypercube_roles(text: str) -> Dict[str, Set[str]]:
    """``role -> {hypercube concept}`` for every has-hypercube (``all``/``notAll``) arc.

    Parsed with this module's quote-agnostic ``_link_blocks``/``_attrs``/``_LOC_RE``: XML
    allows single-quoted attributes and EDGARsuite linkbases use them on every loc and arc.
    (``xbrl.parse_definition`` reads only double-quoted attributes and so misses every
    has-hypercube arc of such a filing; it is not used here.)  A prohibited has-hypercube
    arc removes the relationship it names in its role.
    """
    out: Dict[str, Set[str]] = {}
    prohibited: Dict[str, Set[str]] = {}
    for a, body in _link_blocks(text, "definitionLink"):
        role = a.get("xlink:role", "")
        locs = _locators(body)
        for am in _DEF_ARC_RE.finditer(body):
            aa = _attrs(am.group("attrs"))
            if aa.get("xlink:arcrole", "").strip() not in HAS_HYPERCUBE_ARCROLES:
                continue
            to = locs.get(aa.get("xlink:to", ""))
            if not to:
                continue
            if aa.get("use") == "prohibited":
                prohibited.setdefault(role, set()).add(to)
                continue
            out.setdefault(role, set()).add(to)
    for role, hcs in prohibited.items():
        if role in out:
            out[role] -= hcs
            if not out[role]:
                del out[role]
    return out


# --------------------------------------------------------------------------- #
# Filing material
# --------------------------------------------------------------------------- #


@dataclass
class FactRec:
    concept: str
    value: Decimal
    decimals: Optional[float]
    period: Tuple[Optional[str], Optional[str], Optional[str]]
    unit: Optional[str]
    entity: Optional[str]
    context_id: str
    fact_id: Optional[str]
    pos: int

    @property
    def alignment(self) -> Tuple:
        return (self.period, self.unit, self.entity)


@dataclass
class Material:
    """Everything the rule reads, with where each part came from."""

    role_defs: Dict[str, str]
    role_def_source: Dict[str, str]
    pres_roles: Dict[str, int]
    calc: Dict[str, CalcNetwork]
    cubes: Dict[str, Set[str]]
    #: concept -> dimension-free, non-nil, numeric facts in document order (XULE-deduplicated)
    nondim: Dict[str, List[FactRec]]
    #: concepts with at least one fact of any kind (used by the Chapter 11 test)
    concepts_present: Set[str]
    dei_period: Optional[Tuple[Optional[str], Optional[str]]]
    dei_periods_all: List[Tuple]
    released_role: Optional[str]
    sources: Dict[str, str]
    question: Optional[X.Question] = None
    question_period_type: Optional[str] = None
    #: dimension-free facts dropped as consistent duplicates (XULE default fact index)
    duplicates_removed: int = 0
    #: "filing_xsd" (roleType definitions of the filing's .xsd only) or "query_fallback"
    role_def_mode: str = "query_fallback"
    #: instance sanity counts: contextRef attributes vs parsed facts, facts without a context
    instance_check: Dict[str, int] = field(default_factory=dict)
    #: the files read from the filing directory
    dts_paths: Dict[str, List[str]] = field(default_factory=dict)


def _read(path: Optional[Path]) -> str:
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _filing_file(filing_dir: Optional[Path], suffix: str) -> Optional[Path]:
    """The first file with ``suffix`` (kept for callers that want one file; see :func:`dts_files`)."""
    if not filing_dir:
        return None
    d = Path(filing_dir)
    if not d.is_dir():
        return None
    if suffix == ".xsd":
        c = sorted(d.glob("*.xsd"))
    elif suffix == "_htm.xml":
        c = sorted(d.glob("*_htm.xml")) or [
            p for p in sorted(d.glob("*.xml")) if not re.search(r"_(cal|def|lab|pre|ref)\.xml$", p.name)
        ]
    else:
        c = sorted(d.glob(f"*{suffix}"))
    return c[0] if c else None


def dts_files(filing_dir) -> Dict[str, List[Path]]:
    """Every local file of the filing's DTS that can hold the links the rule reads.

    ``xsd``: all ``*.xsd`` (roleType definitions; linkbases may be embedded in them).
    ``linkbases``: every ``*_pre.xml``/``*_cal.xml``/``*_def.xml`` plus any other local file a
    ``.xsd`` names in a presentation/calculation/definition (or role-less) ``linkbaseRef``.
    """
    out: Dict[str, List[Path]] = {"xsd": [], "linkbases": []}
    if not filing_dir:
        return out
    d = Path(filing_dir)
    if not d.is_dir():
        return out
    out["xsd"] = sorted(d.glob("*.xsd"))
    lbs: List[Path] = []
    for suf in ("_pre.xml", "_cal.xml", "_def.xml"):
        lbs.extend(sorted(d.glob(f"*{suf}")))
    wanted_roles = ("presentationLinkbaseRef", "calculationLinkbaseRef", "definitionLinkbaseRef")
    for x in out["xsd"]:
        for m in _LINKBASE_REF_RE.finditer(_read(x)):
            a = _attrs(m.group("attrs"))
            href, role = a.get("xlink:href", ""), a.get("xlink:role", "")
            if not href or re.match(r"^[a-zA-Z][a-zA-Z0-9+.-]*://", href):
                continue
            if role and not role.endswith(wanted_roles):
                continue
            p = (x.parent / href.split("#", 1)[0])
            try:
                p = p.resolve()
                if p.is_file() and p.parent == d.resolve() and p not in [q.resolve() for q in lbs]:
                    lbs.append(p)
            except OSError:
                continue
    out["linkbases"] = lbs
    return out


def find_filing_dir(query: str) -> Optional[Path]:
    """The complete filing behind a query: practice ``<form>-<stem>`` or ranked ``<cik10>-<stem>``."""
    m = _SCHEMA_REF_RE.search(query)
    if not m:
        return None
    stem = Path(m.group(1) or m.group(2)).name
    stem = stem[:-4] if stem.endswith(".xsd") else stem
    cm = _CIK_RE.search(query[query.find("##Instance document"):] if "##Instance document" in query else query)
    if cm and RANKED_FILINGS.is_dir():
        cand = RANKED_FILINGS / f"{int(cm.group(1)):010d}-{stem}"
        if cand.is_dir():
            return cand
    if PRACTICE_FILINGS.is_dir():
        for d in sorted(PRACTICE_FILINGS.glob(f"*-{stem}")):
            if d.is_dir() and "-".join(d.name.split("-")[1:]) == stem:
                return d
    if RANKED_FILINGS.is_dir():
        hits = sorted(RANKED_FILINGS.glob(f"*-{stem}"))
        if len(hits) == 1:
            return hits[0]
    return None


def _index_instance(doc: X.InstanceDoc) -> Tuple[Dict[str, List[FactRec]], Set[str]]:
    nondim: Dict[str, List[FactRec]] = {}
    present: Set[str] = set()
    facts = list(doc.facts)
    for f in facts:
        present.add(f.concept)
        if f.nil or f.value is None or f.truncated:
            continue
        ctx = doc.contexts.get(f.context_ref)
        if ctx is None or ctx.dims or not ctx.complete:
            continue
        v = _to_decimal(f.value)
        if v is None:
            continue
        unit = doc.units.get(f.unit_ref or "", f.unit_ref)
        nondim.setdefault(f.concept, []).append(
            FactRec(f.concept, v, _decimals(f.decimals), _period_key(ctx), unit, ctx.entity,
                    ctx.id, f.id, f.pos)
        )
    return nondim, present


def _round(v: Decimal, places: float) -> Decimal:
    """XULE ``round(value, places)``: Python rounding (half-even); ``inf`` places = exact."""
    if places == INF:
        return v
    with localcontext() as ctx:
        ctx.prec = 200
        return v.quantize(Decimal(1).scaleb(-int(places)), rounding=ROUND_HALF_EVEN)


def _dedup_decimals(f: FactRec) -> float:
    return INF if f.decimals is None else f.decimals


def _decimalized_equal(saved: FactRec, cur: FactRec) -> bool:
    """XuleProcessor.get_decimalized_value: round both values to the lower decimals (a value
    with INF decimals is used as is) and compare."""
    sd, cd = _dedup_decimals(saved), _dedup_decimals(cur)
    md = min(sd, cd)
    sv = saved.value if sd == INF else _round(saved.value, md)
    cv = cur.value if cd == INF else _round(cur.value, md)
    return sv == cv


def xule_dedup(nondim: Dict[str, List[FactRec]]) -> Tuple[Dict[str, List[FactRec]], int]:
    """The XULE processor's default duplicate-fact elimination (XuleProcessor.index_model).

    Facts are visited in document order and grouped by aspects (concept, period, unit,
    entity; all facts here are dimension-free).  A fact that equals an already indexed fact
    of its group after rounding both to the lower decimals is a consistent duplicate: it is
    not indexed, but replaces that fact when it is more precise.  A fact that equals none is
    an inconsistent duplicate and is indexed too.  Returns ``(index, number dropped)``.
    """
    out: Dict[str, List[FactRec]] = {}
    dropped = 0
    for concept, facts in nondim.items():
        groups: Dict[Tuple, List[FactRec]] = {}
        for f in facts:
            saved = groups.setdefault(f.alignment, [])
            found = False
            for i, s in enumerate(saved):
                if _decimalized_equal(s, f):
                    found = True
                    if _dedup_decimals(f) > _dedup_decimals(s):
                        saved[i] = f
            if not found:
                saved.append(f)
        kept: Dict[int, FactRec] = {}
        for lst in groups.values():
            for f in lst:
                kept.setdefault(id(f), f)
        out[concept] = sorted(kept.values(), key=lambda f: f.pos)
        dropped += len(facts) - len(out[concept])
    return out, dropped


def _dei_period(doc: X.InstanceDoc) -> Tuple[Optional[Tuple[Optional[str], Optional[str]]], List[Tuple]]:
    """Context period of the first DocumentPeriodEndDate fact (document order)."""
    found = []
    for f in doc.facts:
        if _local(f.concept) != "DocumentPeriodEndDate":
            continue
        ctx = doc.contexts.get(f.context_ref)
        if ctx is None:
            continue
        s, e, i = _period_key(ctx)
        found.append((s, e if e is not None else i))
    if not found:
        return None, []
    distinct = list(OrderedDict.fromkeys(found))
    return found[0], distinct


def load_material(query: str, filing_dir=None, *, dedup: bool = True) -> Material:
    """Collect the DTS pieces the rule reads, from the query and (if given) the complete filing.

    ``filing_dir``: a directory, ``None`` (released sections only) or ``"auto"``
    (:func:`find_filing_dir`).  ``dedup=False`` skips XULE's duplicate-fact elimination
    (diagnostics only).
    """
    sec = X.split_sections(query) if "##Instance document" in query else {k: "" for k in X.SECTION_KEYS}
    if filing_dir == "auto":
        filing_dir = find_filing_dir(query)
    fdir = Path(filing_dir) if filing_dir else None
    sources: Dict[str, str] = {}

    # Instance: the complete filing's instance when a filing directory is given (XULE ran on
    # the whole filing; a released section can be truncated or a statement-scoped subset
    # without the DEI facts, e.g. DEV_000273), else the query's section.
    raw = _read(_filing_file(fdir, "_htm.xml"))
    if raw:
        inst_text, sources["instance"] = raw, "raw_filing"
    else:
        inst_text = sec.get("instance", "")
        complete = re.search(r"</(?:xbrli:)?xbrl>\s*$", (inst_text or "").strip())
        sources["instance"] = "query" if complete else "query(truncated)"
    doc = X.parse_instance(inst_text)
    nondim_raw, present = _index_instance(doc)
    if dedup:
        nondim, n_dropped = xule_dedup(nondim_raw)
    else:
        nondim, n_dropped = nondim_raw, 0
    dei, dei_all = _dei_period(doc)
    # xbrl.parse_instance reads double-quoted attributes only: make silent fact loss visible.
    instance_check = {
        "contextRef_attributes": len(_CONTEXT_REF_RE.findall(inst_text or "")),
        "facts_parsed": len(doc.facts) + (1 if doc.dangling_fact is not None else 0),
        "facts_without_context": sum(1 for f in doc.facts if f.context_ref not in doc.contexts),
    }

    files = dts_files(fdir)
    xsd_texts = [_read(p) for p in files["xsd"]]
    raw_xsd = "\n".join(t for t in xsd_texts if t)
    # Complete XML documents joined: every link block closes inside its own file.
    raw_links = "\n".join(t for t in ([_read(p) for p in files["linkbases"]] + xsd_texts) if t)

    # Role definitions.  XULE's role.description is the roleType definition, nothing else.
    role_defs: Dict[str, str] = {}
    role_src: Dict[str, str] = {}
    xsd_defs = parse_role_definitions(raw_xsd)
    if xsd_defs:
        role_def_mode = "filing_xsd"
        for r, d in xsd_defs.items():
            role_defs[r], role_src[r] = d, "raw_xsd"
    else:
        role_def_mode = "query_fallback"
        for r, d in parse_role_definitions(sec.get("schema", "")).items():
            if r not in role_defs:
                role_defs[r], role_src[r] = d, "query_schema"
        for text, link in (
            (sec.get("presentation", ""), "presentationLink"), (sec.get("calculation", ""), "calculationLink"),
            (sec.get("definition", ""), "definitionLink"),
        ):
            for r, t in link_titles(text, link).items():
                if r not in role_defs:
                    role_defs[r], role_src[r] = t, "link_title"

    # Presentation networks: union of complete and released.
    pres: Dict[str, int] = {}
    for text in (raw_links, sec.get("presentation", "")):
        for r, n in presentation_roles(text).items():
            pres[r] = max(pres.get(r, 0), n)
    sources["presentation"] = "raw_filing+query" if raw_links else "query"

    # Calculation: complete DTS when present (what XULE saw); released section otherwise.
    rel_calc = calculation_networks(sec.get("calculation", ""))
    calc = calculation_networks(raw_links) if raw_links else {}
    raw_has_calc = bool(calc)
    for r, net in rel_calc.items():
        if r not in calc:
            calc[r] = net
    sources["calculation"] = "raw_filing" if raw_has_calc else "query"

    # Definition (cubes): complete DTS when present, plus the released section.
    cubes = hypercube_roles(raw_links) if raw_links else {}
    for r, h in hypercube_roles(sec.get("definition", "")).items():
        cubes.setdefault(r, set()).update(h)
    sources["definition"] = "raw_filing+query" if raw_links else "query"

    released_roles = list(rel_calc.keys()) or list(presentation_roles(sec.get("presentation", "")).keys())
    released_role = released_roles[0] if len(released_roles) == 1 else None

    mat = Material(role_defs, role_src, pres, calc, cubes, nondim, present, dei, dei_all,
                   released_role, sources, duplicates_removed=n_dropped, role_def_mode=role_def_mode,
                   instance_check=instance_check,
                   dts_paths={k: [p.name for p in v] for k, v in files.items()})
    try:
        mat.question = X.parse_question(query)
    except ValueError:
        mat.question = None
    if mat.question is not None:
        tax = X.parse_taxonomy(sec.get("taxonomy", "")) if sec.get("taxonomy") else None
        mat.question_period_type = (tax.period_type if tax and tax.concept == mat.question.concept else None)
    return mat


# --------------------------------------------------------------------------- #
# Rule pieces
# --------------------------------------------------------------------------- #


def pres_network_status(role: str, definition: Optional[str]) -> str:
    """``"ok"`` when the role is in $STATEMENT_PRES_NETWORKS, else the reason it is not."""
    if definition is None:
        return "no_role_definition"
    if STATEMENT_MARK not in definition:
        return "not_statement"
    u = role.lower()
    for tok in STATEMENT_PRES_URI_EXCLUDES:
        if tok in u:
            return f"uri_excludes:{tok}"
    d = definition.lower()
    for tok in STATEMENT_PRES_DESC_EXCLUDES:
        if tok in d:
            return f"desc_excludes:{tok}"
    return "ok"


def statement_cube_uris(mat: Material) -> Set[str]:
    """``$cubeURISet``: drs-role URIs of $STATEMENT_CUBES."""
    out: Set[str] = set()
    for role, hcs in mat.cubes.items():
        definition = mat.role_defs.get(role)
        if definition is None or STATEMENT_MARK not in definition:
            continue
        u = role.lower()
        if any(tok in u for tok in STATEMENT_CUBE_URI_EXCLUDES):
            continue
        if any(tok in definition.lower() for tok in STATEMENT_CUBE_DESC_EXCLUDES):
            continue
        # a cube is excluded only when ITS hypercube is a schedule-of-investments table
        if all(h.startswith("us-gaap:") and _local(h) in SOI_TABLES for h in hcs):
            continue
        out.add(role)
    return out


def most_frequent(items: Sequence) -> Tuple[List, Counter]:
    """All items sharing the highest count (more than one = a tie XULE breaks unobservably)."""
    cnt = Counter(items)
    if not cnt:
        return [], cnt
    top = max(cnt.values())
    return [k for k, v in cnt.items() if v == top], cnt


def tolerance_for_decimals(left: Optional[Decimal], left_dec: Optional[float],
                           right: Optional[Decimal], right_dec: Optional[float],
                           factor: int) -> Tuple[bool, Optional[Decimal], float]:
    """lib_functions.xule 163-194.  Returns ``(outside_tolerance, tolerance, decimals_used)``."""
    left_decimal = INF if left_dec is None else left_dec
    right_decimal = left_decimal if right_dec is None else right_dec
    tol1 = left_decimal if left_decimal < right_decimal else right_decimal
    tol2 = Decimal(0) if tol1 == INF else (Decimal(10) ** int(-tol1)) * factor
    lv = Decimal(0) if left is None else left
    rv = Decimal(0) if right is None else right
    return abs(_round(lv, tol1) - _round(rv, tol1)) > tol2, tol2, tol1


def _period_type(mat: Material, concept: str) -> Optional[str]:
    facts = mat.nondim.get(concept, [])
    if facts:
        return "instant" if facts[0].period[2] is not None else "duration"
    if mat.question is not None and concept == mat.question.concept:
        return mat.question_period_type
    return None


def _in_current_period(rec: FactRec, ptype: Optional[str], dei) -> bool:
    if dei is None:
        return False
    ds, de = dei
    s, e, i = rec.period
    if ptype == "instant" or (ptype is None and i is not None):
        return i is not None and i == de
    return i is None and s == ds and e == de


def _child_facts(cands: List[FactRec], fsd) -> List[FactRec]:
    """L53 for one child, ``cands`` = its facts in the parent's alignment::

        first-value([nonils @concept = child where $fact.decimals == $fs_decimals] * weight,
                    first(list([... where $fact.decimals >= $fs_decimals])) * weight,
                    first(list([... where $fact.decimals <  $fs_decimals])) * weight)

    The first argument is a bare factset: every fact it holds is a list item (``none ==
    none`` is true in XULE).  The other two give one fact each.
    """
    eq: List[FactRec] = []
    for f in cands:
        if f.decimals == fsd and all(f.value != g.value for g in eq):
            eq.append(f)
    if eq:
        return eq
    if fsd is None:
        return []
    for f in cands:
        if f.decimals is not None and f.decimals >= fsd:
            return [f]
    for f in cands:
        if f.decimals is not None and f.decimals < fsd:
            return [f]
    return []


def _pick_child(cands: List[FactRec], fsd) -> Optional[FactRec]:
    """The first fact :func:`_child_facts` selects (kept for older callers)."""
    fs = _child_facts(cands, fsd)
    return fs[0] if fs else None


@dataclass
class Evaluation:
    role: str
    parent: str
    fs_decimals: Optional[float]
    fs_decimals_tied: bool
    parent_fact: Optional[FactRec]
    #: one entry per calculation child: (child, weight, first selected fact or None)
    children: List[Tuple[str, Decimal, Optional[FactRec]]]
    addend: Optional[Decimal]
    n_addends: int
    fires: bool
    tolerance: Optional[Decimal]
    decimals_used: Optional[float]
    skip_reason: Optional[str]
    fires_alt: Dict[str, bool]
    calc11: bool
    #: further facts of the bare factset (inconsistent duplicates at $fs_decimals): (child, weight, fact)
    extra_addends: List[Tuple[str, Decimal, FactRec]] = field(default_factory=list)
    #: the addend under readings other than the implemented one (only when they differ)
    alt_addends: Dict[str, Decimal] = field(default_factory=dict)

    def to_finding(self, mat: Material) -> dict:
        pf = self.parent_fact
        diff = (pf.value - self.addend) if (pf is not None and self.addend is not None) else None
        s, e, i = pf.period if pf is not None else (None, None, None)
        multi: Dict[Tuple[str, Decimal], List[FactRec]] = OrderedDict()
        for c, w, f in self.extra_addends:
            first = next((ff for cc, ww, ff in self.children if cc == c and ww == w), None)
            multi.setdefault((c, w), [first] if first is not None else []).append(f)
        return {
            "rule": RULE_ID,
            "rule_element_id": RULE_ELEMENT_ID,
            "role": self.role,
            "role_definition": mat.role_defs.get(self.role),
            "role_definition_source": mat.role_def_source.get(self.role),
            "released_role": self.role == mat.released_role,
            "concept": self.parent,
            "period": {"start": s, "end": e, "instant": i},
            "unit": pf.unit if pf is not None else None,
            "context_id": pf.context_id if pf is not None else None,
            "parent_value": _plain(pf.value) if pf is not None else None,
            "parent_decimals": _dec_text(pf.decimals) if pf is not None else None,
            "children_sum": _plain(self.addend),
            # (child concept, arc weight, child's reported value or None when it has no aligned fact)
            "children": [(c, _plain(w), _plain(f.value) if f is not None else None) for c, w, f in self.children],
            # same plus the chosen fact's decimals and its weighted contribution
            "children_detail": [(c, _plain(w), _plain(f.value) if f is not None else None,
                                 _dec_text(f.decimals) if f is not None else None,
                                 _plain(w * f.value) if f is not None else None) for c, w, f in self.children],
            # children with several facts at $fs_decimals in the alignment (all are addends)
            "multi_value_children": [(c, _plain(w), [_plain(f.value) for f in fs]) for (c, w), fs in multi.items()],
            "n_addends": self.n_addends,
            "n_children": len(self.children),
            "fs_decimals": _dec_text(self.fs_decimals),
            "fs_decimals_tied": self.fs_decimals_tied,
            "difference": _plain(diff),
            "tolerance": _plain(self.tolerance),
            "fires": self.fires,
            "fires_alt": dict(self.fires_alt),
            "alt_addends": {k: _plain(v) for k, v in self.alt_addends.items()},
            "skip_reason": self.skip_reason,
            "calc11": self.calc11,
            "extracted": _plain(pf.value) if pf is not None else None,
            "calculated": _plain(self.addend),
        }


def _evaluate_parent(mat: Material, net: CalcNetwork, parent: str, fsd, tied: bool,
                     chapter11: bool) -> List[Evaluation]:
    """All current-period evaluations of one parent in one checked role (fired or not)."""
    out: List[Evaluation] = []
    children = net.children.get(parent, [])
    ptype = _period_type(mat, parent)
    pfacts = [f for f in mat.nondim.get(parent, []) if _in_current_period(f, ptype, mat.dei_period)]
    if not pfacts:
        out.append(Evaluation(net.role, parent, fsd, tied, None, [], None, 0, False, None, None,
                              "no_parent_fact_in_current_period", {}, net.calc11))
        return out
    # $sum2: [... where $fact.decimals == $fs_decimals]  (none == none is true in XULE)
    matching = [f for f in pfacts if f.decimals == fsd]
    if not matching:
        out.append(Evaluation(net.role, parent, fsd, tied, pfacts[0], [], None, 0, False, None, None,
                              "parent_decimals_differ_from_fs_decimals", {}, net.calc11))
        return out
    seen_align = set()
    for pf in matching:
        key = (pf.alignment, pf.value)
        if key in seen_align:
            continue
        seen_align.add(key)
        comps: List[Tuple[str, Decimal, Optional[FactRec]]] = []
        extra: List[Tuple[str, Decimal, FactRec]] = []
        for child, w in children:
            cands = [f for f in mat.nondim.get(child, []) if f.alignment == pf.alignment]
            fs = _child_facts(cands, fsd)
            comps.append((child, w, fs[0] if fs else None))
            extra.extend((child, w, f) for f in fs[1:])
        used = [(c, w, f) for c, w, f in comps if f is not None] + extra
        if not used:
            out.append(Evaluation(net.role, parent, fsd, tied, pf, comps, None, 0, False, None, None,
                                  "no_child_value", {}, net.calc11, extra))
            continue
        addend = sum((w * f.value for _c, w, f in used), Decimal(0))
        n = len(used)
        if chapter11 and any(c.startswith("us-gaap:") and _local(c) == "LiabilitiesSubjectToCompromise"
                             for c, _w, _f in comps):
            out.append(Evaluation(net.role, parent, fsd, tied, pf, comps, addend, n, False, None, None,
                                  "liabilities_subject_to_compromise_chapter11", {}, net.calc11, extra))
            continue
        fires, tol, dused = tolerance_for_decimals(pf.value, pf.decimals, addend, None, n + 1)
        min_child = min((f.decimals for _c, _w, f in used if f.decimals is not None), default=None)
        alt = {
            "min_child_decimals": tolerance_for_decimals(pf.value, pf.decimals, addend, min_child, n + 1)[0],
            "all_children_counted": tolerance_for_decimals(pf.value, pf.decimals, addend, None,
                                                           len(children) + len(extra) + 1)[0],
        }
        alt_addends: Dict[str, Decimal] = {}
        if extra:
            first_only = sum((w * f.value for _c, w, f in comps if f is not None), Decimal(0))
            n_first = sum(1 for _c, _w, f in comps if f is not None)
            alt_addends["first_value_only"] = first_only
            alt["first_value_only"] = tolerance_for_decimals(pf.value, pf.decimals, first_only, None,
                                                             n_first + 1)[0]
        out.append(Evaluation(net.role, parent, fsd, tied, pf, comps, addend, n, fires, tol, dused,
                              None if fires else "within_tolerance", alt, net.calc11, extra, alt_addends))
    return out


def evaluate(mat: Material, *, concept: Optional[str] = None) -> Tuple[List[Evaluation], List[dict]]:
    """Run the rule over every checked statement role.

    Returns ``(evaluations, role_statuses)``.  With ``concept`` only that parent is evaluated
    (fs_decimals still uses every parent of the role, as the rule does).
    """
    cube_uris = statement_cube_uris(mat)
    chapter11 = any(c.startswith("us-gaap:") and
                    _local(c) == "ReorganizationUnderChapter11OfUSBankruptcyCodeDisclosureTextBlock"
                    for c in mat.concepts_present)
    evals: List[Evaluation] = []
    statuses: List[dict] = []
    roles = sorted(set(mat.pres_roles) | set(mat.calc))
    for role in roles:
        definition = mat.role_defs.get(role)
        st = {"role": role, "definition": definition, "definition_source": mat.role_def_source.get(role),
              "released": role == mat.released_role, "has_pres_network": mat.pres_roles.get(role, 0) > 0,
              "has_calc_network": role in mat.calc, "cube": role in cube_uris,
              "hypercubes": sorted(mat.cubes.get(role, ()))}
        status = pres_network_status(role, definition)
        if status == "ok" and not st["has_pres_network"]:
            status = "no_presentation_network"
        if status == "ok" and role in cube_uris:
            status = "cube"
        if status == "ok" and role not in mat.calc:
            status = "no_calc_network"
        st["status"] = status
        net = mat.calc.get(role)
        if net is not None:
            st["parents"] = len(net.children)
            st["concept_is_parent"] = concept in net.children if concept else None
        statuses.append(st)
        if status != "ok":
            continue
        parents = net.parents
        decs = [f.decimals for p in parents for f in mat.nondim.get(p, [])]
        cands, cnt = most_frequent(decs)
        st["fs_decimals_counts"] = {(_dec_text(k) if k is not None else "none"): v for k, v in cnt.items()}
        tied = len(cands) > 1
        for fsd in cands or [None]:
            for parent in parents:
                if concept is not None and parent != concept:
                    continue
                evals.extend(_evaluate_parent(mat, net, parent, fsd, tied, chapter11))
    return evals, statuses


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #


def _question_matches(ev: Evaluation, q: X.Question) -> bool:
    pf = ev.parent_fact
    if pf is None or ev.parent != q.concept:
        return False
    s, e, i = pf.period
    if q.period_type == "instant":
        return i is not None and i == _norm_date(q.instant)
    return i is None and s == _norm_date(q.start) and e == _norm_date(q.end)


def _dedupe(found: List[dict]) -> List[dict]:
    out, seen = [], set()
    for f in found:
        key = (f["role"], f["concept"], f["context_id"], f["parent_value"], f["children_sum"], f["fs_decimals"])
        if key in seen:
            continue
        seen.add(key)
        out.append(f)
    # released role first, then role URI
    return sorted(out, key=lambda f: (not f["released_role"], f["role"]))


def question_findings(mat: Material) -> List[dict]:
    """Fired findings of an already loaded :class:`Material` for its questioned concept/period."""
    q = mat.question
    if q is None:
        return []
    evals, _ = evaluate(mat, concept=q.concept)
    return _dedupe([ev.to_finding(mat) for ev in evals if ev.fires and _question_matches(ev, q)])


def findings_0126(query: str, filing_dir=None) -> List[dict]:
    """Fired DQC_US_0126 findings for the questioned concept and period (see module doc)."""
    return question_findings(load_material(query, filing_dir))


def all_findings_0126(query: str, filing_dir=None, *, mat: Optional[Material] = None) -> List[dict]:
    """Every fired finding in the filing (all checked statement roles, all parents)."""
    mat = mat if mat is not None else load_material(query, filing_dir)
    evals, _ = evaluate(mat)
    return _dedupe([ev.to_finding(mat) for ev in evals if ev.fires])


def explain_material(mat: Material) -> dict:
    """:func:`explain_0126` for an already loaded :class:`Material`."""
    q = mat.question
    out: dict = {"sources": mat.sources, "dei_period": mat.dei_period,
                 "dei_periods_distinct": mat.dei_periods_all, "released_role": mat.released_role,
                 "duplicates_removed": mat.duplicates_removed, "role_def_mode": mat.role_def_mode,
                 "instance_check": mat.instance_check, "dts_paths": mat.dts_paths}
    if q is None:
        out["gate"] = "no_question"
        return out
    out["question"] = {"concept": q.concept, "period": q.period_key}
    evals, statuses = evaluate(mat, concept=q.concept)
    out["roles"] = statuses
    out["parent_roles"] = [s for s in statuses if s.get("concept_is_parent")]
    if mat.dei_period is None:
        out["gate"] = "no_dei_period"
    else:
        ds, de = mat.dei_period
        if q.period_type == "instant":
            current = _norm_date(q.instant) == de
        else:
            current = (_norm_date(q.start), _norm_date(q.end)) == (ds, de)
        out["question_is_current_period"] = current
        if not current:
            out["gate"] = "period_not_current"
    ev_q = [ev for ev in evals if ev.parent == q.concept]
    out["evaluations"] = [ev.to_finding(mat) for ev in ev_q]
    if "gate" not in out:
        if not ev_q:
            out["gate"] = "not_parent_in_checked_role"
        elif any(ev.fires and _question_matches(ev, q) for ev in ev_q):
            out["gate"] = "fires"
        else:
            order = ["within_tolerance", "liabilities_subject_to_compromise_chapter11", "no_child_value",
                     "parent_decimals_differ_from_fs_decimals", "no_parent_fact_in_current_period"]
            reasons = {ev.skip_reason for ev in ev_q}
            out["gate"] = next((r for r in order if r in reasons), "no_finding")
    out["findings"] = _dedupe([ev.to_finding(mat) for ev in ev_q if ev.fires and _question_matches(ev, q)])
    return out


def explain_0126(query: str, filing_dir=None) -> dict:
    """Why the questioned concept/period does or does not yield a finding.

    ``gate`` is the first condition that stops it, in rule order:
    ``no_question`` / ``no_dei_period`` / ``period_not_current`` /
    ``not_parent_in_checked_role`` (with ``parent_roles`` showing the statuses of roles
    where it IS a parent) / ``no_parent_fact_in_current_period`` /
    ``parent_decimals_differ_from_fs_decimals`` / ``no_child_value`` /
    ``liabilities_subject_to_compromise_chapter11`` / ``within_tolerance`` / ``fires``.
    ``findings`` equals :func:`findings_0126` for the same input.
    """
    return explain_material(load_material(query, filing_dir))
