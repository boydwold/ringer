# Review inventory
You are a correctness reviewer for `inventory.py` and `storage.py`.

Write only `report.md`, with one bullet per defect. Each bullet must put a
relative `file.py:line` citation and a one-line explanation of the faulty
behaviour together on the same line. A short inclusive `file.py:start-end`
range is also allowed. Cite the statement responsible for the defect; one line
of tolerance is allowed. Cite at most eight distinct source lines in total
(range citations count every covered line). Do not list correct code as a
finding or cite it as background. Review behaviour against the contract below;
do not report style preferences or hypothetical violations of input assumptions.
Do not modify the Python files; do not create other files.


Contract: initial is a dict of string SKUs to nonnegative built-in integers.
new_inventory copies the stock mapping; when history is omitted each inventory
has its own empty history. An explicitly supplied history list is intentionally
shared with its caller. reserve receives an existing SKU and must reject
nonpositive or non-integer quantities with ValueError. It must also reject
quantities exceeding stock with ValueError, without changing stock or history.
Successful reservations decrement stock and append (sku, quantity) to history.
unit_labels accepts a nonnegative integer and returns exactly quantity labels,
numbered unit-1 through unit-quantity (zero yields an empty list).

Persistence uses caller-owned text streams, which may fail. save_inventory writes
JSON and must propagate write failures to its caller. No rollback, stream closing
or atomic file replacement is required. load_inventory returns decoded JSON;
on any ordinary exception it appends the exception type name to the caller's
plain list audit and re-raises the original exception. Decoded data validation is
out of scope. Streams and audit lists are otherwise used according to these APIs.
