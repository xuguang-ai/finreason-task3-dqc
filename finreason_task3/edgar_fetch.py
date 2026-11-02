#!/usr/bin/env python3
"""Complete the ranked-phase queries from the same filings on SEC EDGAR.

    python3 edgar_fetch.py map                       # cases -> filings -> accessions
    EDGAR_CONTACT="Team Name email@example.org" \\
    python3 edgar_fetch.py fetch                     # download the six XBRL files
    python3 edgar_fetch.py rebuild                   # hybrid queries, one file per split

Why this exists. The organizers cut every section of a query at 32,767
characters. On the development split that leaves the Instance section short in
39% of cases and the asked-about fact absent in 24%; nobody reading only the
query can answer those. The organizers confirmed (24 Sep 2026) that restoring
the Instance from the same filing's complete XBRL on EDGAR is allowed. What
stays forbidden is reading an *answer* off any service that publishes
data-quality findings; nothing here touches one.

Three stages, each idempotent and resumable:

map      Every case names its filing twice: the CIK in the Instance's context
         identifier and the `<stem>` of its schemaRef (`rtx-20241231`). One
         call per CIK to data.sec.gov lists that filer's submissions; the
         filing is the one whose primary document starts with the stem. Match
         on the stem, never on reportDate alone — a 10-Q and its 10-Q/A share a
         reportDate and the amendment's files carry a different prefix.
fetch    For each filing, the Archives directory listing names the six XBRL
         files (`<stem>.xsd`, `_pre`, `_cal`, `_def`, `_lab`, `<stem>_htm.xml`).
         They land in raw_filings_ranked/<cik>-<stem>/ so `task3_query.assemble`
         reads them unchanged. Keyed on CIK as well as stem because two Lord
         Abbett entities share `lordabbett-20250930`.
rebuild  Hybrid assembly — Instance from the complete filing, the released
         statement-scoped linkbases kept, truncated linkbases repaired role by
         role — which measured best on practice (273/285 against 267/285 for
         all-complete). Writes <split>_inputs_hybrid.jsonl beside the inputs.

SEC's fair-access policy requires a User-Agent naming a contact and caps
requests at 10/s; `fetch` refuses to start without EDGAR_CONTACT and sleeps to
stay under the cap. `map` reads only data.sec.gov, which accepts a descriptive
agent string.
"""
from __future__ import annotations

import json
import os
import re
import ssl
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
from pathlib import Path

HERE = Path(os.environ.get("FINREASON_DATA", "data")).resolve()   # the data directory

SPLITS = {"development": HERE / "development_inputs.jsonl", "test": HERE / "test_inputs.jsonl"}
MANIFEST = HERE / "edgar_manifest.json"
FILINGS = HERE / "filings"
SUFFIXES = (".xsd", "_pre.xml", "_cal.xml", "_def.xml", "_lab.xml", "_htm.xml")

SREF = re.compile(r'schemaRef[^>]*href="[^"]*?([\w.-]+?-\d{8})(?:_htm)?\.xsd"')
CIK = re.compile(r'<(?:xbrli:)?identifier[^>]*scheme="http://www\.sec\.gov/CIK"[^>]*>(\d+)<')
MIN_INTERVAL = 0.13  # seconds between requests: under SEC's 10/s with margin

try:
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except ImportError:  # pragma: no cover
    _SSL = ssl.create_default_context()

_last = [0.0]
_throttle = threading.Lock()


def _pace() -> None:
    """One global gap between requests, whichever thread is asking. SEC's cap
    is per client, not per connection, so the limiter has to be shared."""
    with _throttle:
        wait = MIN_INTERVAL - (time.monotonic() - _last[0])
        if wait > 0:
            time.sleep(wait)
        _last[0] = time.monotonic()


