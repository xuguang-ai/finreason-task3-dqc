"""Assemble a complete FinMR ``query`` from primary sources.

The organizers ship each case as one ~40k-character ``query`` string built by
concatenating eight parts: a fixed instruction preamble, six per-filing XBRL
documents, the rendered US GAAP taxonomy for the audited concept, and a
two-question tail. Six of those eight are cut at 32,767 characters each
(measured on the practice set: the Label section hits the cap in 209 of 332
cases and the Instance section in 178), and the answer frequently lives in the
part that was cut — the deterministic solver scores 56.5% on the released text
and 84.9% on the same cases rebuilt whole.

This module rebuilds the whole thing from the sources those parts came from:

* the six XBRL documents from ``task3_source_data/raw_filings/<filing>/``
* the taxonomy section, passed in verbatim from the released query (see ``assemble``) rather than regenerated from
  ``task3_source_data/taxonomy/GAAP_Taxonomy_<year>.xlsx``
* the preamble and question tail reproduced verbatim from the released data

Assembling rather than splicing (see ``task3_raw_filings.splice_raw_sections``,
which patches an existing query) means a case needs no released ``query`` at
all — only ``(concept, period, filing)``. That is what lets the same code path
serve cases the organizers have not published a query for.

Not a byte-reproduction, and deliberately so
---------------------------------------------
The released sections are **not** the raw filing documents. The generator
extracted a statement-level sub-filing per section and re-serialized it: for
``DEV_000000`` the Instance section is 5,999 characters against the 74,473 of
``plasma-20211130_10q_htm.xml``, the Calculation section 731 against 13,005,
and even the context ids are renamed (``From2021-09-012021-11-30_...`` in the
released text vs ``From2021-09-01to2021-11-30`` in the filing). That matches
the FinAuditing paper's own description — "statement-level XBRL sub-filings
serving as the input for numerical reasoning".

So this module cannot and does not reproduce a released ``query`` verbatim; it
emits the same eight-section shape carrying the **complete** documents instead
of a statement-scoped, then truncated, extract. That is a superset of the
released input, which is the entire point: the deterministic solver scores
56.5% on the released text and 84.9% on complete filings.

The one part that IS byte-reproduced is the taxonomy section, in 322 of 332
cases.
"""

from __future__ import annotations

import glob
import re
from pathlib import Path
from typing import Dict, Iterable, List, Mapping, Optional, Tuple

import os

__all__ = [
    "DEFAULT_FILINGS_DIR",
    "SECTION_CHAR_LIMIT",
    "PREAMBLE",
    "assemble",
    "LINKBASE_KEYS",
    "SECTION_KEY_BY_NAME",
    "repair_truncated_linkbase",
    "question_tail",
    "period_phrase",
    "find_filing_dir",
    "filing_index",
]

#: Practice filings live under <FINREASON_DATA>/filings_practice (one directory per filing).
DEFAULT_FILINGS_DIR = Path(os.environ.get("FINREASON_DATA", "data")) / "filings_practice"
_FALLBACK_FILINGS_DIR = DEFAULT_FILINGS_DIR

#: The per-section cut the organizers apply. ``None`` disables it.
SECTION_CHAR_LIMIT = 32767

#: Reproduced verbatim from the released data — identical across all 332 cases.
PREAMBLE = (
    "You are an auditor for XBRL filings. \n"
    "Given the question and the provided filing \n"
    "(schema, presentation, calculation, definition, label, instance, and US GAAP taxonomy), \n"
    "identify the reported value of a financial element and calculate the actual "
    "value that should be reported based on calculation relationships.\n"
    "\n"
    "Answer strictly in the following JSON format:\n"
    "{\n"
    '  "extracted_value": "<numeric value reported in the instance document, or 0 '
    'if not found, keep the same format as in the XBRL filing>",\n'
    '  "calculated_value": "<numeric value computed from calculation relationships, '
    'or 0 if not computable, use the same number formatting style as extracted_value>"\n'
    "}\n"
    "\n"
    "No explanations. No extra text. Only the JSON object."
)

#: Section header -> the raw filing file that supplies it, in emission order.
SECTION_FILES: Tuple[Tuple[str, str], ...] = (
    ("Schema document", ".xsd"),
    ("Presentation linkbase document", "_pre.xml"),
    ("Calculation linkbase document", "_cal.xml"),
    ("Definition linkbase document", "_def.xml"),
    ("Label linkbase document", "_lab.xml"),
    ("Instance document", "_htm.xml"),
)

