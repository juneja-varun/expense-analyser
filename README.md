# Expense Analyser

**Self-hosted personal finance for India.** Upload your bank and credit-card
statements, get every transaction categorised automatically, and budget against
categories that nest three levels deep.

Built for Indian statement formats — the ones generic finance apps don't read.

> **Status: early development.** Statement parsing works and two banks are
> supported; categorisation and budgeting are next. Star the repo to follow
> along, or [add support for your bank](docs/adding-a-bank-parser.md) — it's
> three files and no changes to shared code.

---

## Why this exists

[Firefly III](https://www.firefly-iii.org/) and
[Actual Budget](https://actualbudget.org/) are excellent self-hosted finance
apps. Neither can read an HDFC savings statement or an ICICI credit-card PDF.

If you bank in India, you currently export to CSV by hand, wrestle with column
layouts that differ per bank, and re-categorise the same merchants every month.
This project does that part for you:

- **Statement parsing built for Indian banks** — bank and credit-card formats,
  including password-protected PDFs.
- **Categorisation that learns** — deterministic rules over merchant names and
  UPI VPAs. Recategorise once and it remembers. Works fully offline.
- **Three-level categories** — `Food & Dining → Eating Out → Weekend`, budgeted
  and reported at any level.
- **Your data stays yours** — runs on your own machine or server. No account,
  no cloud, no third party unless you explicitly opt in.

**Your bank isn't supported yet?** That's the whole point of the architecture —
adding one is three files and no changes to shared code.
See [docs/adding-a-bank-parser.md](docs/adding-a-bank-parser.md).

---

## Quick start (self-hosting)

```bash
git clone https://github.com/varunjuneja/expense-analyser.git
cd expense-analyser
cp .env.example .env          # set DJANGO_SECRET_KEY before exposing to a network
docker compose -f deploy/docker-compose.yml up
```

Open <http://localhost:8000> and register. The first account is yours; everything
lives in Postgres inside the stack.

## Quick start (developing)

No Docker needed. You need Python 3.11+, Node 20+, Poetry and a local Postgres.

```bash
git clone https://github.com/varunjuneja/expense-analyser.git
cd expense-analyser
make setup    # installs deps, creates the databases, runs migrations
make dev      # backend on :8000, frontend on :5173
```

Open <http://localhost:5173>. Both servers hot-reload.
Full guide: [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Supported banks

| Bank | Savings/current | Credit card | Formats |
| --- | --- | --- | --- |
| HDFC Bank | ✅ | — | `xls` (delimited export), `csv`, `txt` |
| ICICI Bank | ✅ | ✅ | `pdf` (incl. password-protected) |

Adding yours is the most useful contribution you can make, and the codebase is
arranged specifically to make it cheap. Start with
[docs/adding-a-bank-parser.md](docs/adding-a-bank-parser.md), or
[open a bank support request](../../issues/new?template=bank-support-request.yml)
if you'd rather someone else write it.

---

## How it works

```
Statement (PDF/XLS/CSV)
        │
        ▼
  Parser registry ──► bank-specific parser ──► canonical transactions
        │                                              │
        │                                              ▼
        │                                      dedupe (re-uploading an
        │                                      overlapping period is a no-op)
        │                                              │
        ▼                                              ▼
  Rules engine ──► category (3-level tree) ──► budgets and charts
```

The rules engine runs in this order, first match wins: your own rules → rules
learned from your past recategorisations → bundled community merchant patterns.
Everything is deterministic and offline.

An **optional** AI categoriser can label whatever the rules miss. It is off by
default, needs your own API key, and sends transaction descriptions to a third
party — see [docs/faq.md](docs/faq.md) before enabling it.

More detail: [docs/architecture.md](docs/architecture.md).

---

## Tech stack

Django 5 + Django REST Framework · PostgreSQL · React + TypeScript + Vite

---

## Contributing

Contributions are very welcome — especially bank parsers, but also bug reports,
docs and UI work.

- [CONTRIBUTING.md](CONTRIBUTING.md) — setup and workflow
- [docs/adding-a-bank-parser.md](docs/adding-a-bank-parser.md) — the most
  wanted contribution
- [Good first issues](../../issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22)

⚠️ **Never commit a real statement.** Test fixtures must be anonymised first —
[docs/anonymising-statements.md](docs/anonymising-statements.md) explains how,
and CI will reject fixtures that look like they contain personal data.

---

## Licence

[AGPL-3.0](LICENSE). Use it, modify it, self-host it freely. If you run a
modified version as a network service, you must publish your changes.
