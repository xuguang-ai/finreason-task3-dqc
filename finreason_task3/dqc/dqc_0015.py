"""DQC_US_0015 "Negative Values" -- the official XULE rule, with every constant resolved locally.

Rule body (src_2026_DQC_0015.xule lines 15-28 and 39-44)::

    if not applicable_form_string('0015') skip else
    $fact1 = {nonils @concept in $NON_NEG_ITEMS.keys @unit=* where $fact < 0 and
               ($fact.dimensions.length == 0 or
                 (not match_set_substring($fact, $EXCLUDE_NON_NEG_STRING_MEMBERS)
                  and (to-set($fact.dimensions-explicit.values.name) intersect $EXCLUDE_NON_NEG_MEMBERS).length == 0
                  and ($fact.dimensions.keys.name intersect $EXCLUDE_NON_NEG_AXIS).length == 0
                  and not_elim_adjust($fact, $EXCLUDE_NON_NEG_AXIS_MEMBERS)))};
    $rule_suffix_id = $NON_NEG_ITEMS[$fact1.concept.name];
    true
    ... rule-focus $fact1   effectiveDate $effective_dates[$rule_suffix_id]

So ONE finding per fact: every non-nil fact that has a unit, whose concept is on the list and
whose value is < 0 is flagged, unless it is dimensional AND one of the four exclusions applies.
A fact with no dimensions is never excluded. The finding's numbers are the fact value
(extracted) and its magnitude (calculated).

Rule sources (task3_source_data/dqc_rules/)
-------------------------------------------
The logic is identical in src_2024/2025/2026_DQC_0015.xule. 2024 has CRLF line endings, no
``/** DQCRT RULE **/`` comment and the body indented under ``else``. 2025 adds that comment and
a blank line after ``else`` and un-indents the body. 2026 equals 2025 minus one blank line
before ``effectiveDate``. All three headers say "Taxonomy: US GAAP 2024". Only the 2026
libraries are local (lib_2026_*.xule, lib_functions.xule). lib_2026_resources.xule says
"Release Version 29" (line 8), but its csv-data URLs point at the v30 tag (lines 20, 32).

How each piece is implemented
-----------------------------
``nonils``
    ``xsi:nil`` facts are skipped.
``@unit=*``
    An aspect filter ``= *`` admits the facts that HAVE the aspect, with any value (DQC 0117
    uses ``@$dim = *`` the same way to mean "the fact carries this axis"). A fact without a
    ``unitRef`` is rejected (``"no-unit"``); only numeric facts carry a unit.
``$fact < 0``
    The value is parsed exactly with ``Decimal``; ``-0`` is not < 0.
``@concept in $NON_NEG_ITEMS.keys``  (lib_2026_resources.xule 31-34)
    The rule loads the list from four GitHub CSVs (usgaap/srt/dei/ebp) that are not local.
    The published master list ``DQC_US_0015__DQC_0015_ListOfElements.xlsx`` is used instead
    (generated into ``dqc_0015_items.json`` by dqc_rules/build_0015_items.py). Each row carries
    the release that added it and, if removed, the release that removed it, so the list is
    rebuilt "as of" any DQC release (``version=``): an element is listed at version V when
    ``added <= V`` and it was not removed at or before V. Deprecated elements stay listed
    (the sheet only ends a listing by an explicit removal), and the 46 elements that moved
    from us-gaap to SRT in 2018 have separate srt rows, so both QNames are listed.
``match_set_substring($fact, $EXCLUDE_NON_NEG_STRING_MEMBERS)``  (lib_functions.xule 454-458)
    True when the lower-cased LOCAL NAME of any EXPLICIT dimension member contains one of the
    strings. Axis names and typed-member values are not tested. The 2026 set is read from the
    DQC rules taxonomy (lib_2026_constant-us-gaap.xule 206-209, not local) plus the literals
    'basisswap' and 'unfunded'. The taxonomy part is taken from the commented-out literal it
    replaced (lines 196-203: adjust, consolidat, eliminat, netting, reconcili, reclass), which
    equals the MemberExclusions.xlsx "contains the text (Case insensitive)" rows.
``$EXCLUDE_NON_NEG_MEMBERS``  (lines 213-226)
    Explicit members by QName: the commented-out literal set (9 members, identical to the xlsx
    "Member equals" rows) + EffectOfModifiedRetrospectiveApplicationAccountingStandards
    Update201812Member, which line 226 adds explicitly.
``$EXCLUDE_NON_NEG_AXIS``  (lines 241-253)
    Any dimension (explicit or typed) on one of these axes excludes the fact: the
    commented-out literal set (identical to the xlsx "Axis equals" rows with no member
    condition) + StatementBusinessSegmentsAxis, InvestmentIdentifierAxis and
    ``qname($EXTENSION_NS, 'IncomeTaxEffectChangeInLawAxis')``.
``$EXTENSION_NS``  (lib_2026_constant.xule 31: ``taxonomy().entry-point-namespace``)
    The targetNamespace of the schema the instance's ``schemaRef`` names, read from the
    query's Schema section, else from the raw filing's ``.xsd``, else the single non-standard
    namespace the instance declares. Only that namespace is the extension. Another
    non-standard namespace, such as a filing agent's, is not. When none of these determines
    it, every non-standard namespace is treated as the extension.
``not_elim_adjust($fact, $EXCLUDE_NON_NEG_AXIS_MEMBERS)``  (lib_functions.xule 470-486; constants 229-238)
    For each (axis, members) pair: a fact that has that axis with one of those members is
    excluded. Pairs from the commented-out literal (the xlsx "Axis equals AND member equals"
    rows; the xlsx names the ConsolidatedEntitiesAxis pair us-gaap as of 2017, the 2026
    literal names it srt after the 2018 SRT move): StatementBusinessSegmentsAxis x
    {CorporateAndOther, Corporate, AllOtherSegments}; srt:ConsolidatedEntitiesAxis x
    {srt:ParentCompany, srt:Subsidiaries, srt:GuarantorSubsidiaries, srt:NonGuarantorSubsidiaries,
    srt:SubsidiaryIssuer}; FairValueByMeasurementBasisAxis x {ChangeDuringPeriodFairValueDisclosureMember}.
``applicable_form_string('0015')``  (lib_functions.xule 1047-1049)
    Depends on rule-form-lookup.csv (not local). Every practice and dev filing is a 10-K or
    10-Q, which the rule covers, so the guard is treated as always true.
``effectiveDate``
    An output attribute of the message, not a filter in the rule body. It is reported on each
    finding and does not gate it (an assumption; see APPROXIMATIONS).
Duplicate facts (XULE processor, not the rule text)
    The XULE processor indexes facts with duplicate elimination unless it is run with
    ``--xule-include-dups``. Duplicates are facts with the same concept, period, entity, unit
    and dimensions whose values are equal at the lower of their two ``decimals``. One fact is
    kept per duplicate set, the more precise one. Facts that differ in value are all kept.
    This is the Arelle XULE plugin's default as recalled. It is NOT in the local material.
    ``duplicates`` on each finding counts the instance facts merged into it.

Release model (``version=``)
----------------------------
In XULE a filing is evaluated by the per-taxonomy-year rule set of the DQC release that
processed it. That rule set reads its own ``dqc_15_usgaap_<year>_concepts.csv`` and binds
``us-gaap:`` to that year's namespace. Which release processed each gold filing cannot be
observed. One release carries three taxonomy years (the local snapshot: 2024-2026). Practice
filings use the 2021-2024 taxonomies, so practice gold cannot come from one v29/v30 run.
``DEFAULT_VERSION = 29`` is therefore a CHOSEN release, not an inferred one. Under a
single-release assumption, v20-v29 is the window consistent with practice (DEV_000105 needs
>= 20, DEV_000001 needs <= 29). A per-filing (filing-time) release fits practice equally well.
QNames are compared as (namespace family, local name), which is exact only when the matching
yearly rule set ran.

What is NOT rule logic (``HEURISTICS``)
---------------------------------------
* Order. XULE emits one message per flagged fact, with no order. ``order="tiebreak"`` (the
  default, unchanged) returns the dimension-free finding first, then document order. That is
  a tie-break for callers that need one answer, and it is unvalidated. ``order="document"``
  returns document order only. ``tiebreak_rank`` is always set.
* ``in_released_linkbase`` is a hint, never a filter.

API
---
``findings_0015(query, filing_dir=None, *, version=DEFAULT_VERSION, include_rejected=False,
order="tiebreak", allow_truncated=False)``
    Findings for the QUESTIONED concept and period, one dict per flagged (de-duplicated) fact::

        {"concept", "context_id", "dims", "period", "extracted", "calculated", "value", "unit",
         "decimals", "fact_id", "duplicates", "duplicate_fact_ids", "rule_element_id",
         "rule_id", "effective_date", "version_sensitive", "pos", "tiebreak_rank",
         "instance_source", "instance_complete", "in_released_linkbase"}

    ``extracted``/``calculated`` are plain decimal strings (``"-2881000"``/``"2881000"``).
    ``in_released_linkbase`` is True when every axis/member of a dimensional finding appears in
    the released, statement-scoped definition/presentation sections (None when dimension-free).
    ``version_sensitive`` says the finding's concept is listed differently somewhere in
    v17..v30 (a per-finding flag; it cannot see a concept listed only in other releases).
    With ``include_rejected`` the questioned concept's unflagged facts are returned too, with
    ``rejected`` (first reason) and ``rejected_all`` (every exclusion that applies).
    If the instance has no closing ``</xbrl>`` and ``filing_dir`` gives no complete raw instance,
    :class:`IncompleteInstanceError` is raised. With ``allow_truncated=True``, the truncated
    instance is used and every finding says ``instance_complete=False``.
``all_findings_0015(query_or_instance, filing_dir=None, *, version=..., order=..., allow_truncated=False)``
    Every fact the rule flags in the filing, any concept and period.
``instance_info(query, filing_dir=None)``
    Which instance would be used, and whether it is complete, plus ``$EXTENSION_NS`` and its source.
``is_listed(concept, version=DEFAULT_VERSION)``, ``rule_element_id(...)``, ``listing_versions(...)``
    The element list as of a release.
``exclusion_reasons(dims, nsmap=None, ext_ns=None)`` / ``exclusion_reason(...)``
    Every exclusion that exempts a dimensional context, or the first one (None when the rule
    would flag it).
"""
from __future__ import annotations

