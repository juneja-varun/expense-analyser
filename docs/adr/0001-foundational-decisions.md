# ADR 0001 — Foundational decisions

**Status:** Accepted · **Date:** 2026-08-16

Recorded together because they were taken together, at project start, before any
feature code existed. Each is expensive to reverse, so the reasoning is written
down to save re-litigating it later.

---

## 1. The parser plugin system is the architecture, not a module

**Decision.** Organise the whole backend around making "add a bank" the cheapest
possible contribution: auto-discovered parsers, no central registry, shared
utilities for the fiddly parts, golden-file tests that need no test code.

**Why.** India has 100+ banks and card issuers, each with its own layout, and
those layouts change without notice. No single maintainer can keep up. The
project is only viable if strangers add their own banks, so contribution cost
for that one action outranks other design considerations.

**Consequence.** Where elegance elsewhere conflicts with parser contribution
cost, parser contribution cost wins.

---

## 2. PostgreSQL, not MongoDB

**Decision.** Postgres with the Django ORM. `Decimal` for money, never `float`.

**Why.** The earlier prototype (commit `a55a922`) used MongoDB with pandas and
was cleared before this rewrite. Financial data is relational and benefits from
foreign keys, unique constraints (deduplication depends on one), transactions
and migrations. Hierarchical categories, budgets-per-category-per-month and
household scoping are all natural relational shapes. Django's admin and
migrations also lower the barrier for contributors.

**Alternatives.** MongoDB — rejected; schema flexibility is not an asset when
the schema is the correctness guarantee. SQLite — rejected as the default;
excellent for single-user but weaker for concurrent household use, though it may
be worth offering later for trivial deployments.

---

## 3. DRF API + React SPA, not a server-rendered monolith

**Decision.** Django REST Framework backend and a React/TypeScript/Vite frontend
in one monorepo, split at `backend/` and `frontend/`.

**Why.** The product is chart- and interaction-heavy (category breakdowns,
budget progress, month-over-month trends), where a SPA has a materially higher
ceiling. A monolith with HTMX was the serious alternative and would have been
simpler.

**Consequence.** Two toolchains, accepted deliberately. Mitigated by the
directory split: a contributor fixing a parser regex never installs Node. Auth
is a same-origin session cookie (Vite proxies `/api` in development, whitenoise
serves the bundle in production), so there is no CORS configuration and no
token-in-JavaScript storage problem.

---

## 4. AGPL-3.0

**Decision.** GNU Affero General Public License v3.0.

**Why.** The value proposition is that your financial data stays yours. AGPL
keeps that true downstream: anyone may use, modify and self-host freely, but
running a *modified* version as a network service requires publishing the
changes. It is also what Firefly III uses, so it is well understood in this
space.

**Consequence.** Some companies will not adopt AGPL software. That is an
acceptable trade for a self-hosted personal finance app. The decision is
effectively irreversible once external contributors hold copyright in the code.

---

## 5. Households, not users, as the tenancy boundary

**Decision.** All financial data hangs off a `Household`. Users join households
through memberships.

**Why.** Family finances are shared, and duplicating records per user is both
wasteful and a source of drift. One deployment should also be able to serve
unrelated people safely.

**Consequence.** Every financial model carries a `household` FK from the first
commit — retrofitting would mean migrating every table. Enforced by
`HouseholdScopedModel` and `HouseholdScopedViewSet`, which raises rather than
returning an unscoped queryset, so mistakes fail loudly in development instead
of leaking quietly in production.

---

## 6. Rules-first categorisation, LLM strictly optional

**Decision.** A deterministic rules engine is the categoriser. Any LLM backend
is opt-in, off by default, and behind an interface whose default implementation
does nothing.

**Why.** Offline operation and privacy are core to the product. An app that
needs an API key to be useful is not a self-hosted app. Rules are also
debuggable, free and instant, and the app improves through use because every
manual recategorisation becomes a rule.

**Consequence.** LLM results are persisted as rules, so the same merchant is
never queried twice and cost decays toward zero. Enabling it sends transaction
descriptions to a third party — stated plainly in the FAQ.

---

## 7. Docker for deploying, native for developing

**Decision.** `deploy/docker-compose.yml` is the self-hosting artifact.
Contributors run Django and Vite directly against a local Postgres via
`make dev`.

**Why.** A container build in the inner loop costs rebuild latency and awkward
debugging, and is a common way to lose a contributor's first evening. Both paths
are verified in CI, and `django-environ` reads `DATABASE_URL` so local, CI and
Docker differ only by environment variable — no branching on "am I in a
container".
