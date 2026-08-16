<!--
Thanks for contributing. Keep this short — the checklist matters more than prose.
-->

## What this changes

<!-- And why. If it fixes a parsing bug, name the bank and the layout quirk. -->

Closes #

## Checklist

- [ ] `make check` passes locally (lint + tests)
- [ ] Behaviour changes have tests

### If this adds or changes a bank parser

- [ ] **Fixtures are anonymised** — no real names, account numbers, PANs, emails
      or phone numbers. See [docs/anonymising-statements.md](../docs/anonymising-statements.md)
- [ ] A golden `expected/*.json` accompanies each fixture
- [ ] Reusable logic went into `apps/parsers/utils/`, not the bank module
- [ ] README's supported-banks table is updated

> ⚠️ Committed fixtures are permanent — deleting a file later does **not** remove
> it from git history. If you have already pushed real data, do not open a
> follow-up commit to delete it; report it privately per [SECURITY.md](../SECURITY.md)
> so the history can be purged.