import json
import re
from decimal import Decimal, InvalidOperation
from functools import lru_cache
from pathlib import Path
from typing import Dict, Iterable, List, NamedTuple, Optional, Sequence, Tuple

from .. import xbrl as X

__all__ = [
    "DEFAULT_VERSION",
    "LATEST_VERSION",
    "VERSION_SENSITIVITY_RANGE",
    "APPROXIMATIONS",
    "HEURISTICS",
    "ORDERS",
    "EXCLUDE_NON_NEG_STRING_MEMBERS",
    "EXCLUDE_NON_NEG_MEMBERS",
    "EXCLUDE_NON_NEG_AXIS",
    "EXCLUDE_NON_NEG_AXIS_MEMBERS",
    "IncompleteInstanceError",
    "findings_0015",
    "all_findings_0015",
    "instance_info",
    "is_listed",
    "rule_element_id",
    "listing_versions",
    "exclusion_reasons",
    "exclusion_reason",
    "entry_point_namespace",
    "namespace_map",
    "ns_family",
]

# --------------------------------------------------------------------------- #
# Versions
# --------------------------------------------------------------------------- #

#: The rule set shipped with the local sources reads its CSVs from the v30 tag.
LATEST_VERSION = 30

#: A CHOSEN release (see "Release model" in the module docstring), not an inferred one.
#: Under a single-release assumption v20..v29 is the window consistent with practice:
#: DEV_000105 (an element added in v20) needs >= 20 and DEV_000001
#: (IncomeTaxReconciliationTaxCredits, removed in v30) needs <= 29. On dev, a full v17..v30
#: sweep changes the answer set of 5 cases, each from no finding to one: DEV3_000001/012/075/141
#: fire only from v26 and DEV3_000137 only from v24. 29 keeps all five, and neither sibling rule
#: module fires on them.
DEFAULT_VERSION = 29

