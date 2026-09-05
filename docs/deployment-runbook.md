# Deployment Runbook

Single-host, Docker Compose production deployment of OpenAgent. This is the
deliberate architecture (see [`ARCHITECTURE.md` §10](agentos-v2/ARCHITECTURE.md)):
one host, no Kubernetes, no billing, static RBAC. Do not treat those as bugs.

Two supported modes:

- **VPN-only / internal** — no TLS profile, reach the stack over a private
  network (VPN, SSH tunnel, or a cloud security-group that only allows your
  own IPs). Simpler, no domain needed.
- **Internet-facing** — `tls` Compose profile, Caddy terminates real HTTPS
  via Let's Encrypt. Requires ports 80/443 reachable from the internet and a
  resolvable domain (sslip.io works fine — see below).

This runbook covers the internet-facing mode end to end; the VPN-only mode is
the same steps minus section 4 (TLS) and with the firewall in section 6 doing
more of the isolation work.

---

## 1. Prerequisites

- A host with Docker + Docker Compose v2, and a public IPv4 address if using
  the `tls` profile.
- Ports 80 and 443 open inbound on that host (cloud security group + any
  host firewall) if using `tls`. Otherwise, keep 80/443/3000/8000 restricted
  to your VPN/known IPs — see section 6.
- Real secrets for every `:?`-required variable in `docker-compose.yml`
  (Postgres, ZITADEL, JWT, MinIO/S3, Redis, Langfuse, crawler token). None
  of these have safe defaults; the compose file refuses to start without
  them.
