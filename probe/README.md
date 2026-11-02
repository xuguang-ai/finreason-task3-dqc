# Development-leaderboard diagnostic

`solver.py` is the exact-inference tool of the paper's section "Diagnostic Use of the
Development Leaderboard": every scored development upload assigns each open case one of its
candidate answers, the rule-judge count of the upload is a linear constraint on the hidden
references, and dynamic programming over the candidate assignments gives the posterior.

It needs `probe/ledger.json` (a list of `[name, file, correct_count]` entries for the
scored uploads), the uploaded prediction files under `<FINREASON_DATA>/probe/`, and the
development hybrid queries. The ledger and the files are not distributed, because together
they determine the references of 26 development cases, which remain the organizers' data.
