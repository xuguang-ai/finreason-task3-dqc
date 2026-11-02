#!/usr/bin/env bash
# Download the DQC rule sources, documentation and element workbooks that the modules were written
# from (XBRL US Data Quality Committee, github.com/DataQualityCommittee/dqc_us_rules, master branch).
# They are not redistributed here; see THIRD_PARTY_NOTICES.md.  Usage: scripts/fetch_dqc_sources.sh [outdir]
set -euo pipefail
OUT="${1:-dqc_sources}"; mkdir -p "$OUT"
RAW=https://raw.githubusercontent.com/DataQualityCommittee/dqc_us_rules/master
while read -r name url; do
  [ -z "$name" ] && continue
  curl -sSL "$url" -o "$OUT/$name" && echo "  $name"
done < <(cat "$(dirname "$0")/../research/DQC_US_0015.list" "$(dirname "$0")/../research/DQC_US_0117.list" "$(dirname "$0")/../research/DQC_IFRS_0126.list")
for y in 2024 2025 2026; do for r in 0015 0117 0126; do
  curl -sSL "$RAW/dqc_us_rules/source/us/$y/DQC_$r.xule" -o "$OUT/src_${y}_DQC_$r.xule" && echo "  src_${y}_DQC_$r.xule"
done; done
for f in lib/functions.xule us/2026/constant.xule us/2026/constant-us-gaap.xule us/2026/resources.xule us/2026/functions.xule; do
  n="lib_$(echo "$f" | sed 's#us/2026/#2026_#; s#lib/##')"; curl -sSL "$RAW/dqc_us_rules/source/$f" -o "$OUT/$n" && echo "  $n"
done
curl -sSL "$RAW/License.md" -o "$OUT/License.md"
echo "done -> $OUT"
