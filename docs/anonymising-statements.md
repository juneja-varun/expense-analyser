# Anonymising statements

**Read this before committing any test fixture.**

A bank statement identifies you completely: full name, account number, address,
and a month-by-month record of where you were and what you bought. Committing
one to a public repository publishes all of it — and `git` keeps it forever.
Deleting the file in a later commit does not remove it; anyone can recover it
from history.

So: every fixture in this repository must be anonymised **before** its first
commit.

---

## What has to go

| Field | Replace with |
| --- | --- |
| Account holder name | `TEST USER` |
| Address | `1 Test Street, Test City 000000` |
| Account number | `XXXXXXXX1234` (keep only the last four, if the parser needs them) |
| Card number | `XXXX XXXX XXXX 1234` |
| Customer ID / CRN | `000000000` |
| PAN | `ABCDE1234F` |
| Aadhaar | Remove entirely — never include one, masked or not |
| IFSC | `BANK0000000` |
| Email | `test@example.com` |
| Phone | `9000000000` |
| UPI VPA | `testuser@examplebank` |
| Counterparty names | Invented names — `RAHUL K`, `ASHA S` |
| Amounts | Round or jitter them (see below) |

**Keep** the layout, column order, header junk, date formats, number
formatting, `Dr`/`Cr` markers, and the merchant *patterns* the parser relies on.
Those are the only reason the fixture exists.

### About amounts

Amounts are more identifying than people expect — a rent figure plus a salary
credit narrows things down fast. Round them to something obviously synthetic
(`12,500.00`, `1,00,000.00`) or shift every value by a constant factor.

Do keep the *shape*: if the bank writes `1,20,450.00` in lakh grouping, your
replacement should too. That formatting is exactly what the parser is being
tested against.

### About merchant names

Real merchant strings are what the categorisation rules match on, so a handful
of genuine ones (`SWIGGY`, `IRCTC`, `AMAZON PAY INDIA`) are valuable and are
not personal data. What must go is anything tying a merchant to *you* — the
UPI VPA, order IDs, terminal IDs, and the merchant's own reference numbers.

---

## The tool

```bash
python scripts/anonymise_statement.py path/to/statement.pdf --out fixture.pdf
```

It scrubs the common fields, preserves layout, and jitters amounts. It is a
starting point, not an authority: **open the result and read it** before
committing. Statement layouts vary too much for any tool to be exhaustive.

For CSV and XLS it is usually quicker to edit by hand in a spreadsheet.

---

## Check your work

```bash
python scripts/check_fixtures_anonymised.py
```

This is what CI runs. It flags PAN-shaped strings, Aadhaar-shaped numbers,
emails, Indian mobile numbers, unmasked long digit runs and IFSC codes.

It is a **backstop, not a guarantee**. It cannot recognise a real person's name,
a home address, or a distinctive spending pattern. A clean run means nothing
obvious slipped through — it does not mean the fixture is safe. You have to read
it yourself.

For PDFs, also check the text layer and metadata, not just the visible page:

```bash
pdftotext fixture.pdf - | less           # what is actually extractable
pdfinfo fixture.pdf                       # Author/Title often carry names
exiftool -all= fixture.pdf                # strip metadata entirely
```

---

## A safer alternative: synthesise instead of anonymise

You do not need a real statement at all. If you can reproduce the layout —
header rows, column order, date and amount formats — by hand, do that. A
hand-built fixture with invented data carries zero risk and tests the parser
just as well.

This is the recommended path when the statement is a CSV or XLS, where layout
is easy to recreate.

---

## If you have already committed real data

**Do not push a commit that deletes the file.** The data remains in history, and
the deletion commit points straight at it.

Report it privately per [SECURITY.md](../SECURITY.md). We will purge it from
history and force-push. Contributors will need to re-clone — a small price, and
much better than the alternative.
