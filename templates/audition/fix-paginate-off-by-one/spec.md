# Repair pagination
You are maintaining a small Python utility. Correct `paginate(items, page, size)`
in `paginate.py`. Deliver only `paginate.py`; do not create other files.

`items` is a Python list. `page` and `size` must each be a positive built-in int;
booleans, other types, zero and negative values must raise ValueError, even when
items is empty. Pages are 1-based: page 1 starts at index 0, and page 2 starts
at index size. Return a new list with at most size elements in original order.
The last page can be partial; any page beyond the end returns []. Empty items
returns [] for valid arguments. Do not mutate items. No I/O or dependencies.
Example: paginate([10, 20, 30, 40, 50], 2, 3) returns [40, 50].