#: Releases that can plausibly have produced Task 3 gold (filings dated 2021-2026).
VERSION_SENSITIVITY_RANGE = range(17, LATEST_VERSION + 1)

APPROXIMATIONS: Tuple[str, ...] = (
    "$NON_NEG_ITEMS comes from four GitHub CSVs (usgaap/srt/dei/ebp, v30 tag) that are not local; "
    "it is rebuilt from DQC_0015_ListOfElements.xlsx (7,994 rows) as of a release using each row's "
    "add/removal release. Deprecated elements stay listed; the sheet ends a listing only by removal.",
    "Release model: XULE evaluates each filing with the per-taxonomy-year rule set of the release "
    "that processed it; which release produced each gold is not observable. DEFAULT_VERSION=29 is "
    "CHOSEN; under a single-release assumption v20..v29 is the window consistent with practice, and a "
    "per-filing (filing-time) release fits practice equally well. QNames are compared as (namespace "
    "family, local name), which ignores the us-gaap/srt year and the dei version.",
    "effectiveDate is an output attribute, not a filter; whether the harness that produced the gold "
    "filtered messages by effective date is not observable. No practice gold can test it; on dev only "
    "DEV3_000001 and DEV3_000141 (10-Ks filed 2025-03-06, v26 elements effective 2025-03-31) could flip.",
    "$EXCLUDE_NON_NEG_STRING_MEMBERS, $EXCLUDE_NON_NEG_MEMBERS, $EXCLUDE_NON_NEG_AXIS and "
    "$EXCLUDE_NON_NEG_AXIS_MEMBERS are read in 2026 from the DQC rules taxonomy (not local); they are "
    "taken from the commented-out literal sets they replaced, which equal the MemberExclusions.xlsx "
    "rows, plus the items the 2026 code adds explicitly ('basisswap', 'unfunded', "
    "EffectOfModifiedRetrospectiveApplicationAccountingStandardsUpdate201812Member, "
    "StatementBusinessSegmentsAxis, InvestmentIdentifierAxis, extension IncomeTaxEffectChangeInLawAxis). "
    "The substrings are kept lower-case (the xlsx says 'Case insensitive'); match_set_substring "
    "lower-cases only the member name, so if the 2026 taxonomy stored them capitalised they would "
    "never match in 2026. Practice confirms only 'reconcili', 'basisswap', StatementEquityComponentsAxis "
    "and StatementBusinessSegmentsAxis; other exclusions are unexercised by practice "
    "(validate_0015.py lists the dev answers that depend on them, by ablation).",
    "$EXTENSION_NS is the entry-point namespace: the schemaRef'd schema's targetNamespace from the "
    "query's Schema section or the raw filing's .xsd, else the single non-standard namespace in the "
    "instance; when undetermined, every non-standard namespace counts as the extension.",
    "applicable_form_string('0015') depends on rule-form-lookup.csv (not local); 10-K/10-Q filings "
    "are assumed in scope (all practice and dev filings are 10-K or 10-Q).",
    "Duplicate facts follow the XULE processor's default duplicate elimination (Arelle XULE plugin, "
    "--xule-include-dups off; recalled, not in the local material): same concept/period/entity/unit/"
    "dimensions and equal values at the lower decimals -> one fact, the more precise one. Nil facts "
    "are removed by nonils before this and never merge with valued facts.",
)

