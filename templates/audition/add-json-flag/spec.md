# Add JSON output
You are extending a tiny command-line utility. Update `wordcount.py` to accept
an optional `--json` flag before or after its one positional TEXT argument.
Deliver only `wordcount.py`; do not create other files. Use only the standard
library. The CLI reads TEXT from argv, not stdin or a filename.

Without --json, preserve exactly the current output:
lines: L\nwords: W\ncharacters: C\n
where L = len(TEXT.splitlines()), W = len(TEXT.split()), C = len(TEXT).
These are Python Unicode string operations; characters are not UTF-8 bytes.
An empty TEXT has all zero counts; a trailing newline does not add an extra
splitlines() record. Whitespace-only lines do count as lines.

With --json, stdout must contain only one JSON object with exactly the keys
"lines", "words", "characters" and integer values for those same counts.
JSON spacing, key order and a trailing newline are irrelevant. Both successful
modes must exit 0 with empty stderr. Retain argparse's help and invalid-argument
handling. Keep the script importable without parsing arguments at import time.
Example TEXT "hi there" yields lines 1, words 2, characters 8 in both modes.
