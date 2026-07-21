# Deploying Juggle to Google Cloud Compute Engine

A single-VM Docker Compose deployment: PostGIS + API + maintenance worker + a Caddy
edge that serves the SPA and reverse-proxies `/api`. Caddy issues/renews HTTPS
automatically once a domain points at the VM.

> **Scope note.** The `party_planner` feature (party votes / party page) ships **behind a
> flag that is OFF in production** until a real email gateway is wired (ADR-0011). The rest
> of the marketplace runs without it. See [§7](#7-post-deploy-configuration) to enable it
> deliberately for a demo. Stripe stays on the in-memory FakeGateway until you set live keys.

---

## 0. What you need

- A GCP project with billing enabled and the `gcloud` CLI (or the Cloud Console).
- A domain name you can add a DNS **A record** to (for HTTPS). Optional for a first HTTP-only boot.
- The repo (this deploy uses `docker-compose.prod.yml`, `apps/api/Dockerfile`, `apps/web/Dockerfile`).

## 1. Create the VM

`e2-small` (2 GB RAM) is the practical minimum — the frontend image runs `vue-tsc` at build
time and can OOM on `e2-micro`. Use `e2-medium` if you want headroom.

```bash
gcloud compute instances create juggle \
  --machine-type=e2-small \
  --image-family=ubuntu-2404-lts --image-project=ubuntu-os-cloud \
  --boot-disk-size=30GB \
  --tags=http-server,https-server \
  --zone=australia-southeast1-b        # Sydney — closest region to Perth
```

Open the firewall for web traffic (the `http-server`/`https-server` tags map to these on most
projects; create them explicitly if missing):

```bash
gcloud compute firewall-rules create allow-web \
  --allow=tcp:80,tcp:443 --target-tags=http-server,https-server --direction=INGRESS
```

Note the VM's **external IP**: `gcloud compute instances describe juggle --zone=... --format='value(networkInterfaces[0].accessConfigs[0].natIP)'`.

## 2. Point DNS at the VM (for HTTPS)

Add an **A record** for your apex host (e.g. `kidspots.store`) → the VM's external IP.
Skip this to test over plain HTTP first (leave `DOMAIN` blank in `.env`).

## 3. Install Docker on the VM

SSH in: `gcloud compute ssh juggle --zone=australia-southeast1-b`

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"        # then log out/in so `docker` works without sudo
```

## 4. Get the code + configure

```bash
# Clone (or scp) the repo:
git clone https://github.com/turabekh/juggle.git && cd juggle
# `main` has the full stack (the feature branches were merged). Use a tag/branch if you pin one.

# Create the env file from the template and fill in secrets:
cp .env.production.example .env
nano .env
```

Fill in `.env` (see comments in the file):
- `JUGGLE_DB_PASSWORD` — `openssl rand -hex 24`; **also embed the same value** in `JUGGLE_DATABASE_URL`.
- `JUGGLE_JWT_SECRET` — `openssl rand -hex 48`.
- `DOMAIN` + `JUGGLE_PUBLIC_BASE_URL` + `JUGGLE_CORS_ORIGINS` — your hostname (or leave `DOMAIN`
  blank for HTTP-only on the IP).
- `JUGGLE_PLATFORM_LEGAL_NAME` / `JUGGLE_PLATFORM_ABN` — before charging in production.
- Stripe keys — optional; blank runs the FakeGateway (no real charges).

## 5. Launch

```bash
docker compose -f docker-compose.prod.yml up -d --build
```

Order is handled for you: `db` (health-gated) → `migrate` (runs `alembic upgrade head` once) →
`api` + `worker` → `web`. First build takes a few minutes (npm + uv installs).

Check it:
```bash
docker compose -f docker-compose.prod.yml ps
docker compose -f docker-compose.prod.yml logs -f api      # Ctrl-C to stop tailing
curl -s http://localhost:8000/health                       # from the VM: {"status":"ok",...}
```
Then open `https://<your-domain>` (or `http://<vm-ip>`). Caddy provisions the TLS cert on the
first HTTPS request (allow ~30s); certs persist in the `caddy_data` volume and auto-renew.

## 6. Create the first admin

There is no admin-signup endpoint — flip the flag directly. Sign up a normal account through the
site, then:

```bash
docker compose -f docker-compose.prod.yml exec db \
  psql -U juggle -d juggle -c \
  "UPDATE user_account SET is_admin = true WHERE email = 'you@example.com';"
```
Log out/in to pick up the admin claim. You now have the admin console (provider approval, config,
flags, bookings ops).

## 7. Post-deploy configuration

- **Runtime config** (fee %, seat-hold TTL, etc.) is edited in the **admin panel**, not `.env`.
- **Transactional email (SMTP).** Blank `JUGGLE_EMAIL_SMTP_*` runs the in-memory FakeEmailGateway
  (nothing is sent). To send real mail (booking confirmations, waitlist offers, party invites),
  set `JUGGLE_EMAIL_SMTP_HOST` + `JUGGLE_EMAIL_FROM_ADDRESS` (and username/password) in `.env` and
  `up -d` again — the gateway activates automatically, same pattern as Stripe/Twilio. Providers:
  - **Postmark:** host `smtp.postmarkapp.com`, port `587`, username **and** password = your Server
    API token.
  - **Amazon SES:** host `email-smtp.<region>.amazonaws.com`, port `587`, SES SMTP credentials.
  The `JUGGLE_EMAIL_FROM_ADDRESS` must be a **verified sender** with the provider. Quick check after
  wiring: trigger a booking confirmation (checkout → confirm) and confirm the message arrives.
- **Enable `party_planner`** (only *after* real email is wired above): admin → Flags → turn on
  `party_planner`. Its guest-facing emails (invites, reveal) go through the same gateway, so while
  email is stubbed they are silently dropped — keep the flag OFF until SMTP is configured.
- **Stripe** (when ready): set the three `JUGGLE_STRIPE_*` keys in `.env`, `up -d` again, and add a
  webhook in the Stripe dashboard to `https://<domain>/api/v1/booking/stripe/webhook`.

## 8. Operating it

```bash
# Update to new code:
git pull && docker compose -f docker-compose.prod.yml up -d --build   # migrate re-runs (idempotent)

# Back up the database (run from the VM; store the dump off-box):
docker compose -f docker-compose.prod.yml exec -T db \
  pg_dump -U juggle -d juggle | gzip > juggle-$(date +%F).sql.gz

# Restore:
gunzip -c juggle-YYYY-MM-DD.sql.gz | \
  docker compose -f docker-compose.prod.yml exec -T db psql -U juggle -d juggle

# Stop (keeps data volumes) / start:
docker compose -f docker-compose.prod.yml down
docker compose -f docker-compose.prod.yml up -d
```

## 9. Hardening notes (recommended before real users)

- **Managed database.** Running Postgres in a container on the VM is fine to start, but for
  durability move to **Cloud SQL for PostgreSQL** (enable the PostGIS extension), drop the `db`
  service from the compose file, and point `JUGGLE_DATABASE_URL` at the Cloud SQL instance
  (via the Cloud SQL Auth Proxy or private IP). Then take scheduled backups off the app's shoulders.
- **Secrets.** `.env` on the box is the simplest option; for stronger hygiene use GCP Secret Manager
  and inject at deploy time. Never commit `.env` (INV-9).
- **Backups.** Automated — nightly `pg_dump` → GCS. See §10.
- **SSH exposure.** Done for kidspots.store — port 22 is restricted to the operator IP + Google's
  IAP range via two firewall rules (`kidspots-ssh-allow` priority 1000, `kidspots-ssh-deny` priority
  1100) targeting the `kidspots-ssh` network tag, so only this VM is affected. IP changed? Use
  `gcloud compute ssh kidspots --zone=australia-southeast1-b --tunnel-through-iap`.
- **Image builds.** For faster/leaner deploys, build images in CI and push to Artifact Registry,
  then `image:` them in the compose file instead of `build:`.

## 10. Automated backups & restore test

Nightly off-box backups to Google Cloud Storage, plus a recoverability check.

**One-time setup (already done for kidspots.store):**
- Bucket `gs://lotscope-501014-kidspots-db-backups` (australia-southeast1) with a 30-day
  auto-delete lifecycle rule.
- The VM's service account needs **storage read-write scope** (set with the VM stopped:
  `gcloud compute instances set-service-account kidspots --zone=... --scopes=devstorage.read_write,...`)
  **and** `roles/storage.objectAdmin` on the bucket
  (`gcloud storage buckets add-iam-policy-binding <bucket> --member=serviceAccount:<sa> --role=roles/storage.objectAdmin`).
- `scripts/kidspots-backup.sh` installed at `/usr/local/bin/kidspots-backup.sh`, run by root cron:
  `0 18 * * * /usr/local/bin/kidspots-backup.sh >> /var/log/kidspots-backup.log 2>&1` (02:00 Perth).

**Verify recoverability** (safe — restores into a throwaway DB, never touches live):
```bash
./scripts/kidspots-restore-test.sh    # run on the VM
```

**Restore a backup into live** (only if you mean it):
```bash
gcloud storage cp gs://lotscope-501014-kidspots-db-backups/juggle-<stamp>.sql.gz - \
  | gunzip | sudo docker compose -f docker-compose.prod.yml exec -T db psql -U juggle -d juggle
```

Both scripts honour `KIDSPOTS_BACKUP_BUCKET` / `KIDSPOTS_COMPOSE_FILE` env overrides.
