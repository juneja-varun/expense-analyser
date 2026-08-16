# Adding a bank parser

> **Status: the parser system lands in the next phase.** This page describes the
> interface being built so you can see the shape of the contribution. Once
> `apps/parsers` is in place this becomes a full walkthrough with a worked
> example. Want to be notified? Comment on the parser-system tracking issue.
>
> In the meantime, the most useful thing you can do is
> [file a bank support request](../../issues/new?template=bank-support-request.yml)
> describing your statement's layout.

---

## The idea

Adding a bank is **three files in one new directory**. You change no shared
code, so you never conflict with anyone else adding a different bank, and you
write no test code — a shared harness discovers your fixtures automatically.

```
backend/apps/parsers/banks/<bank>/
├── parser.py
└── tests/
    ├── fixtures/<bank>_savings_2024.pdf      # anonymised statement
    └── expected/<bank>_savings_2024.json     # what it should parse to
```

Parsers are auto-discovered from that directory. There is no registry to edit.

## The interface

A parser takes a file and returns dataclasses. It never touches the database —
persistence, deduplication and categorisation happen elsewhere, so you only need
to think about reading the file.

```python
class HDFCSavingsParser(BaseParser):
    bank_slug = "hdfc"
    display_name = "HDFC Bank — Savings"
    statement_kind = "bank"
    file_formats = ["xls", "csv"]

    @classmethod
    def can_parse(cls, file: ParsedFile) -> Confidence:
        """How confident are we that this file is ours?

        Returns a score rather than a boolean: the dispatcher picks the highest
        scorer, and falls back to asking the user when nothing is confident.
        Mis-parsing a statement silently is worse than not parsing it.
        """

    def parse(self, file: ParsedFile) -> ParsedStatement:
        """Return the transactions. Raise ParseError with a useful message."""
```

`ParsedTransaction` carries `txn_date`, `value_date`, `description` (raw and
untouched), a signed `Decimal` `amount` (negative for money out), `balance`,
`reference`, and the original row in `raw` for debugging.

## What you should not have to write

The fiddly parts are shared, in `apps/parsers/utils/`:

- **`pdf.py`** — text and table extraction, and password-protected PDFs
  (including the date-of-birth style passwords Indian issuers use)
- **`dates.py`** — `03/04/24`, `03-Apr-2024`, `03 Apr 2024`, and the rest
- **`amounts.py`** — lakh-style grouping (`1,20,450.00`), `Dr`/`Cr` suffixes,
  trailing minus, parenthesised negatives
- **`tables.py`** — locating the real table under a pile of header junk

**If you find yourself writing something a second bank would also need, put it
in `utils/` rather than the bank module.** That is what keeps the next parser
cheap to write.

## Testing

Drop an anonymised statement in `tests/fixtures/` and its expected output in
`tests/expected/`. A shared test walks the registry and asserts every fixture
round-trips to its golden JSON — you write no test code.

To regenerate a golden file after an intentional change:

```bash
make regenerate-goldens BANK=<bank>     # review the diff before committing
```

## ⚠️ Anonymise your fixtures first

A real statement carries your name, account number, address and complete
spending history, and once committed it is in git history permanently.

Read **[anonymising-statements.md](anonymising-statements.md)** before you
commit anything, and run the checker:

```bash
python scripts/check_fixtures_anonymised.py
```

CI runs the same check, but it is a backstop that cannot recognise a real
person's name. You are the actual safeguard.

Safest of all: if your statement is a CSV or XLS, **retype the layout by hand
with invented data** rather than anonymising a real one. It tests the parser
just as well and carries no risk.