#: Section header -> the key ``xbrl.split_sections`` uses for it.
SECTION_KEY_BY_NAME: Dict[str, str] = {
    "Schema document": "schema",
    "Presentation linkbase document": "presentation",
    "Calculation linkbase document": "calculation",
    "Definition linkbase document": "definition",
    "Label linkbase document": "label",
    "Instance document": "instance",
}

#: Everything but the Instance — the sections whose released form is
#: statement-scoped and therefore worth keeping over the complete file.
LINKBASE_KEYS: Tuple[str, ...] = (
    "schema",
    "presentation",
    "calculation",
    "definition",
    "label",
)

_TAXONOMY_SECTION = "US GAAP Taxonomy"
_SCHEMA_REF_RE = re.compile(r'schemaRef[^>]*href="([^"]+)\.xsd"')


# --------------------------------------------------------------------------- #
# Locating a filing
# --------------------------------------------------------------------------- #


def _filings_dir(explicit: Optional[Path] = None) -> Path:
    for candidate in (explicit, DEFAULT_FILINGS_DIR, _FALLBACK_FILINGS_DIR):
        if candidate and Path(candidate).is_dir():
            return Path(candidate)
    raise FileNotFoundError(
        f"no filings directory at {DEFAULT_FILINGS_DIR} or {_FALLBACK_FILINGS_DIR}"
    )


def filing_index(filings_dir: Optional[Path] = None) -> Dict[str, Path]:
    """``schemaRef stem`` -> filing directory, e.g. ``plasma-20211130`` -> path.

    The stem drops the leading filing-type token from the directory name
    (``10q-plasma-20211130``). Verified unique: the 157 directories yield 157
    distinct stems, so nothing is silently overwritten here.
    """
    root = _filings_dir(filings_dir)
    return {
        "-".join(d.name.split("-")[1:]): d
        for d in sorted(root.iterdir())
        if d.is_dir()
    }


def find_filing_dir(
    query_or_stem: str, filings_dir: Optional[Path] = None
) -> Optional[Path]:
    """Resolve a filing from either a released ``query`` or a bare stem."""
    m = _SCHEMA_REF_RE.search(query_or_stem)
    stem = m.group(1) if m else query_or_stem.strip()
    return filing_index(filings_dir).get(stem)


def _section_file(filing_dir: Path, suffix: str) -> Optional[Path]:
    matches = sorted(glob.glob(str(filing_dir / f"*{suffix}")))
    if suffix == ".xsd":
        # The linkbases also end in .xml, but a stray "<stem>_cal.xsd" has never
        # appeared; guard anyway so the schema slot cannot pick up a linkbase.
        matches = [
            m for m in matches
            if not m.endswith(("_cal.xml", "_def.xml", "_lab.xml", "_pre.xml"))
        ]
    return Path(matches[0]) if matches else None


# --------------------------------------------------------------------------- #
# The question tail
# --------------------------------------------------------------------------- #


def period_phrase(period: str) -> str:
    """``"2021-09-01 to 2021-11-30"`` and ``"2023-12-31"`` both render as the
    released data words them."""
    return f"the period {period.strip()}"


def question_tail(concept: str, period: str) -> str:
    phrase = period_phrase(period)
    return (
        f"Question1: What's the reported value of {concept} in the Instance "
        f"document for {phrase}?\n"
        f"Question2: What's the actual value of {concept} in the Instance "
        f"document for {phrase}, calculated based on the calculation relationship?\n"
        "Answer:"
    )


# --------------------------------------------------------------------------- #
# Assembly
# --------------------------------------------------------------------------- #


def _clip(text: str, limit: Optional[int]) -> str:
    return text if limit is None or len(text) <= limit else text[:limit]


#: Linkbase elements arrive either as ``<link:presentationLink>`` or, when the
#: filer declares the linkbase namespace as the default, as bare
#: ``<presentationLink>``. Practice had one such filing; the development split
#: has 67 (10%), so the prefix is optional everywhere below.
_LINK_ROLE_RE = re.compile(r'<(?:link:)?(\w+Link)\b[^>]*xlink:role="([^"]+)"')
_LINK_BLOCK_RE = re.compile(
    r"<(?P<prefix>link:)?(?P<tag>\w+Link)\b[^>]*?>.*?</(?P=prefix)(?P=tag)>"
    r"|<(?P<tag2>\w+Link)\b[^>]*?>.*?</(?P=tag2)>",
    re.S,
)
_LINK_OPEN_RE = re.compile(r"<(?:link:)?(?:definition|presentation|calculation)Link\b")


