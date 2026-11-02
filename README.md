# finreason-task3-dqc

Exact reproduction of the XBRL US Data Quality Committee (DQC) rule findings behind each
case of **FinReason Cup 2026 Task 3 (Financial Audit Verification)**, IEEE BigData Cup 2026.
Team `xai`: 100% on the development set, 97.50% on the hidden test set (third of 23 teams,
two cases behind the joint first place), with no language model in the loop.

The accompanying Working Notes explain why: every reference answer is one
finding of DQC_US_0015, DQC_US_0117 or DQC_US_0126, produced by a deterministic rule
engine, so the task reduces to (1) restoring the complete filing the engine saw,
(2) re-implementing the rule text exactly and (3) choosing among several findings when the
question does not say which one is meant. The remaining errors sit entirely in (3), where
the dataset's choice is effectively random.

## Layout

```
finreason_task3/            the pipeline (standard library only)
  xbrl.py                   instance / linkbase parsing, query sections, question parsing
  query.py                  hybrid query assembly: complete instance + the organizers' linkbases
  edgar_fetch.py            map cases to EDGAR accessions, fetch the XBRL files, rebuild queries
  dqc/dqc_0015.py           negative values on non-negative elements (release-aware element list)
  dqc/dqc_0117.py           financial-statement dimensional cross check (elements 9574 and 10093)
  dqc/dqc_0126.py           calculation check with non-dimensional data
  dqc/dqc_0015_items.json   the DQC_US_0015 element list by release (derived from the DQC workbook)
  integrate.py              run the three modules on a case, normalise findings to (extracted, calculated)
  predict.py                answer selection (the policy of the final test submission) and output files
  format_thousands.py       submission number style (thousands separators)
scripts/                    fetch the DQC sources; rebuild the element list from the workbook
probe/                      exact inference over development-leaderboard scores (diagnostic, see paper)
research/                   unmodified measurement scripts behind the paper (author-machine paths)
submissions/                the file submitted to the test phase
data/                       inputs, filings and outputs live here (not distributed; see data/README.md)
```

## Reproducing the test submission

Python 3.12 or newer; no third-party package is needed for the pipeline.

```bash
export FINREASON_DATA=data
# 1. the organizers' inputs (see data/README.md) -> data/test_inputs.jsonl
# 2. the filings: data/edgar_manifest.json already maps every case to its EDGAR accession
export EDGAR_CONTACT="Your Name your@email"        # required by SEC's fair-access policy
python -m finreason_task3.edgar_fetch fetch --split=test
# 3. queries with the complete instance document
python -m finreason_task3.edgar_fetch rebuild --split=test --out=test_inputs_hybrid.jsonl
# 4. predictions
python -m finreason_task3.predict --input data/test_inputs_hybrid.jsonl --out data/predictions_test
```

`data/predictions_test_commas.jsonl` is then identical, case by case, to
`submissions/predictions_test_v4_commas.jsonl` (checked on 2 November 2026). Step 4 takes
about 90 seconds for 680 cases; step 2 downloads 693 filings (a few GB) at the SEC's
rate limit. To start from scratch instead of the shipped manifest, run
`python -m finreason_task3.edgar_fetch map` first.

`data/predictions_test_disputed.json` lists the 24 cases where a choice had to be made:
21 DQC_US_0015 ties, two three-way ties among 10093 findings and one case where two rules
fire. Everything else has exactly one finding.

## Decision rules

Documented at the top of `finreason_task3/predict.py`: one finding is the answer; several
DQC_US_0015 findings are resolved by the value closer to zero when there are two distinct
values and by multiplicity then most-negative value otherwise; several DQC_US_0117
findings by document order of the total fact; no finding at all by element 10093 evaluated
without its notes guard (an empirical property of the dataset generator, confirmed on every
such development case); two rules on one fact by the DQC_US_0015 pair.

## Using the rule modules directly

```python
from finreason_task3 import integrate as I
from finreason_task3.dqc import dqc_0015, dqc_0117, dqc_0126

query = ...                                   # one case's query text (hybrid or released)
fdir = I.filing_dir(query, "data/filings")    # the filing's directory, or None
I.official_findings(query, fdir)              # [(rule, extracted, calculated), ...]
dqc_0015.findings_0015(query, filing_dir=fdir, include_rejected=True)   # every fact, with reasons
dqc_0117.findings_0117(query, fdir, dqc_0117.FAITHFUL, all_alignments=True)
dqc_0126.findings_0126(query, filing_dir=fdir)
```

Each module's docstring maps its code to the lines of the 2026 XULE source it implements
and records the readings that practice and development data support.

## Compliance

The pipeline reads the filing itself (from the case and from SEC EDGAR) and the published
rule definitions. It never consults a service that publishes DQC findings for a filing and
never runs Arelle, XULE or the DQC plug-in; no language model is used. See
`THIRD_PARTY_NOTICES.md` for the licences of the DQC material and the data.

## Citation

Xuguang Ai. *The Auditor Is a Rule Engine: Reproducing XBRL Data Quality Checks Exactly for
FinReason Cup 2026 Task 3.* Working Notes, FinReason Cup 2026 (IEEE BigData Cup), 2026.

## Licence

MIT (`LICENSE`) for the code in this repository; third-party material as described in
`THIRD_PARTY_NOTICES.md`.
