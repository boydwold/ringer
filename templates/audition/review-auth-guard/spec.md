# Review authentication guards
You are a security and correctness reviewer for `auth.py` and `handler.py`.

Write only `report.md`, with one bullet per defect. Each bullet must put a
relative `file.py:line` citation and a one-line explanation of the faulty
behaviour together on the same line. A short inclusive `file.py:start-end`
range is also allowed. Cite the statement responsible for the defect; one line
of tolerance is allowed. Cite at most eight distinct source lines in total
(range citations count every covered line). Do not list correct code as a
finding or cite it as background. Review behaviour against the contract below;
do not report style preferences or hypothetical violations of input assumptions.
Do not modify the Python files; do not create other files.


Contract: upstream code validates all argument types and required keys.
password_matches and recovery_code_matches each receive two equal-length bytes
values representing secret verifier material (derivation/storage is upstream).
They must return whether the values match without leaking matching-prefix length
through comparison timing. token_active receives a dict with integer expires_at
and an integer now on the same clock; a token is valid strictly before expires_at
and is invalid at or after that instant. Issuance, signatures and clock trust are
upstream responsibilities.

handle runs only after authentication and token validation. user has string name
and role fields; roles are "admin" or "member". settings is a plain dict with a
boolean enabled entry, and audit is a plain list. Any authenticated user may read
status. Only admins may enable or disable the service; other users must receive
PermissionError with settings and audit unchanged. Successful changes update
enabled, append (user name, action) to audit, and return {"ok": True}. Status
returns {"enabled": current boolean}. Unknown actions raise ValueError. Roles
and action names are public, non-secret strings. Concurrency is out of scope.
