# Research scripts

Unmodified scripts behind the measurements reported in the paper. They were written for the
author's machine and still carry its paths (`/Users/xai/Desktop/FinReason/...`); they are kept
for transparency, not as a supported interface. The supported pipeline is the
`finreason_task3` package.

| Script | Measurement |
| --- | --- |
| `validate_0015.py`, `validate_0117.py`, `validate_0126.py` | each rule module against the practice references, with the rule label withheld; release-window and guard-variant sweeps |
| `crosscheck_0015_independent.py`, `crosscheck_0126_independent.py` | independent re-implementations (no shared parsing code) compared with the modules on practice, development and test |
| `audit_0126_variants.py` | alternative readings of DQC_US_0126 (duplicate elimination, addend counting, decimals) |
| `review_0117_*.py` | which DQC_US_0117 guard blocks each practice case the 2026 text misses; development sensitivity to the guards |
| `review2_sweep*.py` | the guard / factset-reading sweep over practice, development and test behind the generator model (element 10093 without its notes guard) |
| `DQC_US_0015.list`, `DQC_US_0117.list`, `DQC_IFRS_0126.list` | the documentation and workbook URLs the modules were written from (read by `scripts/fetch_dqc_sources.sh`) |
| `DQC_License.md` | the licence of the DQC material |

The practice inputs these scripts read are the FinMR cases with the complete instance
document spliced in from the filings (the organizers' practice release cuts every section at
32,767 characters); the two practice references the paper calls defective (DEV_000117 and
DEV_000273) are excluded from their "curated" scoring files.
