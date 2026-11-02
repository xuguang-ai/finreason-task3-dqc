# Third-party material

## XBRL US Data Quality Committee rules

The modules under `finreason_task3/dqc/` re-implement rules DQC_US_0015, DQC_US_0117 and
DQC_US_0126 from the published XULE sources, documentation and element workbooks of the
Data Quality Committee (https://github.com/DataQualityCommittee/dqc_us_rules). The element
list `finreason_task3/dqc/dqc_0015_items.json` is derived from
`docs/DQC_US_0015/DQC_0015_ListOfElements.xlsx` of that repository and is a derivative
work that assists in the implementation of the rules. The rule sources themselves are not
redistributed here; `scripts/fetch_dqc_sources.sh` downloads them. The DQC licence
(`research/DQC_License.md`, reproduced below as required) applies to that material:

> All published final recommendations of the Data Quality Committee are copyrighted as
> follows, whether the copyright is carried explicitly in the material (such as .md files,
> program code and some .xml files), or not in the file (such as .csv files, which have no
> means of embedding copyright and legal wording):
>
> Copyright © 2015-present, American Institute of CPAs (AICPA)
> Copyright © 2015-present, Calcbench, Inc.
> Copyright © 2015-present, Toppan Merrill LLC
> Copyright © 2015-present, Workiva Inc.
> Copyright © 2015-present, XBRL US, Inc.
>
> This document and translations of it may be copied and furnished to others, and
> derivative works that comment on or otherwise explain it or assist in its implementation
> may be prepared, copied, published and distributed, in whole or in part, without
> restriction of any kind, provided that the above copyright notice and this paragraph are
> included on all such copies and derivative works.

See `research/DQC_License.md` for the complete text, including its patent notice.

## FinReason Cup 2026 Task 3 data

The practice cases (TheFinAI/FinMR) and the development and test inputs
(YanAdjeNole/FinReason-Task3, CC BY 4.0) are published by the competition organizers on
Hugging Face and are not included in this repository. `data/README.md` explains where to put
them. The reference answers of the development and test phases remain with the organizers.

## SEC EDGAR filings

The complete XBRL filings that the pipeline restores are public records of the U.S.
Securities and Exchange Commission, downloaded from EDGAR by `finreason_task3/edgar_fetch.py`
under the SEC's fair-access policy (identify yourself in `EDGAR_CONTACT`; at most ten
requests per second). They are not included here; `data/edgar_manifest.json` lists the
accession numbers used.
