# Implement CSV summaries
You are implementing a small data utility. Implement `summarize(csv_text)` in
`summary.py`; `sample.csv` is an example. Deliver only `summary.py`; do not
create other files or change sample.csv. Use Python 3.11+ standard library only.

Input is a string containing valid comma-separated CSV, with standard double
quote escaping and a header of unique, nonempty column names. Rows have exactly
the header width. Preserve header names verbatim. Ignore completely blank lines
(as csv.reader does); quoted commas and newlines are data. Other malformed CSV
and non-string inputs are outside this task's scope.

Return exactly {"row_count": int, "numeric": dict, "non_numeric": list}.
row_count counts data records, excluding header and blank lines. A column is
numeric only if there is at least one data row and EVERY cell, after stripping
whitespace, converts with float() to a finite number. Empty cells, NaN, infinity,
or any non-number make the entire column non-numeric. For each numeric column,
map its name to {"min": number, "max": number, "mean": number}, using all rows.
Round each statistic with Python round(value, 2); mean is the arithmetic mean.
Test data uses moderate magnitudes (no overflow). Numeric values may be ints or
floats. List non-numeric column names in header order. Dictionary order does not
matter. Do not mutate global state or perform file I/O.

Empty input or only blank lines returns
{"row_count": 0, "numeric": {}, "non_numeric": []}.
A header with no data rows returns row_count 0, numeric {}, and ALL header names
in non_numeric. For "name,n\na,2\nb,4\n", return
{"row_count": 2, "numeric": {"n": {"min": 2, "max": 4, "mean": 3}},
 "non_numeric": ["name"]}.
