# Keycloak Stale-User Cleanup

A scheduled job that disables users inactive for 120+ days in a Keycloak
realm, packaged to run on Kubernetes as a CronJob.

## Quick start

```bash
cp .env.example .env
make up            # Keycloak + Postgres, realm `acme` imported, login data seeded
make grant-roles    # grants the service account the Admin API roles it needs

python3 -m venv .venv && source .venv/bin/activate
pip install -e .
python -m cleaner.main               # dry-run (default) — logs candidates, changes nothing
DRY_RUN=false python -m cleaner.main # actually disables stale users
```

Expected dry-run output against the seeded data: `alice`, `bob`, `carol`,
`dave` flagged (120+ days inactive), `break-glass` skipped despite being the
oldest (excluded), everyone else kept.

## 1. Approach chosen, rejected alternatives, reasoning

**Chosen:** an external Python script (`src/cleaner/`) that authenticates to
Keycloak via the OAuth2 **client_credentials** grant (the seeded
`user-cleanup-service` service account) and calls the Admin REST API
directly — list users, check staleness, disable the stale ones.

**Rejected: a Java Keycloak SPI.** A scheduled-task SPI runs in-process and
needs no separate service account, but it ships coupled to a specific
Keycloak version, requires a JVM/Maven toolchain, and is harder to test or
scale independently of Keycloak itself. For a periodic batch job that only
needs read/write access to the Admin API, an external tool is the simpler,
more portable choice 

**Rejected: `LOGIN` events as the staleness signal.** The realm also carries
a backdated `LOGIN` event per user, which would work equally well and is
closer to how an unmodified production Keycloak tracks activity. I used the
seeded `lastLogin` user attribute instead — it's a single field read instead
of a paginated, retention-limited events query, and the assignment seeds it
specifically so login-tracking isn't the thing being tested. In production
I'd expect neither of these and would use a real signal (see point 5).

**Rejected: hard delete.** The Admin API supports both. I disable
(`enabled: false`) instead of deleting, because it's reversible and leaves
the user record in place as its own audit trail — deletion is a one-way
door that I'd want to be a separate, deliberate policy decision, not the
default action of a nightly job.

## 2. How this deploys on Kubernetes

See [`deploy/`](deploy/) — a Helm chart, one release per realm:

- **CronJob** — runs `python -m cleaner.main` on a schedule (default daily
  at 03:00), `concurrencyPolicy: Forbid` so overlapping runs can't race,
  bounded job history and `backoffLimit`.
- **ConfigMap** — non-secret per-realm config (URL, realm name, client ID,
  inactivity threshold, dry-run flag, exclusions).
- **Secret** — the Keycloak client secret. See point 3 for how it's
  supplied.
- **ServiceAccount** — dedicated, not `default`, with
  `automountServiceAccountToken: false`.
- **No Role/RoleBinding.** The suggested chart shape includes one, but this
  job never calls the Kubernetes API — only Keycloak's Admin REST API over
  HTTP, authenticated via the mounted Secret. Binding a Role to it would be
  an unused grant, not a safety rail, so I left it out and I'm noting that
  choice here instead.
- **ArgoCD sync-wave** annotation on the CronJob (`values.argo.syncWave`),
  bumpable so it lands after Keycloak itself is up and roles are granted.

```bash
helm lint ./deploy --set keycloak.clientSecret=dummy
helm template acme-cleanup ./deploy --set keycloak.clientSecret=dummy
```

## 3. Per-realm config and safety rails

Config lives in the chart's `values.yaml`, one values file per realm,
rendered into the ConfigMap/Secret above. Safety rails:

- **Exclusions** (`EXCLUSIONS`, default `admin,break-glass`) — usernames
  skipped unconditionally regardless of age. Verified against the seeded
  `break-glass` user (320 days inactive, the oldest in the realm) — it's
  excluded, not disabled.
- **Dry-run** (`DRY_RUN`, default `true`) — logs exactly what would happen
  without calling the disable endpoint. Must be explicitly set to `false`
  to take real action.
- **Audit trail** — every decision (`skip` / `would_disable` / `disable`)
  is logged as one logfmt-style (`key=value`) line to stdout, plus a
  summary line per run with total/disabled/excluded/kept counts. No extra
  infra (DB, PVC) — Kubernetes captures stdout natively, and a real
  deployment would ship these to whatever log aggregation already exists.

## 4. Extending to many realms

One chart, parameterized by `.Values.realm`. Every resource name is derived
from it (`{{ .Values.realm }}-cleanup-*`), so a second realm is a second
`helm install` release with its own values file and its own Keycloak
client/secret — not a code or template change:

```bash
helm install beta-cleanup ./deploy --set realm=beta -f values-beta.yaml
```

Verified directly: `helm template ... --set realm=beta` renames every
resource to `beta-cleanup-*` with no other changes. What's *not* built
(deliberately, per the assignment's own scope): a single job iterating
multiple realms, dynamic realm discovery, or a controller managing
releases — the seam is the parameterization, not a multi-tenant runtime.

## 5. One thing I'd change in production

I'd split this into two stages instead of one: **disable** at 120 days
inactive (as now), then a separate, slower, independently-scheduled job
that **hard-deletes** accounts that have stayed disabled past a further
retention window (e.g. another 90 days), with its own explicit approval
gate before it's allowed to run destructively. Coupling disable-now with
delete-later means a single bad threshold or a transient staleness signal
never causes irreversible data loss in one run — hard deletion becomes a
deliberate second decision made from an audit trail that's already proven
itself over the retention window, not a same-run side effect.

## 6. AI usage
I used Claude Code throughout. Before any code was written, we worked
through the open decisions together (Python vs. SPI, `lastLogin` vs. events,
disable vs. delete, Helm vs. manifests, secret handling) and logged the
reasoning — I didn't let it silently pick an approach. It then implemented
`config.py`, `keycloak_client.py`, `main.py`, and the Helm chart in small,
independently-tested steps, and ran each one live against the seeded realm
(token fetch, pagination, disable/re-enable, dry-run vs. real run) rather
than asserting it worked. I accepted the `httpx`-based client and the
logfmt audit format as proposed. I pushed back twice: I rejected using the
`python-keycloak` wrapper library it suggested, since raw `httpx` keeps the
OAuth2 grant and Admin API calls visible in code I wrote rather than hidden
in a dependency which matters given "OAuth2 fluency" is explicitly
graded. I also had it drop the `rbac.yaml` the suggested chart shape calls
for, once we established the job never touches the Kubernetes API, a
bound Role would have been an unjustified grant, not a safety rail.