HEURISTICS: Tuple[str, ...] = (
    "Order: XULE emits findings unordered. order='tiebreak' (default) puts the dimension-free finding "
    "first, then document order; it decides every case with more than one distinct answer and is "
    "UNVALIDATED (on practice all such cases sit in byte-identical conflicting groups whose golds are a "
    "permutation of the findings, so any deterministic pick scores the same). order='document' gives "
    "document order only.",
    "in_released_linkbase: every axis/member of a dimensional finding appears in the released "
    "statement-scoped linkbases. A hint only; as a filter it would drop 8 of 110 practice golds.",
)

ORDERS = ("tiebreak", "document")

# --------------------------------------------------------------------------- #
# Exclusion constants (resolved)
# --------------------------------------------------------------------------- #

#: lib_2026_constant-us-gaap.xule 196-209. Lower-case; compared against the
#: lower-cased member local name (lib_functions.xule 454-458).
EXCLUDE_NON_NEG_STRING_MEMBERS: Tuple[str, ...] = (
    "adjust",
    "consolidat",
    "eliminat",
    "netting",
    "reconcili",
    "reclass",
    "basisswap",
    "unfunded",
)

#: lib_2026_constant-us-gaap.xule 213-226.
EXCLUDE_NON_NEG_MEMBERS = frozenset(
    {
        ("us-gaap", "CorporateNonSegmentMember"),
        ("us-gaap", "FairValueConcentrationOfRiskMarketRiskManagementEffectsOnIncomeOrNetAssetsMember"),
        ("us-gaap", "AccumulatedNetGainLossFromDesignatedOrQualifyingCashFlowHedgesMember"),
        ("us-gaap", "AccumulatedNetUnrealizedInvestmentGainLossMember"),
        ("us-gaap", "DeferredDerivativeGainLossMember"),
        ("us-gaap", "AboveMarketLeasesMember"),
        ("us-gaap", "NewAccountingPronouncementEarlyAdoptionEffectMember"),
        ("us-gaap", "UnallocatedFinancingReceivablesMember"),
        ("us-gaap", "DifferenceBetweenRevenueGuidanceInEffectBeforeAndAfterTopic606Member"),
        ("us-gaap", "EffectOfModifiedRetrospectiveApplicationAccountingStandardsUpdate201812Member"),
    }
)

#: lib_2026_constant-us-gaap.xule 241-253. ("ext", name) = qname($EXTENSION_NS, name).
EXCLUDE_NON_NEG_AXIS = frozenset(
    {
        ("us-gaap", "StatementEquityComponentsAxis"),
        ("us-gaap", "ErrorCorrectionsAndPriorPeriodAdjustmentsRestatementByRestatementPeriodAndAmountAxis"),
        ("us-gaap", "AdjustmentsForChangeInAccountingPrincipleAxis"),
        ("us-gaap", "AdjustmentsForNewAccountingPronouncementsAxis"),
        ("us-gaap", "ProspectiveAdoptionOfNewAccountingPronouncementsAxis"),
        ("us-gaap", "QuantifyingMisstatementInCurrentYearFinancialStatementsByNatureOfErrorAxis"),
        ("us-gaap", "PartnerCapitalComponentsAxis"),
        ("us-gaap", "ChangeInAccountingEstimateByTypeAxis"),
        ("us-gaap", "PartnerTypeOfPartnersCapitalAccountAxis"),
        ("us-gaap", "StatementBusinessSegmentsAxis"),
        ("us-gaap", "InvestmentIdentifierAxis"),
        ("ext", "IncomeTaxEffectChangeInLawAxis"),
    }
)

#: lib_2026_constant-us-gaap.xule 229-238; consumed by not_elim_adjust.
EXCLUDE_NON_NEG_AXIS_MEMBERS: Tuple[Tuple[Tuple[str, str], frozenset], ...] = (
    (
        ("us-gaap", "StatementBusinessSegmentsAxis"),
        frozenset({("us-gaap", "CorporateAndOtherMember"), ("us-gaap", "CorporateMember"),
                   ("us-gaap", "AllOtherSegmentsMember")}),
    ),
    (
        ("srt", "ConsolidatedEntitiesAxis"),
        frozenset({("srt", "ParentCompanyMember"), ("srt", "SubsidiariesMember"),
                   ("srt", "GuarantorSubsidiariesMember"), ("srt", "NonGuarantorSubsidiariesMember"),
                   ("srt", "SubsidiaryIssuerMember")}),
    ),
    (
        ("us-gaap", "FairValueByMeasurementBasisAxis"),
        frozenset({("us-gaap", "ChangeDuringPeriodFairValueDisclosureMember")}),
    ),
)

# --------------------------------------------------------------------------- #
# Namespaces
# --------------------------------------------------------------------------- #

_STD_NS = (
    (re.compile(r"^https?://fasb\.org/us-gaap-ebp/", re.I), "us-gaap-ebp"),
    (re.compile(r"^https?://fasb\.org/ebp/", re.I), "us-gaap-ebp"),
    (re.compile(r"^https?://fasb\.org/us-gaap/", re.I), "us-gaap"),
    (re.compile(r"^https?://fasb\.org/srt/", re.I), "srt"),
    (re.compile(r"^https?://xbrl\.sec\.gov/dei/", re.I), "dei"),
    (re.compile(r"^https?://xbrl\.sec\.gov/invest/", re.I), "invest"),
)
_OTHER_STD_NS = re.compile(r"^https?://(?:fasb\.org|xbrl\.sec\.gov|www\.xbrl\.org|xbrl\.org|www\.w3\.org)/", re.I)
_PREFIX_FALLBACK = {"us-gaap": "us-gaap", "srt": "srt", "dei": "dei", "invest": "invest",
                    "us-gaap-ebp": "us-gaap-ebp", "ebp": "us-gaap-ebp"}
