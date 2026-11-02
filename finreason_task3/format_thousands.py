#!/usr/bin/env python3
"""Rewrite a predictions file in the reference answers' number style.

    python3 format_thousands.py <in.jsonl> <out.jsonl>

Practice gold writes integers of magnitude >= 1000 with thousands separators
("-2,881,000") in about 85-90% of cases, and decimals and small integers plain.
The official LLM judge (gpt-5-mini, minimal reasoning) compares the two strings
as text in its prompt, so matching the dominant style removes a conversion step
from most comparisons.  Values are not changed: every output parses to the same
Decimal as its input, which this script asserts.
"""
import json
import sys
from decimal import Decimal, InvalidOperation


def style(v: str) -> str:
    s = str(v).strip()
    try:
        d = Decimal(s.replace(",", ""))
    except InvalidOperation:
        return s
    if "." in s or "e" in s.lower() or abs(d) < 1000:
        return s.replace(",", "")
    return f"{int(d):,}"


def main(src: str, dst: str) -> int:
    n = changed = 0
    with open(src) as fh, open(dst, "w") as out:
        for line in fh:
            r = json.loads(line)
            for k in ("extracted_value", "calculated_value"):
                new = style(r[k])
                assert Decimal(new.replace(",", "")) == Decimal(str(r[k]).replace(",", "")), (r["id"], k, r[k], new)
                changed += new != r[k]
                r[k] = new
            out.write(json.dumps(r) + "\n")
            n += 1
    print(f"{n} rows, {changed} values restyled -> {dst}")
    return 0


if __name__ == "__main__":
    sys.exit(main(*sys.argv[1:3]))
