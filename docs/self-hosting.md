# Self-hosting

Two ways to run it. If you just want to *use* the app, use Docker. If you want
to change the code, see [CONTRIBUTING.md](../CONTRIBUTING.md) instead — the
development setup runs natively and doesn't need Docker at all.

---

## Docker (recommended)

```bash
git clone https://github.com/varunjuneja/expense-analyser.git
cd expense-analyser
cp .env.example .env
```

Set a real secret key in `.env` before going any further:

```bash
python3 -c "import secrets; print('DJANGO_SECRET_KEY=' + secrets.token_urlsafe(64))"
```

Then:

```bash
docker compose -f deploy/docker-compose.yml up -d
```

Open <http://localhost:8000> and register. The first account is yours.

The stack is two containers: Postgres, and the app (Django + Gunicorn serving
both the API and the compiled frontend from one origin). Migrations run
automatically on start.

### Useful commands

```bash
docker compose -f deploy/docker-compose.yml logs -f       # follow logs
docker compose -f deploy/docker-compose.yml down          # stop
docker compose -f deploy/docker-compose.yml pull && \
  docker compose -f deploy/docker-compose.yml up -d --build   # upgrade
docker compose -f deploy/docker-compose.yml exec app \
  python manage.py createsuperuser                        # admin at /admin/
```

---

## Configuration

All of it lives in `.env`.

| Variable | Default | Notes |
| --- | --- | --- |
| `DJANGO_SECRET_KEY` | — | **Required.** Change it before exposing the instance. |
| `DJANGO_ALLOWED_HOSTS` | `localhost,127.0.0.1` | Add your domain. |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | `http://localhost:8000` | Must include the scheme. |
| `APP_PORT` | `8000` | Host port to publish. |
| `POSTGRES_USER` / `_PASSWORD` / `_DB` | `expense` / `expense` / `expense_analyser` | Change the password for anything internet-facing. |
| `DJANGO_TIME_ZONE` | `Asia/Kolkata` | |
| `DEFAULT_CURRENCY` | `INR` | |
| `DJANGO_SECURE_COOKIES` | `False` | Set `True` once you have TLS. |
| `DJANGO_SECURE_SSL_REDIRECT` | `False` | Set `True` once you have TLS. |

---

## Putting it on a real domain

The app does not terminate TLS. Run a reverse proxy in front of it — Caddy,
nginx or Traefik — and point it at `localhost:8000`.

With Caddy, a complete config is two lines:

```caddyfile
finance.example.com {
    reverse_proxy localhost:8000
}
```

Then update `.env` and restart:

```bash
DJANGO_ALLOWED_HOSTS=finance.example.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://finance.example.com
DJANGO_SECURE_COOKIES=True
DJANGO_SECURE_SSL_REDIRECT=True
```

> **Registration is open by default.** Anyone who can reach the page can create
> an account on your instance. Household scoping keeps their data separate from
> yours, but if you don't want that, keep the instance on a private network or
> VPN.

---

## Backups

The database holds your entire financial history and is the only copy.

```bash
# Back up
docker compose -f deploy/docker-compose.yml exec -T db \
  pg_dump -U expense expense_analyser | gzip > backup-$(date +%F).sql.gz

# Restore
gunzip -c backup-2026-01-15.sql.gz | \
  docker compose -f deploy/docker-compose.yml exec -T db psql -U expense expense_analyser
```

Automate it, and test a restore at least once — an untested backup is a guess.

---

## Troubleshooting

**`DJANGO_SECRET_KEY` error on start** — it isn't set in `.env`. Generate one
with the command above.

**CSRF failures when logging in** — `DJANGO_CSRF_TRUSTED_ORIGINS` must include
the scheme and exactly match the URL in your browser
(`https://finance.example.com`, not `finance.example.com`).

**Cannot log in over plain HTTP** — `DJANGO_SECURE_COOKIES=True` requires HTTPS.
Either set up TLS or set it back to `False`.

**Database connection failures on first boot** — the app waits for Postgres to
become healthy, so this usually means the `db` container failed. Check
`docker compose -f deploy/docker-compose.yml logs db`.