_XMLNS_RE = re.compile(r"xmlns:([A-Za-z_][\w.-]*)\s*=\s*\"([^\"]*)\"")
_SCHEMA_TNS_RE = re.compile(r"<(?:[A-Za-z_][\w.-]*:)?schema\b[^>]*?\btargetNamespace\s*=\s*[\"']([^\"']+)[\"']", re.S)
_SCHEMAREF_RE = re.compile(r"<(?:[A-Za-z_][\w.-]*:)?schemaRef\b[^>]*?\bxlink:href\s*=\s*[\"']([^\"']+)[\"']", re.S)


def ns_family(uri: Optional[str], ext_ns: Optional[str] = None) -> str:
    """Namespace URI -> family used for QName comparison.

    ``"ext"`` stands for ``$EXTENSION_NS``. With ``ext_ns`` given, only that URI is ``"ext"`` and
    any other non-standard namespace is ``"nonstd:<uri>"`` (equal to nothing in the rule's
    constants). With ``ext_ns=None`` (entry point unknown) every non-standard namespace is ``"ext"``.
    """
    if not uri:
        return "ext" if ext_ns is None else "nonstd:"
    for rx, fam in _STD_NS:
        if rx.match(uri):
            return fam
    if _OTHER_STD_NS.match(uri):
        # other standard namespaces (country, currency, srt-types, xbrldi, ...): keep a
        # distinct family so they never equal a us-gaap/srt name nor the extension.
        return "std:" + re.sub(r"/\d{4}(?:-\d{2}-\d{2})?/?$", "", uri.lower())
    if ext_ns is None or uri == ext_ns:
        return "ext"
    return "nonstd:" + uri


def namespace_map(instance_text: str) -> Dict[str, str]:
    """``{prefix: uri}`` from every ``xmlns:`` declaration in the instance (first one wins)."""
    out: Dict[str, str] = {}
    for p, u in _XMLNS_RE.findall(instance_text):
        out.setdefault(p, u)
    return out


def _qname(name: str, nsmap: Dict[str, str], ext_ns: Optional[str] = None) -> Tuple[str, str]:
    """``"prefix:Local"`` (or ``"{uri}Local"``) -> ``(family, local)``."""
    name = name.strip()
    if name.startswith("{"):
        uri, _, local = name[1:].partition("}")
        return ns_family(uri, ext_ns), local
    if ":" in name:
        prefix, local = name.split(":", 1)
        uri = nsmap.get(prefix)
        if uri is not None:
            return ns_family(uri, ext_ns), local
        return _PREFIX_FALLBACK.get(prefix, "ext"), local
    return "", name


def entry_point_namespace(instance_text: str, schema_section: Optional[str] = None, filing_dir=None,
                          nsmap: Optional[Dict[str, str]] = None) -> Tuple[Optional[str], str]:
    """``$EXTENSION_NS`` (``taxonomy().entry-point-namespace``, lib_2026_constant.xule 31).

    Returns ``(uri, source)``. ``source`` is ``"schema_section"``, ``"filing_xsd"``,
    ``"single_extension_namespace"`` or ``"unknown"`` (uri None).
    """
    if schema_section:
        m = _SCHEMA_TNS_RE.search(schema_section)
        if m:
            return m.group(1), "schema_section"
    if filing_dir:
        d = Path(filing_dir)
        if d.is_dir():
            cands: List[Path] = []
            m = _SCHEMAREF_RE.search(instance_text or "")
            if m:
                cands.append(d / m.group(1).rsplit("/", 1)[-1])
            xsds = sorted(d.glob("*.xsd"))
            if len(xsds) == 1:
                cands.append(xsds[0])
            for p in cands:
                if p.is_file():
                    try:
                        m2 = _SCHEMA_TNS_RE.search(p.read_text(encoding="utf-8", errors="replace"))
                    except OSError:
                        continue
                    if m2:
                        return m2.group(1), "filing_xsd"
    nsmap = nsmap if nsmap is not None else namespace_map(instance_text or "")
    ext = sorted({u for u in nsmap.values() if ns_family(u) == "ext"})
    if len(ext) == 1:
        return ext[0], "single_extension_namespace"
    return None, "unknown"


# --------------------------------------------------------------------------- #
# $NON_NEG_ITEMS
# --------------------------------------------------------------------------- #

_ITEMS_PATH = Path(__file__).with_name("dqc_0015_items.json")


@lru_cache(maxsize=1)
def _items() -> Dict[Tuple[str, str], List[list]]:
    data = json.loads(_ITEMS_PATH.read_text())
    out: Dict[Tuple[str, str], List[list]] = {}
    for key, rows in data["items"].items():
        prefix, local = key.split(":", 1)
        out[(_PREFIX_FALLBACK.get(prefix, prefix), local)] = rows
    return out


@lru_cache(maxsize=1)
def _items_by_local() -> Dict[str, List[Tuple[str, str]]]:
    out: Dict[str, List[Tuple[str, str]]] = {}
    for fam, local in _items():
        out.setdefault(local, []).append((fam, local))
    return out


