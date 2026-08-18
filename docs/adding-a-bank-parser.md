# Adding a bank parser

This is the most useful contribution you can make, and the codebase is arranged
specifically to make it cheap: **three files in one new directory, no changes
to shared code, and no test code to write.**

Because parsers are auto-discovered, you never edit a registry — so you can't
conflict with anyone else adding a different bank.

---

## What you need

- Your statement, downloaded from net banking (not a screenshot or a scan)
- A working dev setup — see [CONTRIBUTING.md](../CONTRIBUTING.md)
- About an hour, most of it spent staring at the file

---

## Step 1 — Look at the file

Before writing anything, find out what you actually have. Bank exports are
routinely mislabelled — HDFC's "Download as XLS" produces a **tab-delimited
text file** with an `.xls` extension, not a spreadsheet.

```bash
make inspect FILE=~/Downloads/statement.xls
# password-protected PDF? add the password:
make inspect FILE=~/Downloads/statement.pdf PASSWORD=name0203
```

This stores nothing — it reads the file, reports on it, and forgets it. Output
is **redacted by default** (account numbers, emails, phone numbers and PANs
masked), so it is safe to paste into an issue; names are not detectable, so
give it a glance first. `--raw` disables redaction for local viewing only.

It tells you three things:

- whether any existing parser recognises the file, and how confidently
- the extracted text layer — the layout your parser has to read
- if something does parse it, the rows produced, so you can check them against
  the statement itself

**"No parser recognised this file" is the useful case** — the layout printed
underneath is your specification.

If the text layer is empty, the PDF is a scan with no text in it. Those aren't
supported (no OCR); download the original from net banking rather than a
printed-and-scanned copy.

Note four things:

1. How many junk lines precede the transaction table
2. The **exact** header labels (`Withdrawal Amt.`, not `Withdrawal`)
3. The date format — `03/04/24`? `03-Apr-2024`?
4. Whether debits and credits are separate columns, or one column with a
   `Dr`/`Cr` suffix

---

## Step 2 — Create the directory

```
backend/apps/parsers/banks/<bank>/
├── __init__.py
├── parser.py
└── tests/
    ├── __init__.py
    ├── fixtures/<bank>_savings_2024_04.xls
    └── expected/<bank>_savings_2024_04.json    # generated, not hand-written
```

`<bank>` is a short slug — `hdfc`, `sbi`, `axis`. It must match the parser's
`bank_slug`; a test enforces that so the tree stays navigable.

---

## Step 3 — Write the parser

Two complete, working examples are in the tree, deliberately different in shape:

- **[`banks/hdfc/parser.py`](../backend/apps/parsers/banks/hdfc/parser.py)** —
  a delimited text export with separate withdrawal and deposit columns
- **[`banks/icici/parser.py`](../backend/apps/parsers/banks/icici/parser.py)** —
  a credit-card PDF with no ruling lines, parsed line-by-line, where the signs
  are inverted

Copy whichever is closer. The interface is small:

```python
class MyBankStatementParser(BaseParser):
    bank_slug = "mybank"
    display_name = "My Bank — Savings"
    statement_kind = "bank"          # or "credit_card"
    file_formats = ["xls", "csv"]

    @classmethod
    def can_parse(cls, file: ParsedFile) -> Confidence:
        text = file.head.lower()
        if "my bank" in text and "narration" in text:
            return Confidence.STRONG
        return Confidence.NONE

    def parse(self, file: ParsedFile) -> ParsedStatement:
        rows = read_delimited(file.text)
        header, body = rows_after_header(rows, ["date", "narration", "withdrawal"])
        ...
        return self.build_statement(transactions, period_start=..., period_end=...)
```

### Three rules that matter

**1. Negative means money leaving the account.** Always, regardless of how the
statement prints it. Card statements show purchases as positive and payments
with a `CR` suffix — flip that in the parser so nothing downstream needs to
know which kind of statement a transaction came from.

**2. Never clean up the description.** Store the narration exactly as printed.
The user needs to recognise their own transaction, and the categorisation rules
match on the raw string.

**3. Find columns by header name, not by position.** Banks add and reorder
columns. `find_header_row` / `rows_after_header` handle the junk above the
table, and matching is substring-based, so `"withdrawal"` finds
`"Withdrawal Amt."`. A parser that hardcodes "skip 20 lines, take column 4"
breaks the first time your bank tweaks its template.

### Don't write the fiddly parts yourself

`apps/parsers/utils/` already handles:

