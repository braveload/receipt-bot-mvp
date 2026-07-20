# Project Working Rules

These rules apply to every task in this repository.

## Ponytail gate

Before writing or changing code, answer these questions in order:

1. Is the feature necessary? If not, skip it (YAGNI).
2. Can the Python standard library do it? If so, use it.
3. Does FastAPI, Kakao OpenBuilder, Render, SQLite, or another native platform feature already do it? If so, use it.
4. Can an already-installed dependency do it? If so, reuse it.
5. Is a one-line implementation sufficient and still readable and testable? If so, use it.
6. Only then write the minimum viable code.

Do not interpret “one line” as permission to reduce readability, validation, security, or tests. Security-sensitive behavior such as webhook verification and signed report URLs must remain explicit and testable.

## Project-specific application

- Prefer `sqlite3`, `hmac`, `hashlib`, `secrets`, `datetime`, and `pathlib` before adding packages.
- Reuse FastAPI request validation and response primitives.
- Reuse Kakao OpenBuilder's secure-image plugin for receipt image collection.
- Reuse `httpx` for outbound HTTP and `openpyxl` for `.xlsx`; do not add equivalent clients or spreadsheet libraries.
- Keep optional OCR providers behind the existing extractor interface.
- Add a dependency only when its necessity and the rejected built-in/existing alternatives are documented.
- Keep changes scoped and run `pytest` plus the relevant demo before completion.
