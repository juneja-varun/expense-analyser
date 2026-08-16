# FAQ

## Why not use India's Account Aggregator framework?

This comes up often, and the answer is regulatory rather than technical.

The AA framework moves financial data between a **Financial Information
Provider** (your bank) and a **Financial Information User** (an app), brokered
by an RBI-licensed **Account Aggregator** acting as consent manager.

To receive data, an app must be a registered FIU. That requires being a
regulated financial entity — an RBI/SEBI/IRDAI/PFRDA-regulated institution —
and holding a commercial agreement with a licensed AA.

A self-hosted open-source app cannot satisfy that. There is no FIU registration
for "software a person runs on their own laptop", and no way to ship credentials
in a public repository that would let every user's instance act as one. Even a
hosted version would require becoming a regulated financial entity first.

**Statement upload is not a workaround for lacking AA access — for this class of
software it is the only lawful route.** It also happens to preserve the property
that matters most here: your financial data never leaves your machine.

If you are building a *regulated commercial* product, AA is likely the right
path, and this project is not the codebase to start from.

## Is my financial data sent anywhere?

No, with one opt-in exception.

By default everything — statements, transactions, categories, budgets — stays in
your own Postgres. There is no telemetry, no analytics and no external call.

The exception is the **optional AI categoriser**. It is disabled unless you set
`ENRICHMENT_BACKEND` and provide your own API key. When enabled, it sends
transaction *descriptions* (merchant strings such as
`UPI/SWIGGY/123456/PAYMENT`) to the provider you configured, to label the
transactions your rules didn't match. It does not send account numbers,
balances, or your identity.

If that trade isn't one you want, leave it off. The rules engine works fully
offline and gets better as you use it — every manual recategorisation becomes a
rule.

## Will it work with my bank?

Check the supported-banks table in the [README](../README.md). If yours isn't
there, [request it](../../issues/new?template=bank-support-request.yml) or
[add it](adding-a-bank-parser.md) — it's designed to be a small contribution.

## Can my family and I share one instance?

Yes. Data is scoped to a **household**, not a user, so several people can share
one deployment and see the same finances. Separate households on the same
instance cannot see each other's data.

Multi-household switching exists in the schema but has no UI yet.

## Can I use it outside India?

Nothing prevents it — the category tree, budgets and rules are generic, and the
currency is configurable. But the parsers are the point of the project and they
target Indian formats. Elsewhere you would be doing manual CSV imports, and
[Firefly III](https://www.firefly-iii.org/) or
[Actual Budget](https://actualbudget.org/) will serve you better today.

The parser interface is not India-specific. If someone wants to add parsers for
another country's banks, that is welcome.

## Why AGPL and not MIT?

So that self-hosted finance software stays open. Anyone can use, modify and
self-host this freely. The obligation only applies to running a *modified*
version as a network service for others — then those changes must be published
too. It keeps improvements in the commons rather than in a closed fork.

## Is it safe to expose on the internet?

Only with care. Put it behind a reverse proxy with TLS, set a unique
`DJANGO_SECRET_KEY`, and turn on `DJANGO_SECURE_COOKIES` and
`DJANGO_SECURE_SSL_REDIRECT`. Remember that registration is open by default, so
anyone who can reach the page can create an account on your instance.

See [SECURITY.md](../SECURITY.md).