def _is_truncated(section: str) -> bool:
    """A section cut at the cell limit, or one whose last element never closed."""
    if len(section) >= SECTION_CHAR_LIMIT - 2:
        return True
    opens = len(re.findall(r"<(?:link:)?(\w+)Link\b", section))
    closes = len(re.findall(r"</(?:link:)?(\w+)Link>", section))
    return opens > closes


def repair_truncated_linkbase(released: str, complete: str) -> Optional[str]:
    """Rebuild a truncated linkbase section from the complete file, same roles.

    Truncation is the one case where the released text is strictly worse than
    the filing: the statement scoping it carries is only useful if the arcs
    survived, and past the cut they did not. ``DEV_000140`` and ``DEV_000141``
    lose their entire segment hypercube this way — the Definition section stops
    at exactly 32,767 characters mid-``definitionLink`` and no axis is declared,
    so the member filter that decides those cases never runs.

    The repair keeps the scoping rather than discarding it: only the extended
    link roles the released section *names* are taken from the complete file.
    Replacing the whole section instead was measured and is worse (262/285
    against 273), because the complete file unions every statement and note.

    Returns ``None`` when nothing can be repaired — not truncated, no roles
    named, or the complete file has none of them — so the caller keeps the
    released text.

    Honest status: on the practice set this repair currently changes **no**
    answer. It verifiably does its job — ``DEV_000140``'s segment hypercube
    goes from empty to its eight declared members — but those two cases still
    fail downstream, because the restored role declares all four axes and the
    "declared by the hypercube" ranking key then stops discriminating. It is
    kept because it recovers data truncation destroyed, which is a property of
    the input rather than a heuristic fitted to these golds; the axis-name
    tables that were also inert were deleted instead, precisely because they
    were fitted. If a future change makes axis choice sharper, this repair is
    what will let it see the members at all.
    """
    if not released or not complete or not _is_truncated(released):
        return None
    wanted = {role for _tag, role in _LINK_ROLE_RE.findall(released)}
    if not wanted:
        return None

    kept: List[str] = []
    for m in _LINK_BLOCK_RE.finditer(complete):
        role_m = re.search(r'xlink:role="([^"]+)"', m.group(0))
        if role_m and role_m.group(1) in wanted:
            kept.append(m.group(0))
    if not kept:
        return None
    open_m = _LINK_OPEN_RE.search(released)
    header_end = open_m.start() if open_m else -1
    if header_end < 0:
        return None
    header = released[:header_end]
    # Close the document the way the released text opened it.
    closing = "</link:linkbase>" if "<link:linkbase" in header else "</linkbase>"
    return f"{header}{''.join(kept)}\n{closing}"


def assemble(
    concept: str,
    period: str,
    filing_dir: Path,
    taxonomy_dir: Optional[Path] = None,
    section_char_limit: Optional[int] = None,
    taxonomy_year: Optional[int] = None,
    override_sections: Optional[Mapping[str, str]] = None,
    taxonomy_text: str = "",
) -> str:
    """Build the full query for one audit target.

    ``taxonomy_text`` is the ``US GAAP Taxonomy`` section to emit verbatim (the
    rule modules never read it; the hybrid keeps the organizers' text).

    ``section_char_limit`` reproduces the organizers' per-section cut when set
    to :data:`SECTION_CHAR_LIMIT`; leave it ``None`` (the default, and the whole
    point of this module) to keep every section complete.

    ``override_sections`` maps a :data:`SECTION_KEYS` name to text to emit
    instead of the raw file — how :func:`assemble_for_case` keeps the released,
    statement-scoped linkbases. Overrides are emitted verbatim and are never
    clipped: they come from a source that already applied its own limit.

    A missing raw file yields an empty section rather than an exception: a
    partial assembly is still usable, and the caller can spot it by the section
    being empty.
    """
    filing_dir = Path(filing_dir)
    override_sections = dict(override_sections or {})
    parts: List[str] = [PREAMBLE, "\n\n"]

    for name, suffix in SECTION_FILES:
        key = SECTION_KEY_BY_NAME[name]
        if key in override_sections:
            parts.append(f"##{name}\n{override_sections[key]}\n")
            continue
        path = _section_file(filing_dir, suffix)
        body = path.read_text(encoding="utf-8", errors="ignore") if path else ""
        parts.append(f"##{name}\n{_clip(body, section_char_limit)}\n")

    parts.append(f"##{_TAXONOMY_SECTION}\n{taxonomy_text}\n")
    parts.append(question_tail(concept, period))
    return "".join(parts)
