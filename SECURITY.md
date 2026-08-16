# Security Policy

This project handles financial data. Two kinds of report matter here:
software vulnerabilities, and personal data accidentally committed to the repo.

## Reporting a vulnerability

**Do not open a public issue.** Use GitHub's
[private vulnerability reporting](../../security/advisories/new), or email
**varunjuneja7@gmail.com** with:

- what the issue is and how to reproduce it
- what an attacker could reach (another household's data? the host?)
- the version or commit you tested

You'll get an acknowledgement within 72 hours and an assessment within a week.
Please give us a reasonable window to ship a fix before disclosing publicly.

Especially interested in: anything that crosses the household boundary,
authentication or session handling flaws, and code execution via a malicious
statement file (parsers process untrusted input by definition).

## Personal data committed by mistake

If a real bank statement, account number or other personal data lands in the
repository — yours or someone else's — **report it privately, immediately**.
Do not open a PR deleting the file: the data stays in git history, and the PR
advertises exactly where to find it.

We will rewrite history to purge it and force-push. Contributors will need to
re-clone; that is a small price.

To avoid this: run every fixture through
[the anonymisation guide](docs/anonymising-statements.md) before committing.

## Scope

In scope: this codebase, its default configuration, and the deployment stack in
`deploy/`.

Out of scope: vulnerabilities in Django, PostgreSQL or other dependencies
(report those upstream); an instance a user has deliberately exposed to the
internet without TLS or with `DJANGO_DEBUG=True`.

## For self-hosters

- Set a unique `DJANGO_SECRET_KEY` before exposing the instance to any network.
- Run behind a reverse proxy with TLS. Keep `DJANGO_SECURE_COOKIES=True`.
- Anyone with an account on your instance is a member of your deployment —
  household scoping separates their data from yours, but do not treat the
  registration page as a public signup form unless you intend to.
- Back up your database. It is the only copy of your financial history.