def get(url: str, agent: str, retries: int = 3) -> bytes:
    for attempt in range(retries):
        _pace()
        req = urllib.request.Request(url, headers={"User-Agent": agent, "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, context=_SSL, timeout=60) as resp:
                data = resp.read()
                if resp.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    data = gzip.decompress(data)
                return data
        except urllib.error.HTTPError as exc:
            if exc.code in (403, 429, 503) and attempt < retries - 1:
                time.sleep(2.0 * (attempt + 1))
                continue
            raise
    raise RuntimeError(f"unreachable: {url}")


def selected_splits() -> dict:
    """`--split=development` narrows every stage to that split's filings."""
    want = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--split=")), None)
    return {k: v for k, v in SPLITS.items() if want in (None, k)}


def cases() -> list[dict]:
    out = []
    for split, path in selected_splits().items():
        for line in path.open(encoding="utf-8"):
            row = json.loads(line)
            q = row["query"]
            m, k = SREF.search(q), CIK.search(q.split("##Instance document", 1)[-1])
            out.append({"split": split, "id": row["id"],
                        "stem": m.group(1) if m else None,
                        "cik": k.group(1).zfill(10) if k else None})
    return out


#: Forms that carry an XBRL instance. Anything else at the same reportDate
#: (NT 10-K, ARS, Form 5, proxy) is noise and is dropped before fetch.
XBRL_FORMS = {"10-K", "10-K/A", "10-KT", "10-KT/A", "10-Q", "10-Q/A", "10-QT", "10-QT/A",
              "20-F", "20-F/A", "40-F", "40-F/A", "N-CSR", "N-CSRS", "N-CSR/A", "10-K405"}
CACHE = HERE / ".edgar_cache"


def submissions(cik: str, agent: str) -> list[dict]:
    """Every submission page for one filer, cached on disk after the first read."""
    CACHE.mkdir(exist_ok=True)
    path = CACHE / f"CIK{cik}.json"
    if path.exists():
        return json.loads(path.read_text())
    data = json.loads(get(f"https://data.sec.gov/submissions/CIK{cik}.json", agent))
    pages = [data["filings"]["recent"]]
    for extra in data["filings"].get("files", []):
        pages.append(json.loads(get(f"https://data.sec.gov/submissions/{extra['name']}", agent)))
    out = [{"name": data.get("name"), "pages": pages}]
    path.write_text(json.dumps(out))
    return out


#: Preference among forms that could own a stem. The 10-K/10-Q family first
#: because that is what the cases audit; an 8-K filed the same day carries its
#: own cover-page XBRL under the *same* stem, so `<stem>.xsd` alone cannot tell
#: them apart and the order here has to.
FORM_RANK = {"10-K": 0, "10-Q": 0, "10-KT": 0, "10-QT": 0, "10-K405": 0,
             "10-K/A": 1, "10-Q/A": 1, "10-KT/A": 1, "10-QT/A": 1,
             "20-F": 2, "40-F": 2, "N-CSR": 2, "N-CSRS": 2, "20-F/A": 3, "40-F/A": 3, "N-CSR/A": 3}


def candidates(stem: str, pages: list[dict]) -> list[dict]:
    """Filings that could own this stem, best first.

    The stem's trailing YYYYMMDD is usually the period end, which is the
    submission's reportDate; some filers name it after the filing date instead
    (nika-20250513 is a 10-Q for the quarter to 2025-03-31, filed 13 May). Both
    are tried. Several filings can share a date — the original, an amendment,
    an 8-K with cover-page XBRL — so all of them are returned in FORM_RANK
    order and `fetch` keeps the first whose Archives listing has `<stem>.xsd`.

    When neither date matches anything (ggro-20261231 names a period that has
    not ended), every XBRL-bearing filing from the fifteen months before the
    stem date is offered as a fallback, nearest first, and flagged so the
    manifest shows the guess. Matching on the primary document's prefix alone
    found 238 of 693: printers name that file `eml_10k.htm`, not after the stem.
    """
    date = stem.rsplit("-", 1)[-1]
    iso = f"{date[:4]}-{date[4:6]}-{date[6:]}"
    stem_l = stem.lower()
    found, pool = [], []
    for page in pages:
        for j, form in enumerate(page["form"]):
            doc = page["primaryDocument"][j]
            row = {"form": form, "reportDate": page["reportDate"][j], "filingDate": page["filingDate"][j],
                   "accession": page["accessionNumber"][j].replace("-", ""), "primary": doc}
            prefix = doc.lower().startswith((stem_l + ".", stem_l + "_"))
            by_date = iso in (row["reportDate"], row["filingDate"]) and form in XBRL_FORMS
            if prefix or by_date:
                found.append((FORM_RANK.get(form, 9), 0 if prefix else 1, row["filingDate"], row))
            elif form in XBRL_FORMS and row["reportDate"] and row["reportDate"] < iso:
                pool.append(row)
    if found:
        found.sort(key=lambda t: t[:3])
        return [t[3] for t in found]
    lo = f"{int(date[:4]) - 1}-{date[4:6]}-{date[6:]}" if date[4:8] != "0229" else f"{int(date[:4]) - 1}-02-28"
    fallback = sorted((r for r in pool if r["reportDate"] >= lo), key=lambda r: r["reportDate"], reverse=True)
    for r in fallback:
        r["fallback"] = True
    return fallback


def stage_map(agent: str) -> int:
    rows = cases()
    missing = [r["id"] for r in rows if not (r["stem"] and r["cik"])]
    if missing:
        print(f"  {len(missing)} cases lack a CIK or stem and cannot be located: {missing[:5]}")
    keys = {(r["cik"], r["stem"]) for r in rows if r["stem"] and r["cik"]}
    by_cik: dict[str, set[str]] = {}
    for cik, stem in keys:
        by_cik.setdefault(cik, set()).add(stem)
    print(f"  {len(rows)} cases -> {len(keys)} filings, {len(by_cik)} filers")
    manifest: dict[str, dict] = {}
    none = multi = 0
    for i, (cik, stems) in enumerate(sorted(by_cik.items()), 1):
        subs = submissions(cik, agent)
        for stem in stems:
            cands = candidates(stem, subs[0]["pages"])
            manifest[f"{cik}-{stem}"] = {"cik": cik, "stem": stem, "name": subs[0]["name"], "candidates": cands}
            none += not cands
            multi += len(cands) > 1
        if i % 50 == 0:
            print(f"    ... {i}/{len(by_cik)} filers")
    MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    forms: dict[str, int] = {}
    for v in manifest.values():
        if v["candidates"]:
            f = v["candidates"][0]["form"]
            forms[f] = forms.get(f, 0) + 1
    print(f"  with candidates {len(manifest) - none} | without {none}")
    print(f"  preferred forms: {dict(sorted(forms.items(), key=lambda kv: -kv[1]))}")
    for v in manifest.values():
        if not v["candidates"]:
            print(f"    no candidate: {v['stem']}  {v['name']}  CIK {v['cik']}")
    print(f"  → {MANIFEST}")
    return 1 if none else 0


def fetch_one(key: str, f: dict, agent: str) -> str:
    """Download one filing's six files. Returns 'done', 'incomplete' or 'error'."""
    target = FILINGS / key
    if (target / "COMPLETE").exists():
        return "done"
    target.mkdir(parents=True, exist_ok=True)
    for marker in ("INCOMPLETE", "ERROR"):
        (target / marker).unlink(missing_ok=True)
    try:
        for cand in f["candidates"]:
            base = f"https://www.sec.gov/Archives/edgar/data/{int(f['cik'])}/{cand['accession']}/"
            names = [it["name"] for it in json.loads(get(base + "index.json", agent))["directory"]["item"]]
            if not any(n.lower() == f["stem"].lower() + ".xsd" for n in names):
                # Some accessions list only the wrapper files plus
                # `<accession>-xbrl.zip`; the schema and linkbases are inside the
                # zip and the extracted instance sits unlisted at
                # `<primary>_htm.xml` (verified: scnd-20250630, HTTP 200 on a
                # file index.json never named). Fall through to that path.
                zips = [n for n in names if n.endswith("-xbrl.zip")]
                if not zips:
                    continue
                import io, zipfile
                archive = zipfile.ZipFile(io.BytesIO(get(base + zips[0], agent)))
                members = {m.filename.rsplit("/", 1)[-1]: m for m in archive.infolist()}
                if f["stem"].lower() + ".xsd" not in {m.lower() for m in members}:
                    continue
                got = set()
                for name, member in members.items():
                    if name.lower().startswith(f["stem"].lower()) and name.endswith(SUFFIXES[:-1]):
                        (target / name).write_bytes(archive.read(member))
                        got.add(next(sfx for sfx in SUFFIXES if name.endswith(sfx)))
                primary_stem = cand["primary"].rsplit(".", 1)[0]
                for guess in (f"{primary_stem}_htm.xml", f"{f['stem']}_htm.xml"):
                    try:
                        (target / (f["stem"] + "_htm.xml")).write_bytes(get(base + guess, agent))
                        got.add("_htm.xml")
                        break
                    except urllib.error.HTTPError as exc:
                        if exc.code != 404:
                            raise
                lacking = [sfx for sfx in SUFFIXES if sfx not in got]
                if lacking:
                    (target / "INCOMPLETE").write_text("missing: " + " ".join(lacking) + "\nvia xbrl.zip; index: " + " ".join(names))
                    print(f"  {key}: still missing {lacking} after the xbrl.zip fallback")
                    return "incomplete"
                (target / "COMPLETE").write_text(json.dumps({**cand, "via": "xbrl.zip"}))
                return "done"
            # Schema and linkbases are named after the stem. The instance is
            # named after the *primary document* (`wddd10k24_htm.xml` beside
            # `wddd-20241231.xsd`), so it is found by suffix and saved under the
            # stem so the assembler's `*_htm.xml` glob and the practice layout
            # both hold.
            want = {n: n for n in names
                    if n.lower().startswith(f["stem"].lower()) and n.endswith(SUFFIXES[:-1])}
            instances = [n for n in names if n.endswith("_htm.xml")]
            primary_stem = cand["primary"].rsplit(".", 1)[0].lower()
            instances.sort(key=lambda n: (not n.lower().startswith(primary_stem),
                                          not n.lower().startswith(f["stem"].lower()), n))
            if instances:
                want[instances[0]] = f["stem"] + "_htm.xml"
            got = set()
            for remote, local in want.items():
                (target / local).write_bytes(get(base + remote, agent))
                got.add(next(sfx for sfx in SUFFIXES if local.endswith(sfx)))
            lacking = [sfx for sfx in SUFFIXES if sfx not in got]
            if lacking:
                (target / "INCOMPLETE").write_text("missing: " + " ".join(lacking) + "\nindex: " + " ".join(names))
                print(f"  {key}: missing {lacking}")
                return "incomplete"
            (target / "COMPLETE").write_text(json.dumps(cand))
            return "done"
        (target / "ERROR").write_text("no candidate accession lists <stem>.xsd")
        print(f"  {key}: none of {len(f['candidates'])} candidate accessions lists {f['stem']}.xsd")
        return "error"
    except Exception as exc:  # noqa: BLE001
        (target / "ERROR").write_text(str(exc))
        print(f"  {key}: {type(exc).__name__}: {str(exc)[:120]}")
        return "error"


def stage_fetch(agent: str, workers: int = 4) -> int:
    if "@" not in agent:
        sys.exit("fetch needs EDGAR_CONTACT=\"<name> <email>\": SEC Archives rejects requests without a contact in the User-Agent")
    manifest = json.loads(MANIFEST.read_text())
    wanted = {f"{r['cik']}-{r['stem']}" for r in cases() if r["cik"] and r["stem"]}
    todo = {k: f for k, f in sorted(manifest.items()) if f.get("candidates") and k in wanted}
    skipped = len(manifest) - len(todo)
    tally = {"done": 0, "incomplete": 0, "error": 0}
    started = time.monotonic()
    # Four workers share one 10-requests-per-second budget; the gain over one
    # worker is overlapping SEC's per-request latency with file transfer, not
    # more requests per second.
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(fetch_one, k, f, agent): k for k, f in todo.items()}
        for i, fut in enumerate(as_completed(futures), 1):
            tally[fut.result()] += 1
            if i % 25 == 0:
                rate = i / (time.monotonic() - started)
                print(f"    ... {i}/{len(todo)}  complete {tally['done']} incomplete {tally['incomplete']} error {tally['error']}"
                      f"  about {(len(todo) - i) / rate / 60:.0f} min left", flush=True)
    print(f"  complete {tally['done']} | incomplete {tally['incomplete']} | error {tally['error']} | skipped (no candidate) {skipped}")
    return 1 if tally["incomplete"] or tally["error"] else 0


def stage_rebuild() -> int:
    from . import xbrl as X
    from .query import LINKBASE_KEYS, _section_file, assemble, repair_truncated_linkbase
    manifest = json.loads(MANIFEST.read_text())
    src_override = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--source=")), None)
    out_override = next((a.split("=", 1)[1] for a in sys.argv if a.startswith("--out=")), None)
    for split, path in selected_splits().items():
        # --source picks which organizer release supplies the linkbases the hybrid
        # keeps; the 28 Sep 2026 republication changed them in some cases.
        if src_override:
            path = HERE / src_override
        out = HERE / (out_override or f"{split}_inputs_hybrid.jsonl")
        n = rebuilt = kept = 0
        grew = 0
        with out.open("w", encoding="utf-8") as fh:
            for line in path.open(encoding="utf-8"):
                row = json.loads(line); q = row["query"]; n += 1
                m, k = SREF.search(q), CIK.search(q.split("##Instance document", 1)[-1])
                key = f"{k.group(1).zfill(10)}-{m.group(1)}" if (m and k) else None
                fdir = FILINGS / key if key else None
                if not (fdir and (fdir / "COMPLETE").exists()):
                    fh.write(json.dumps(row, ensure_ascii=False) + "\n"); kept += 1
                    continue
                question = X.parse_question(q)
                period = (f"{question.start} to {question.end}" if question.start and question.end
                          else (question.instant or ""))
                released = X.split_sections(q)
                overrides = {kk: released[kk] for kk in LINKBASE_KEYS if released.get(kk)}
                for kk, suffix in (("definition", "_def.xml"), ("calculation", "_cal.xml"), ("presentation", "_pre.xml")):
                    if kk in overrides:
                        p = _section_file(fdir, suffix)
                        if p is not None:
                            fixed = repair_truncated_linkbase(overrides[kk], p.read_text(encoding="utf-8", errors="ignore"))
                            if fixed:
                                overrides[kk] = fixed
                full = assemble(question.concept, period, fdir, override_sections=overrides,
                                taxonomy_text=released.get("taxonomy", ""))
                grew += len(full) > len(q)
                fh.write(json.dumps({"id": row["id"], "query": full}, ensure_ascii=False) + "\n"); rebuilt += 1
        print(f"  {split}: {n} cases -> rebuilt {rebuilt} (longer than released: {grew}) | kept as released {kept} -> {out.name} ({out.stat().st_size / 1e6:.0f} MB)")
    return 0


def main() -> int:
    stage = sys.argv[1] if len(sys.argv) > 1 else "map"
    agent = os.environ.get("EDGAR_CONTACT", "finreason-task3-dqc (set EDGAR_CONTACT)")
    if stage == "map":
        return stage_map(agent)
    if stage == "fetch":
        return stage_fetch(agent)
    if stage == "rebuild":
        return stage_rebuild()
    sys.exit(f"unknown stage {stage!r}; expected map, fetch or rebuild")


if __name__ == "__main__":
    sys.exit(main())
