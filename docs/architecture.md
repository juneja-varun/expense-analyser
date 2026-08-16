# Architecture

## The shape of the problem

Everything here follows from one constraint: **India has 100+ banks and card
issuers, each with its own statement layout, and those layouts change without
notice.** No individual maintainer can keep up with that. The project is
therefore built so that adding a bank is the cheapest possible contribution —
three files, no changes to shared code, no test code to write.

If a design decision made parsers harder to contribute in exchange for elegance
elsewhere, it was the wrong decision.

## Pipeline

```
Upload  ─►  Parser registry  ─►  Canonical transactions  ─►  Dedupe
                   │                                            │
          highest-confidence                                    ▼
           bank parser wins                              Rules engine
                                                                │
                                                                ▼
                                              Category (3-level tree) ─► Budgets, charts
```

## Components

### `apps/parsers` — the plugin system

The centrepiece. A parser takes a file and returns dataclasses; it never touches
the database, which keeps it trivially unit-testable and means a contributor
needs no Django knowledge to write one.

- `base.py` — `BaseParser`, `ParsedStatement`, `ParsedTransaction`
- `registry.py` — auto-discovers `banks/*/parser.py`. **No central list to
  edit**, so two people adding different banks never conflict.
- `utils/` — shared PDF/date/amount helpers. Most of a parser should be regex
  and configuration; anything a second bank would need belongs here.
- `banks/<bank>/` — one directory per bank, with its own fixtures and golden
  files.

Detection is by **confidence score**, not a boolean. The dispatcher picks the
highest scorer and falls back to asking the user which bank it is. Silently
mis-parsing a statement is worse than failing to parse it.

### `apps/statements` — orchestration and dedupe

Owns upload, parser dispatch, and persistence. Deduplication is a
`sha256(source, date, amount, normalised_description, reference)` unique per
household: re-uploading an overlapping period is a no-op, because users
routinely download overlapping date ranges.

### `apps/categories` — the tree

Three levels (`Food & Dining → Eating Out → Weekend`), modelled as a
self-referential FK with a validated `depth` and a denormalised `root`.

Deliberately *not* django-mptt or treebeard: the tree is small and fixed-depth,
so a materialised `root_id` makes "roll spend up to top-level categories" a
single indexed join, with no tree-rebuild step and one fewer dependency to
explain to a contributor.

### `apps/rules` — categorisation

Deterministic and offline. First match wins:

1. The user's own rules
2. Rules learned from their past recategorisations — this is what makes the app
   improve with use, with no AI involved
3. Bundled community merchant and UPI-VPA patterns
4. Uncategorised

### `apps/enrichment` — optional LLM

An `EnrichmentBackend` interface whose default is `NullBackend`. Off unless the
user supplies their own API key. Results are written back as rules, so the same
merchant is never queried twice and cost decays toward zero. The deterministic
path must always work with no network access.

### `apps/accounts` and `apps/common` — tenancy

`Household` is the tenancy boundary, not `User`, so shared family finances work
without duplicating records and one deployment can safely serve unrelated
people.

Every financial model inherits `HouseholdScopedModel`; every viewset serving one
extends `HouseholdScopedViewSet`, which raises if a subclass returns an unscoped
queryset. Scoping fails loudly in development rather than leaking quietly in
production.

## Decisions worth knowing

| Decision | Why |
| --- | --- |
| Postgres, not MongoDB | Financial data is relational and needs constraints, migrations and `Decimal`. The original prototype used Mongo; the schema work it forced was the reason for the rewrite. |
| Session auth, not JWT | The SPA is same-origin (Vite proxy in dev, whitenoise in production), so an httpOnly cookie is both simpler and safer than storing tokens in JS. |
| DRF + React, not a Django-template monolith | Chosen for the UX ceiling on charts and interactions, accepting the cost of two toolchains. The `backend/`/`frontend/` split keeps a parser contributor away from Node entirely. |
| AGPL-3.0 | Keeps self-hosted finance software open even when someone runs it as a service. |
| Docker for deploying, native for developing | A container build in the inner loop is the fastest way to lose a contributor's first evening. |
| Statement upload, not Account Aggregator | Not a preference — see [faq.md](faq.md). |

Longer-form decision records live in [`adr/`](adr/).
