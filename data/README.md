# Data directory

Nothing here is distributed except this file and `edgar_manifest.json`. Set
`FINREASON_DATA` to this directory (the default is `data/` relative to the working
directory) and populate it as follows.

| Path | Content | Source |
| --- | --- | --- |
| `development_inputs.jsonl`, `test_inputs.jsonl` | the organizers' ranked-phase inputs (680 cases each; revision of 28 September 2026) | https://huggingface.co/datasets/YanAdjeNole/FinReason-Task3 |
| `edgar_manifest.json` | case → filing → EDGAR accession map (693 filings); written by `edgar_fetch.py map`, shipped here so that `fetch` uses the accessions of the paper | this repository |
| `filings/<cik10>-<stem>/` | the six XBRL files of each filing (`.xsd`, `_pre`, `_cal`, `_def`, `_lab`, `<stem>_htm.xml`) plus a `COMPLETE` marker | `edgar_fetch.py fetch` |
| `<split>_inputs_hybrid.jsonl` | the organizers' queries with the complete instance document restored (about 1.6 GB per split) | `edgar_fetch.py rebuild` |
| `predictions_<split>*.jsonl` | the pipeline's output | `python -m finreason_task3.predict` |
| `filings_practice/` (optional) | complete filings behind the 332 FinMR practice cases, one directory per filing, named `*-<stem>` | the research scripts expect them; see `research/README.md` |

Two filings resolve to the wrong accession under the generic rule of `map` (a file stem
reused across a company's reports); the manifest here already carries the corrected
accessions for `0001489874-ggro-20261231` (10-Q for 2026-03-31) and
`0001744494-adn-20231231` (10-K for FY2024).
