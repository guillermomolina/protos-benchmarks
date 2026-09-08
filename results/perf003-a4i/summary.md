# PERF003-A4i decision

- Control: GraphTooBig=40, 50681:150026:150000
- Preparation boundary only: GraphTooBig=40, 51502:150053:150000
- Control median: 9950715696 ns
- Boundary median: 5752923868 ns
- Boundary/control median ratio: 0.5781
- Compilability decision: **NOT_SUFFICIENT**
- Reason: preparation boundary alone did not eliminate all deterministic GraphTooBig bailouts
- Next: close this boundary-localization line; no further PE microexperiments