- A ZITADEL OAuth2 application already configured (or configure it as part
  of first boot — the `identity` profile bootstraps a self-hosted ZITADEL
  instance for you if you don't have an external one).

## 2. Getting a domain when you only have a bare IP

If you don't own a domain yet, use [sslip.io](https://sslip.io): any subdomain
of the form `<anything>.<IP>.sslip.io` resolves via public DNS straight to
`<IP>`, with no registration or DNS records to manage. It behaves exactly
like a real domain from Let's Encrypt's point of view (the HTTP-01 challenge
just needs the name to resolve to a host that answers on port 80), so Caddy's
automatic HTTPS works against it unmodified.

Example, for a host at `203.0.113.10`:

```env
OPENAGENT_APP_DOMAIN=app.203.0.113.10.sslip.io
OPENAGENT_API_DOMAIN=api.203.0.113.10.sslip.io
OPENAGENT_AUTH_DOMAIN=auth.203.0.113.10.sslip.io
ZITADEL_DOMAIN=auth.203.0.113.10.sslip.io
```

When you later buy a real domain, just point `OPENAGENT_APP_DOMAIN` /
`OPENAGENT_API_DOMAIN` / `OPENAGENT_AUTH_DOMAIN` / `ZITADEL_DOMAIN` at it
instead — nothing else changes.

## 3. Required environment variables checklist (production)

Copy `.env.example` to `.env` on the deploy host and fill in every one of
these. Anything not listed here already has a safe default.

**Runtime / secrets validator** (see `app/config.py`'s
`validate_production_secrets` — refuses to boot if these are wrong):
- `OPENAGENT_RUNTIME=production` — without this, the insecure-default
  checks below are silently skipped. This is the single most important line
  in the whole checklist; double-check it's actually set on the runner, not
  just in a local `.env` you forgot to sync.
- `OPENAGENT_JWT_SECRET_KEY` — random, ≥32 characters, not the dev default.
- `OPENAGENT_COOKIE_SECURE=true`.
- `OPENAGENT_S3_ACCESS_KEY` / `OPENAGENT_S3_SECRET_KEY` (via
  `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD`) — not `minioadmin`.

**Identity (ZITADEL)**:
- `OPENAGENT_AUTH_PROVIDER=zitadel`.
- `ZITADEL_MASTERKEY` — exactly 32 characters.
- `ZITADEL_POSTGRES_PASSWORD`, `ZITADEL_FIRSTINSTANCE_ORG_HUMAN_PASSWORD`.
- `ZITADEL_DOMAIN` — your real domain or an sslip.io name (section 2).
- `ZITADEL_EXTERNALSECURE=true` when using the `tls` profile (Caddy
  terminates TLS in front of ZITADEL; ZITADEL itself still runs with
  `--tlsMode disabled` since Caddy handles the certificate — this only
  controls whether ZITADEL *tells clients* to use `https://` URLs). Leave
  `false` only in the VPN-only/no-TLS mode.
- `OPENAGENT_ZITADEL_ISSUER_URL`, `OPENAGENT_ZITADEL_REDIRECT_URI`,
  `OPENAGENT_ZITADEL_POST_LOGOUT_REDIRECT_URI` — must use your real
  domain/scheme (`https://auth.<domain>/...`), not the `127.0.0.1.sslip.io`
  defaults, once you're off localhost.
- `OPENAGENT_ZITADEL_PROJECT_ID`, `OPENAGENT_ZITADEL_CLIENT_ID`,
  `OPENAGENT_ZITADEL_CLIENT_SECRET` — from the ZITADEL console after first
  boot (chicken-and-egg: bring the stack up once with the `identity` profile
  to bootstrap ZITADEL, create the OAuth app in its console, then set these
  and restart `api`/`worker`/`frontend`).
- `OPENAGENT_PLATFORM_ADMIN_EMAILS` — your real admin email(s), not the
  `zitadel-admin@localhost` placeholder.

**Data plane**:
- `OPENAGENT_POSTGRES_PASSWORD`, `OPENAGENT_DB_URL` (or point at an external
  managed Postgres instead of the bundled `postgres` service).
- `OPENAGENT_REDIS_PASSWORD` — new in this hardening pass; required, no
  default. The bundled `redis` service now runs with `--requirepass`.
- `MINIO_ROOT_USER` / `MINIO_ROOT_PASSWORD` — not the `minioadmin` default.
- `CRAWLER_API_TOKEN` — random, ≥32 characters.

**TLS (only when using `--profile tls`)**:
- `OPENAGENT_APP_DOMAIN`, `OPENAGENT_API_DOMAIN`, `OPENAGENT_AUTH_DOMAIN` —
  see section 2. Each must resolve to this host's public IP.
- `NEXT_PUBLIC_API_BASE_URL=https://<OPENAGENT_API_DOMAIN>`.
- `OPENAGENT_ZITADEL_ISSUER_URL=https://<OPENAGENT_AUTH_DOMAIN>` and the
  redirect URIs above updated to match.

**Optional but recommended**: Langfuse observability vars
(`LANGFUSE_*`) and OTel vars if you want tracing; these have their own
`:?`-required secrets in `docker-compose.yml` if the corresponding services
are started (they're in the default profile, not profile-gated, so they
always need real values regardless of TLS/identity choices).

## 4. TLS via Caddy

The `tls` Compose profile adds a `caddy` service that:
- Owns host ports 80/443 (443/tcp and 443/udp for HTTP/3).
- Automatically requests and renews Let's Encrypt certificates for
  `OPENAGENT_APP_DOMAIN`, `OPENAGENT_API_DOMAIN`, `OPENAGENT_AUTH_DOMAIN` per
  the `Caddyfile` at the repo root.
- Reverse-proxies each domain to `frontend:3000`, `api:8000`, and
  `zitadel-proxy:80` respectively, over the internal Compose network.

`zitadel-proxy` no longer needs to publish host port 80 directly once Caddy
is in front of it — it's still reachable by Caddy via the Compose network by
service name. Its host port mapping now defaults to `${ZITADEL_PROXY_HOST_PORT:-80}`
so you can either leave it unset and simply not run `zitadel-proxy` without
Caddy in front, or point it at a different, non-conflicting port if you need
to reach ZITADEL directly during debugging.

**What was NOT verified in this environment**: actual Let's Encrypt
certificate issuance. That requires a real, internet-reachable host with a
domain that resolves to it — neither is available in this sandboxed
development environment. What *was* verified: `docker compose config`
resolves and validates the full compose file (including the `caddy` service
and all three profiles together) with no syntax or variable-interpolation
errors. Confirm real cert issuance on the actual deploy host by tailing
`docker compose logs caddy` after first boot — a successful run logs
`certificate obtained successfully`.

## 5. Deploy commands

Internet-facing (TLS + identity):

```bash
docker compose --env-file .env --profile identity --profile tls up -d --build --remove-orphans
```

VPN-only / internal (no TLS):

```bash
docker compose --env-file .env --profile identity up -d --build --remove-orphans
```

Add `--profile observability` to either command if you want
Prometheus/Grafana/Loki/OTel collector.

The CD pipeline (`.github/workflows/deploy.yml`) runs the `identity`-profile
command automatically on push to `deploy/dev`. To also enable `tls` there,
set the repository variable `DEPLOY_COMPOSE_PROFILES=tls` (space-separated
if you need more than one, e.g. `tls observability`) — the workflow reads it
and appends the corresponding `--profile` flags. Leave it unset to keep
today's HTTP-only CD behavior.

## 6. Firewall guidance

Regardless of mode, the following must be enforced at the host/cloud
firewall level — Compose's `127.0.0.1`-only port bindings (see below) are a
second line of defense, not a substitute for this:

- **Never** expose Postgres (5433), Redis (6379), Qdrant (6333), or MinIO
  (9000/9001) to the internet. As of this hardening pass, their Compose
  host-port mappings are bound to `127.0.0.1` only, so even without a
  firewall they are not reachable from another machine — but keep a real
  firewall rule too in case something rebinds them (e.g. a future compose
  override) or you deploy without this exact compose file.
- **VPN-only mode**: also restrict ports 80, 3000, 8000 to your VPN/known IP
  ranges — nothing here provides TLS, so it must never be exposed to the
  general internet.
- **TLS mode**: only 80 (ACME challenge + redirect) and 443 need to be open
  to the internet. Everything else (3000, 8000, ZITADEL's internal port,
  etc.) should stay closed at the firewall even though the containers bind
  them — defense in depth in case a future change reintroduces a public
  binding by accident.

## 7. Health-check verification

After `docker compose up`, confirm:

```bash
curl -fsS http://127.0.0.1:8000/healthz      # liveness, no dependency checks
curl -fsS http://127.0.0.1:8000/readyz       # checks DB + Redis
curl -fsS http://127.0.0.1:3000/             # frontend responds
docker compose ps                            # every service "healthy" or "running"
```

In TLS mode, also confirm from outside the host (or via `curl --resolve` if
DNS hasn't propagated yet):

```bash
curl -fsS https://<OPENAGENT_API_DOMAIN>/healthz
curl -fsS https://<OPENAGENT_APP_DOMAIN>/
```

A 200 from both, over HTTPS with a valid certificate, confirms Caddy's ACME
issuance succeeded end to end.

## 8. Rollback procedure

The CD pipeline never runs `down -v`, so named volumes (Postgres data,
Qdrant vectors, MinIO objects, ZITADEL's own Postgres) always survive a
redeploy. To roll back a bad deploy:

```bash
# Revert deploy/dev to the last known-good commit, then either:
git push origin <known-good-sha>:deploy/dev --force-with-lease   # re-triggers the CD workflow
# or, directly on the runner:
git -C /path/to/repo checkout <known-good-sha>
docker compose --env-file .env --profile identity [--profile tls] up -d --build --remove-orphans
```

Because volumes persist across redeploys, a rollback to a prior commit does
not lose data — it only reverts application code. If the bad deploy also
ran a destructive migration, restoring from the most recent
`scripts/backup_postgres.ps1` backup is the correct recovery path, not a
code rollback alone.

## 9. Known, deliberate architectural limitations

These are documented design decisions
([`ARCHITECTURE.md` §10](agentos-v2/ARCHITECTURE.md)), not gaps to fix as
part of a deploy:

- **Single host, no Kubernetes.** No failover, no rolling deploys across
  multiple machines. If the host goes down, the whole stack goes down. The
  system is stateless-by-design so a future K8s migration doesn't require
  code changes, but no Helm chart exists today.
- **No dynamic ABAC/policy engine.** RBAC is a static role→permission
  matrix (`owner`/`admin`/`developer`/`viewer`). Sufficient at this scale;
  revisit only if a real need for per-resource dynamic policy emerges.
- **No microVM sandboxing.** `run_shell`/tool sandboxing uses hardened
  Docker containers via a locked-down `docker-socket-proxy` (no raw socket
  mount), which narrows but does not eliminate the blast radius of a
  container-escape RCE. A fully isolated sandbox-runner API is the tracked
  follow-up if untrusted-multi-tenant code execution becomes a real
  requirement.
- **No billing/subscription logic.** The `Organization` model has a `plan`
  field reserved for this, but no billing engine is implemented.
- **Secrets live in a single `.env` file** on the deploy host (referenced by
  the `DEPLOY_ENV_FILE` repo variable), not a secrets manager (Vault/SOPS).
  Documented as out of scope for v1; treat the deploy host's disk access
  control as the actual secret boundary until that changes.