def _active_rows(key: Tuple[str, str], version: int) -> List[list]:
    rows = _items().get(key, ())
    return [r for r in rows if r[1] <= version and (r[2] is None or version < r[2])]


def _resolve_concept(concept: str, nsmap: Optional[Dict[str, str]] = None) -> List[Tuple[str, str]]:
    fam, local = _qname(concept, nsmap or {})
    if fam:
        return [(fam, local)]
    return list(_items_by_local().get(local, [("", local)]))


def is_listed(concept: str, version: int = DEFAULT_VERSION, nsmap: Optional[Dict[str, str]] = None) -> bool:
    """True when ``concept`` is in ``$NON_NEG_ITEMS`` at ``version``.

    ``concept`` may be ``"us-gaap:Foo"`` (prefix resolved through ``nsmap`` when given,
    else by the standard prefix names), ``"{uri}Foo"``, or a bare local name (any family).
    """
    return any(_active_rows(k, version) for k in _resolve_concept(concept, nsmap))


def rule_element_id(concept: str, version: int = DEFAULT_VERSION,
                    nsmap: Optional[Dict[str, str]] = None) -> Optional[int]:
    """The rule suffix (``DQC.US.0015.<id>``) of a listed concept, else ``None``."""
    for k in _resolve_concept(concept, nsmap):
        rows = _active_rows(k, version)
        if rows:
            return max(rows, key=lambda r: (r[1], r[0]))[0]
    return None


def listing_versions(concept: str, nsmap: Optional[Dict[str, str]] = None,
                     versions: Iterable[int] = VERSION_SENSITIVITY_RANGE) -> Dict[int, bool]:
    """``{version: listed}`` -- shows whether a concept's listing depends on the release."""
    return {v: is_listed(concept, v, nsmap) for v in versions}


def _version_sensitive(key: Tuple[str, str]) -> bool:
    states = {bool(_active_rows(key, v)) for v in VERSION_SENSITIVITY_RANGE}
    return len(states) > 1


# --------------------------------------------------------------------------- #
# Exclusions
# --------------------------------------------------------------------------- #


def exclusion_reasons(dims: Sequence[Tuple[str, str]], nsmap: Optional[Dict[str, str]] = None,
                      ext_ns: Optional[str] = None) -> List[str]:
    """Every exclusion that exempts a context with ``dims`` (empty list: the rule flags it).

    ``dims`` is ``[(axis, member), ...]`` as in :class:`xbrl.Context` (typed members are
    written ``"<typed>..."``). An empty ``dims`` is never exempt. Reasons, in rule order:
    ``member-substring:<s>:<member>``, ``member:<member>``, ``axis:<axis>``,
    ``axis-member:<axis>=<member>`` (local names).
    """
    if not dims:
        return []
    nsmap = nsmap or {}
    explicit = [(_qname(a, nsmap, ext_ns), _qname(m, nsmap, ext_ns)) for a, m in dims if not m.startswith("<typed>")]
    axes = [_qname(a, nsmap, ext_ns) for a, _ in dims]
    out: List[str] = []
    # 1. match_set_substring: lower-cased member local names (explicit only)
    for _axis, (_fam, mlocal) in explicit:
        low = mlocal.lower()
        for s in EXCLUDE_NON_NEG_STRING_MEMBERS:
            if s in low:
                out.append(f"member-substring:{s}:{mlocal}")
    # 2. explicit member in $EXCLUDE_NON_NEG_MEMBERS
    for _axis, mem in explicit:
        if mem in EXCLUDE_NON_NEG_MEMBERS:
            out.append(f"member:{mem[1]}")
    # 3. any axis (explicit or typed) in $EXCLUDE_NON_NEG_AXIS
    for ax in axes:
        if ax in EXCLUDE_NON_NEG_AXIS:
            out.append(f"axis:{ax[1]}")
    # 4. not_elim_adjust
    by_axis = {ax: mem for ax, mem in explicit}
    for ax, members in EXCLUDE_NON_NEG_AXIS_MEMBERS:
        mem = by_axis.get(ax)
        if mem is not None and mem in members:
            out.append(f"axis-member:{ax[1]}={mem[1]}")
    return out


def exclusion_reason(dims: Sequence[Tuple[str, str]], nsmap: Optional[Dict[str, str]] = None,
                     ext_ns: Optional[str] = None) -> Optional[str]:
    """The first exclusion that exempts ``dims``, or ``None`` if the rule would flag it."""
    reasons = exclusion_reasons(dims, nsmap, ext_ns)
    return reasons[0] if reasons else None


# --------------------------------------------------------------------------- #
# Instance
# --------------------------------------------------------------------------- #


class IncompleteInstanceError(ValueError):
    """The instance has no closing ``</xbrl>`` and no complete raw instance was found.

    XULE ran on the whole filing; findings from a truncated instance can miss facts. Pass the
    raw filing directory as ``filing_dir``, or ``allow_truncated=True`` to accept partial findings.
    """


_XBRL_END_RE = re.compile(r"</(?:[A-Za-z_][\w.-]*:)?xbrl>\s*$")


def _is_complete(text: Optional[str]) -> bool:
    return bool(text) and bool(_XBRL_END_RE.search(text.strip()))