| Module | What it does |
| --- | --- |
| `amounts.py` | `1,20,450.00`, `(1,234.00)`, `1,234.00 Dr`, trailing minus, `₹`/`Rs.` prefixes, and merging separate debit/credit columns |
| `dates.py` | `03/04/24`, `03-Apr-2024`, `03 Apr 2024` and a dozen more — day-first, never guessed |
| `pdf.py` | Text and table extraction, plus password-protected PDFs |
| `tables.py` | Delimiter detection, locating the header under header junk, dropping separator rows |

**If you find yourself writing something another bank would also need, put it
in `utils/` instead.** That is what keeps the next parser cheap.

### Confidence, not booleans

`can_parse` returns a score. The dispatcher picks the highest, and if the top
two tie it asks the user which bank it is — mis-parsing a statement silently is
worse than failing to parse it.

| Return | When |
| --- | --- |
| `Confidence.CERTAIN` | An unambiguous marker no other issuer uses |
| `Confidence.STRONG` | Bank **and** statement type both identified |
| `Confidence.LIKELY` | Bank identified, type inferred |
| `Confidence.WEAK` | Right shape, no positive identification |
| `Confidence.NONE` | Not ours |

Keep it cheap — it runs for every parser on every upload.

---

## Step 4 — Add a fixture

### Prefer inventing one over cleaning one

For CSV and delimited formats, **retype the layout by hand with invented
data**. It tests the parser exactly as well and carries no risk of leaking
anything. That's how `banks/hdfc/tests/fixtures/` was built.

For PDFs, generate one — see
[`banks/icici/tests/make_fixture.py`](../backend/apps/parsers/banks/icici/tests/make_fixture.py),
which produces a byte-reproducible PDF with reportlab. Commit the generator
alongside the fixture so the next person can change it.

### If you must use a real statement

```bash
python scripts/anonymise_statement.py ~/Downloads/statement.xls --out fixture.xls --jitter
```

Then **read the output in full**. The tool handles the patterns we know about;
it cannot recognise your name, your employer, or a distinctive spending
pattern. It refuses to touch PDFs on purpose — a PDF hides personal data in its
metadata and text layer, and a half-clean is worse than no attempt.

Read [anonymising-statements.md](anonymising-statements.md) before you commit
anything.

### A committed fixture is permanent

Deleting the file in a later commit does **not** remove it from git history. If
you realise you've pushed real data, don't open a "remove file" PR — report it
privately per [SECURITY.md](../SECURITY.md) so the history can be purged.

---

## Step 5 — Generate the golden file and run the tests

```bash
make regenerate-goldens BANK=mybank
```

**Read the generated JSON before committing it.** A golden file records what
your parser currently does, not what it should do — regenerating without
reading is how a parsing bug becomes the expected behaviour. Check a few
transactions against the statement in front of you: right dates, right signs,
balances that actually add up.

```bash
make check
```

The shared harness picks your fixture up automatically and asserts that:

- detection routes it to **your** parser, not another bank's
- it parses to your golden file
- no transaction has a zero amount or an empty description
- every transaction falls inside the statement period
- `source_hint` exposes at most four digits of an account number
- the fixture contains no obvious personal data

You wrote none of those tests. That's the point.

---

## Step 6 — Open the PR

Update the supported-banks table in the [README](../README.md), then open the
PR. The template has a checklist for parser changes.

Say which bank and which statement type, and mention any layout quirk you had
to work around — that context is what the next person needs when the bank
changes its template.

---

## Troubleshooting

**"No parser recognised this file"** — `can_parse` returned `NONE`. Print
`file.head` and check you're matching text that's actually there; PDFs often
extract with different spacing than they display.

**Detection picks the wrong bank** — two parsers return the same confidence.
Tighten whichever is over-claiming; the `test_detected_parser_belongs_to_this_bank`
failure names both.

**"Could not find the transaction table"** — your `required` header fragments
don't match. They're substring-matched and case-insensitive, so pass the
shortest distinctive fragment: `"withdrawal"`, not `"Withdrawal Amt."`.

**Amounts are the wrong sign** — check whether the bank prints debits in a
separate column (`parse_signed_amount`) or with a `Dr` suffix (`parse_amount`
handles the suffix itself).

**Dates land in the wrong month** — the file is probably MM/DD. Pass an
explicit `formats=` tuple to `parse_date`; don't change the shared default,
which is day-first because Indian statements are.

Still stuck? Open a draft PR with what you have. A half-working parser plus a
fixture is much easier to help with than a description.
