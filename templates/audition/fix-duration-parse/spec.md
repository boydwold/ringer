# Repair duration parsing
You are maintaining a duration utility. Correct `parse_duration(text)` in
`duration.py`. Deliver only `duration.py`; do not create other files.

Accept one or more components, each an ASCII nonnegative integer followed by
one lowercase unit: h, m or s. Units may occur at most once and must be in that
order, but any unit may be omitted. No spaces, signs, decimals, uppercase,
trailing characters or newlines are allowed. Leading zeros and values greater
than 59 are allowed. Return integer seconds (h = 3600, m = 60, s = 1).
Examples: "1h30m" -> 5400, "45s" -> 45, "2h" -> 7200, "90m" -> 5400,
"1h0m5s" -> 3605, "2h5s" -> 7205, "0s" -> 0.
Empty strings, non-string inputs and malformed strings must raise ValueError.
Do not perform I/O or add dependencies.
