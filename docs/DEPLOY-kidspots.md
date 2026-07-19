# Deploy checklist — kidspots.store (single GCP VM, PostGIS in a container)

Concrete, copy-pasteable steps to put this repo live at the apex **https://kidspots.store**
on one Compute Engine VM. Postgres/PostGIS runs **in a container** (no Cloud SQL). The generic
guide is `docs/DEPLOY.md`; this file is the kidspots.store-specific run sheet.

**First deploy defaults:** Stripe stays on the in-memory **FakeGateway** (leave the three
`JUGGLE_STRIPE_*` blank — no real charges). Email is stubbed, so the `party_planner` flag stays
**OFF**. Serving is **apex-only** (no `www`).

---

## 1. Create the VM (Sydney — nearest GCP region to Perth; there is no Perth region)

```bash
gcloud compute instances create kidspots \
  --machine-type=e2-small \
  --image-family=ubuntu-2404-lts --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB \
  --tags=http-server,https-server \
  --zone=australia-southeast1-b
```

`e2-small` (2 GB) is the practical minimum — the web image runs `vue-tsc` at build time and can
OOM on `e2-micro`. Bump to `e2-medium` for headroom.

## 2. Firewall for 80/443

The `http-server` / `https-server` tags map to default rules on most projects; create one
explicitly if they don't exist:

```bash
gcloud compute firewall-rules create allow-web \
  --allow=tcp:80,tcp:443 --target-tags=http-server,https-server --direction=INGRESS
```

Get the VM's external IP (you'll paste it into DNS):

```bash
gcloud compute instances describe kidspots --zone=australia-southeast1-b \
  --format='value(networkInterfaces[0].accessConfigs[0].natIP)'
```

## 3. Namecheap DNS — apex A record (remove the URL redirect first)

In Namecheap → **Domain List → Manage (kidspots.store) → Advanced DNS**:

1. **Delete** the default **URL Redirect Record** on Host `@` (and the `CNAME`/parking record if
   present). A `URL Redirect` on `@` will otherwise shadow the A record and you'll get a parking
   page instead of the app.
2. **Add** an **A Record**: Host `@` · Value `<VM_EXTERNAL_IP>` · TTL `Automatic`.
3. Apex-only — **do not** add a `www` record (we're not serving `www`). *If* you later want
   `www.kidspots.store` → apex, add a `CNAME` `www → kidspots.store` **and** the Caddy `www`
   block noted in §7.

Verify propagation before continuing (can take minutes):

```bash
dig +short kidspots.store            # should print the VM IP
```

## 4. Install Docker on the VM

```bash
gcloud compute ssh kidspots --zone=australia-southeast1-b
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"      # then exit + re-SSH so `docker` works without sudo
```

## 5. Get the code + create `.env` (never committed — INV-9)

```bash
git clone https://github.com/turabekh/juggle.git && cd juggle    # main = full stack
cp .env.production.example .env
```

Generate the two secrets and fill `.env`:

```bash
openssl rand -hex 24     # -> JUGGLE_DB_PASSWORD  (also paste into JUGGLE_DATABASE_URL)
openssl rand -hex 48     # -> JUGGLE_JWT_SECRET
```

Edit `.env` (`nano .env`) so that:

- `JUGGLE_DB_PASSWORD=<hex24>` — hex, so no URL-encoding needed.
- `JUGGLE_DATABASE_URL=postgresql+psycopg://juggle:<hex24>@db:5432/juggle` — **same** password,
  host is `db` (the compose service), port `5432` (internal).
- `JUGGLE_JWT_SECRET=<hex48>`.
- `DOMAIN=kidspots.store`, `JUGGLE_PUBLIC_BASE_URL=https://kidspots.store`,
  `JUGGLE_CORS_ORIGINS=["https://kidspots.store"]` — already the defaults in the example.
- Leave `JUGGLE_STRIPE_*` **blank** (FakeGateway) for the first deploy.
- Set `JUGGLE_PLATFORM_LEGAL_NAME` / `JUGGLE_PLATFORM_ABN` before charging real money (not needed
  on the FakeGateway).

## 6. Build + launch

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Ordering is automatic: `db` (health-gated) → `migrate` (runs `alembic upgrade head` once,
exits) → `api` + `worker` → `web` (Caddy on 80/443). First build takes a few minutes.

Watch it come up:

```bash
docker compose -f docker-compose.prod.yml ps                      # migrate = Exited(0); rest Up
docker compose -f docker-compose.prod.yml logs migrate            # should end "Running upgrade ... done"
docker compose -f docker-compose.prod.yml logs -f api             # Ctrl-C to stop tailing
curl -s http://localhost:8000/health                              # {"status":"ok",...}
```

Then open **https://kidspots.store**. Caddy provisions the Let's Encrypt cert on the first HTTPS
request (~30 s); the cert persists in the `caddy_data` volume and auto-renews.

## 7. Make your account admin (no admin-signup endpoint by design)

Sign up a normal account through the site, then flip the flag directly in the DB:

```bash
docker compose -f docker-compose.prod.yml exec db \
  psql -U juggle -d juggle -c \
  "UPDATE user_account SET is_admin = true WHERE email = 'YOUR_EMAIL_HERE';"
```

Log out/in to pick up the `is_admin` JWT claim → admin console (provider approval, config, flags,
bookings ops).

**Optional `www` → apex** (only if you decide you want it later): add the Namecheap `CNAME`
`www → kidspots.store`, then in `apps/web/Caddyfile` add a second site block above the main one:

```
www.kidspots.store {
	redir https://kidspots.store{uri} permanent
}
```

and rebuild web (`docker compose -f docker-compose.prod.yml up -d --build web`). Default stays
apex-only.

---

## What I verified locally (before you deploy)

- `docker compose -f docker-compose.prod.yml config` — **valid**; service graph
  `db → migrate → api/worker → web` intact.
- **API image builds** and **web image builds** (`npm run build` = `vue-tsc` typecheck + `vite build`
  succeed in Docker).
- Alembic reads `get_settings().database_url`, i.e. `JUGGLE_DATABASE_URL` → `@db:5432` at runtime.
- Frontend production bundle calls the API **same-origin at `/api/v1`** (the only `localhost:8000`
  in `apps/web` is an **SSR-only** fallback that this SPA/Caddy deploy never hits).
- Caddy serves the apex from `$SITE_ADDRESS` (= `DOMAIN`), reverse-proxies `/api/*` → `api:8000`,
  and does SPA deep-link fallback (`try_files {path} /index.html`).

## What I could NOT verify (do these on the VM)

1. **TLS issuance** — needs real DNS at the apex + ports 80/443 open on the VM. Check:
   `docker compose -f docker-compose.prod.yml logs web | grep -i certificate` and load
   `https://kidspots.store` in a browser (padlock).
2. **Migrations actually applying against a fresh DB** — check `logs migrate` ends cleanly and
   `docker compose ... exec db psql -U juggle -d juggle -c '\dt' | wc -l` shows the tables.
3. **End-to-end runtime** (I built the images but didn't run the full stack against a real DB).
   After launch: sign up, search, add to cart. `curl -s http://localhost:8000/health` from the VM
   is the quickest liveness check.
4. **Stripe / email** — intentionally off (FakeGateway + stubbed email). Wire real keys later per
   `docs/DEPLOY.md §7`; the webhook sink is `https://kidspots.store/api/v1/booking/stripe/webhook`.

## Backups + ops

See `docs/DEPLOY.md §8–9` for `pg_dump` backup/restore, updates (`git pull && up -d --build`),
and hardening (restrict SSH to your IP/IAP; only 80/443 need to be public).