def _raw_instance(filing_dir) -> Optional[str]:
    if not filing_dir:
        return None
    d = Path(filing_dir)
    if not d.is_dir():
        return None
    cands = sorted(d.glob("*_htm.xml")) or [p for p in sorted(d.glob("*.xml"))
                                            if not re.search(r"_(cal|def|lab|pre)\.xml$", p.name)]
    for p in cands:
        try:
            return p.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
    return None


class _Loaded(NamedTuple):
    sections: Optional[Dict[str, str]]
    source: str  #: "query" | "raw_filing" | "query(truncated)"
    complete: bool
    nsmap: Dict[str, str]
    doc: X.InstanceDoc
    ext_ns: Optional[str]
    ext_ns_source: str


@lru_cache(maxsize=8)
def _load(query: str, filing_dir: Optional[str], allow_truncated: bool) -> _Loaded:
    """Parse once per (query, filing_dir); callers must not mutate the result."""
    sections = X.split_sections(query) if "##Instance document" in query else None
    inst = sections["instance"] if sections is not None else query
    if _is_complete(inst):
        text, source, complete = inst, "query", True
    else:
        raw = _raw_instance(filing_dir)
        if _is_complete(raw):
            text, source, complete = raw, "raw_filing", True
        elif allow_truncated:
            text, source, complete = inst, "query(truncated)", False
        else:
            raise IncompleteInstanceError(
                "instance has no closing </xbrl> and no complete raw instance was found "
                f"(filing_dir={filing_dir!r}); pass the raw filing directory or allow_truncated=True")
    nsmap = namespace_map(text)
    doc = X.parse_instance(text)
    ext_ns, ext_src = entry_point_namespace(text, (sections or {}).get("schema"), filing_dir, nsmap)
    return _Loaded(sections, source, complete, nsmap, doc, ext_ns, ext_src)


def _dir_key(filing_dir) -> Optional[str]:
    return str(filing_dir) if filing_dir else None


def instance_info(query: str, filing_dir=None) -> dict:
    """Which instance the rule would read, whether it is complete, and ``$EXTENSION_NS``."""
    try:
        ld = _load(query, _dir_key(filing_dir), False)  # shares the cache with findings_0015
    except IncompleteInstanceError:
        ld = _load(query, _dir_key(filing_dir), True)
    return {"instance_source": ld.source, "instance_complete": ld.complete,
            "extension_ns": ld.ext_ns, "extension_ns_source": ld.ext_ns_source}


# --------------------------------------------------------------------------- #
# Facts
# --------------------------------------------------------------------------- #

_INF = float("inf")


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


def _plain(d: Decimal) -> str:
    s = format(d, "f")
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    return "0" if s in ("-0", "", "-") else s


def _norm_date(d: Optional[str]) -> Optional[str]:
    if d is None:
        return None
    d = d.strip()
    return d[:10] if re.match(r"^\d{4}-\d{2}-\d{2}T00:00:00", d) else d


def _period_key(ctx: X.Context) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    return (_norm_date(ctx.start), _norm_date(ctx.end), _norm_date(ctx.instant))


def _decimals(f: X.Fact) -> float:
    d = (f.decimals or "").strip()
    if not d or d.upper() == "INF":
        return _INF
    try:
        return int(d)
    except ValueError:
        return _INF


def _same_value(v1: Decimal, d1: float, v2: Decimal, d2: float) -> bool:
    """Equal at the lower of the two precisions (exact when a side is INF)."""
    m = min(d1, d2)
    a = v1 if d1 == _INF else round(v1, int(m))
    b = v2 if d2 == _INF else round(v2, int(m))
    return a == b


def _aspects(f: X.Fact, ctx: X.Context, key: Tuple[str, str], ld: _Loaded) -> tuple:
    unit = ld.doc.units.get(f.unit_ref)
    dims = frozenset(
        (_qname(a, ld.nsmap, ld.ext_ns), m if m.startswith("<typed>") else _qname(m, ld.nsmap, ld.ext_ns))
        for a, m in ctx.dims
    )
    return (key, _period_key(ctx), ctx.entity, unit if unit is not None else ("unitRef", f.unit_ref), dims)


def _rule_reasons(value: Decimal, key: Tuple[str, str], ctx: X.Context, version: int, ld: _Loaded) -> List[str]:
    """Empty when the rule flags the fact, else every reason it does not."""
    if not (value < 0):
        return ["not-negative"]
    if not _active_rows(key, version):
        return ["not-listed"]
    return exclusion_reasons(ctx.dims, ld.nsmap, ld.ext_ns)


def _record(f: X.Fact, ctx: X.Context, key: Tuple[str, str], value: Optional[Decimal], version: int,
            members: Sequence[X.Fact]) -> dict:
    pk = _period_key(ctx)
    rows = _active_rows(key, version)
    rid = max(rows, key=lambda r: (r[1], r[0])) if rows else None
    return {
        "concept": f.concept,
        "context_id": ctx.id,
        "dims": [list(d) for d in ctx.dims],
        "period": {"start": pk[0], "end": pk[1], "instant": pk[2]},
        "extracted": _plain(value) if value is not None else None,
        "calculated": _plain(-value) if value is not None else None,
        "value": value,
        "unit": f.unit_ref,
        "decimals": f.decimals,
        "fact_id": f.id,
        "duplicates": len(members),
        "duplicate_fact_ids": [m.id for m in members],
        "rule_element_id": rid[0] if rid else None,
        "rule_id": f"DQC.US.0015.{rid[0]}" if rid else None,
        "effective_date": rid[3] if rid else None,
        "version_sensitive": _version_sensitive(key),
        "pos": min(m.pos for m in members),
    }


