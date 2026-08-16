# Contributing

Thanks for considering it. The most valuable contribution to this project is
**support for a bank we can't parse yet** — that's what decides whether the app
is useful to anyone outside its author.

Every contribution is welcome though: bug reports, docs, UI work, tests.

---

## Setting up

You need **Python 3.11+**, **Node 20+**, **Poetry**, and **PostgreSQL running
locally**. You do not need Docker — that's only how self-hosters deploy.

```bash
git clone https://github.com/varunjuneja/expense-analyser.git
cd expense-analyser
make setup
make dev
```

`make setup` copies `.env.example` to `.env`, installs both dependency sets,
creates `expense_analyser` and `expense_analyser_test`, and runs migrations.
`make dev` starts Django on `:8000` and Vite on `:5173`; open
**<http://localhost:5173>** and register an account.

If Postgres isn't running: `brew services start postgresql@14` (macOS) or
`sudo systemctl start postgresql` (Linux).

Run `make help` to see every target.

### Before you open a PR

```bash
make check     # lint + tests, the same things CI runs
```

---

## Adding support for a bank

This is the contribution path the codebase is designed around. **You write three
files and change no shared code** — parsers are auto-discovered, so there is no
registry to edit and no merge conflict with anyone else adding a different bank.

```
backend/apps/parsers/banks/<bank>/
├── parser.py                                   # your parser
└── tests/
    ├── fixtures/<bank>_savings_2024.pdf        # an ANONYMISED statement
    └── expected/<bank>_savings_2024.json       # what it should parse to
```

The shared test harness picks these up automatically — you write no test code.
Full walkthrough with a worked example:
**[docs/adding-a-bank-parser.md](docs/adding-a-bank-parser.md)**.

Most of a parser is a few regexes plus configuration; the fiddly parts (PDF
password handling, Indian date formats, lakh-style number grouping, `Dr`/`Cr`
suffixes) already live in `backend/apps/parsers/utils/`. If you find yourself
writing something that another bank would also need, put it there instead.

### ⚠️ Never commit a real statement

Bank statements contain your name, account number, address, and complete
spending history. Once committed, that is in the git history permanently —
deleting the file later does not remove it.

**Anonymise every fixture before committing it.** We ship a tool:

```bash
python scripts/anonymise_statement.py path/to/statement.pdf --out fixture.pdf
```

Read [docs/anonymising-statements.md](docs/anonymising-statements.md) first. CI
scans fixtures for things that look like PANs, Aadhaar numbers, emails and phone
numbers, and fails the build — but that check is a backstop, not a guarantee.
You are the real safeguard.

If you realise you've committed real data, don't push a "remove file" commit —
tell us privately via [SECURITY.md](SECURITY.md) so we can purge the history.

---

## Project layout

```
backend/
├── config/settings/       # base / local / production / test
└── apps/
    ├── accounts/          # users, households (the tenancy boundary)
    ├── common/            # shared model bases, household scoping
    ├── parsers/           # ★ bank plugin system
    ├── statements/        # upload, parse orchestration, dedupe
    ├── transactions/      # canonical transaction model
    ├── categories/        # 3-level category tree
    ├── rules/             # deterministic categorisation
    ├── budgets/           # monthly budgets
    └── insights/          # aggregations for charts
frontend/src/              # React + TypeScript
docs/                      # architecture, guides, decision records
```

### Conventions worth knowing

- **Money is `Decimal`, never `float`.** `DecimalField(max_digits=14, decimal_places=2)`.
- **Financial models inherit `HouseholdScopedModel`.** The `household` FK is the
  tenancy boundary on a shared instance. Serve them from `HouseholdScopedViewSet`,
  which refuses to return an unscoped queryset.
- **Parsers never touch the database.** They take a file and return
  `ParsedStatement` dataclasses; persistence is the `statements` app's job. This
  keeps them trivially unit-testable.
- **Descriptions are stored raw.** Normalise for matching, but keep the original
  — users need to recognise their own transactions.

---

## Pull requests

- Branch off `main`, one logical change per PR.
- Tests for behaviour changes; a new bank parser needs its fixture and golden file.
- Run `make check` before pushing.
- Describe *why*, not just what. If you're fixing a parsing bug, say which bank
  and which statement layout — that context is what future maintainers need.

Small PRs get reviewed faster. If you're planning something large, open an issue
first so we can agree on the approach before you write it.

---

## Reporting bugs

Include your bank and statement type if it's a parsing issue, plus what you
expected versus what happened. **Do not attach a real statement to an issue** —
anonymise it first, or describe the layout in words.

## Code of conduct

By participating you agree to the [Code of Conduct](CODE_OF_CONDUCT.md).