def _scan(ld: _Loaded, version: int, want: Optional[Tuple[str, str]] = None,
          period: Optional[Tuple[Optional[str], Optional[str], Optional[str]]] = None,
          include_rejected: bool = False) -> List[dict]:
    doc = ld.doc
    facts = list(doc.facts)
    if doc.dangling_fact is not None and doc.dangling_fact.value is not None:
        facts.append(doc.dangling_fact)
    out: List[dict] = []
    groups: Dict[tuple, List[dict]] = {}
    kept: List[dict] = []
    for f in facts:
        key = _qname(f.concept, ld.nsmap, ld.ext_ns)
        if want is not None and key != want:
            continue
        ctx = doc.contexts.get(f.context_ref)
        if ctx is None:
            continue
        if period is not None and _period_key(ctx) != period:
            continue
        # factset filters: nonils, @unit=*; then a numeric value for `$fact < 0`
        value = _to_decimal(f.value)
        reason = "nil" if f.nil else ("no-unit" if not (f.unit_ref or "").strip() else
                                      ("non-numeric" if value is None else None))
        if reason is not None:
            if include_rejected:
                rec = _record(f, ctx, key, None if f.nil else value, version, [f])
                rec["rejected"], rec["rejected_all"] = reason, [reason]
                out.append(rec)
            continue
        # duplicate elimination (XULE processor default)
        dec = _decimals(f)
        entries = groups.setdefault(_aspects(f, ctx, key, ld), [])
        for e in entries:
            if _same_value(value, dec, e["value"], e["dec"]):
                e["members"].append(f)
                if dec > e["dec"]:
                    e.update(fact=f, ctx=ctx, value=value, dec=dec)
                break
        else:
            e = {"fact": f, "ctx": ctx, "key": key, "value": value, "dec": dec, "members": [f]}
            entries.append(e)
            kept.append(e)
    for e in kept:
        reasons = _rule_reasons(e["value"], e["key"], e["ctx"], version, ld)
        if reasons and not include_rejected:
            continue
        rec = _record(e["fact"], e["ctx"], e["key"], e["value"], version, e["members"])
        if include_rejected:
            rec["rejected"] = reasons[0] if reasons else None
            rec["rejected_all"] = reasons
        out.append(rec)
    return out


def _order(found: List[dict], order: str) -> List[dict]:
    if order not in ORDERS:
        raise ValueError(f"order must be one of {ORDERS}, got {order!r}")
    tie = sorted(found, key=lambda r: (1 if r["dims"] else 0, r["pos"]))
    for i, r in enumerate(tie):
        r["tiebreak_rank"] = i
    return tie if order == "tiebreak" else sorted(found, key=lambda r: r["pos"])


def _released_names(sections: Optional[Dict[str, str]]) -> set:
    """Local names of every locator in the released (statement-scoped) definition and
    presentation sections -- used only for the ``in_released_linkbase`` hint."""
    names = set()
    if not sections:
        return names
    for key in ("definition", "presentation"):
        for href in re.findall(r"xlink:href=\"[^\"]*#([^\"]+)\"", sections.get(key) or ""):
            names.add(href.split("_", 1)[-1])
    return names


def findings_0015(query: str, filing_dir=None, *, version: int = DEFAULT_VERSION,
                  include_rejected: bool = False, order: str = "tiebreak",
                  allow_truncated: bool = False) -> List[dict]:
    """DQC_US_0015 findings for the questioned concept and period of one Task 3 case.

    ``filing_dir`` (optional) is the raw filing directory. Its instance is read only when the
    query's instance is truncated, and its ``.xsd`` only when the query has no Schema section
    naming ``$EXTENSION_NS``. Raises :class:`IncompleteInstanceError` when the instance is
    truncated and no complete raw instance is found, unless ``allow_truncated``.
    """
    try:
        q = X.parse_question(query)
    except ValueError:
        return []
    ld = _load(query, _dir_key(filing_dir), allow_truncated)
    want = _qname(q.concept, ld.nsmap, ld.ext_ns)
    period = (_norm_date(q.start), _norm_date(q.end), _norm_date(q.instant))
    found = _scan(ld, version, want=want, period=period, include_rejected=include_rejected)
    released = _released_names(ld.sections) if found else set()
    for r in found:
        r["instance_source"] = ld.source
        r["instance_complete"] = ld.complete
        names = {n.split(":", 1)[-1] for d in r["dims"] for n in d if not n.startswith("<typed>")}
        # hint only (not part of the rule): every axis/member of a dimensional finding is
        # named in the released statement-scoped linkbases; None for dimension-free facts.
        r["in_released_linkbase"] = (names <= released) if names else None
    return _order(found, order)


def all_findings_0015(query_or_instance: str, filing_dir=None, *, version: int = DEFAULT_VERSION,
                      order: str = "tiebreak", allow_truncated: bool = False) -> List[dict]:
    """Every fact the rule flags anywhere in the filing (all concepts, all periods)."""
    ld = _load(query_or_instance, _dir_key(filing_dir), allow_truncated)
    found = _scan(ld, version)
    for r in found:
        r["instance_source"] = ld.source
        r["instance_complete"] = ld.complete
    return _order(found, order)
