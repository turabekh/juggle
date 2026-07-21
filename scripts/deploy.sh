#!/usr/bin/env bash
#
# Build & deploy the kidspots.store production stack.
#
# The production deployment is a single Google Compute Engine VM running the
# Docker Compose stack in docker-compose.prod.yml (db → migrate → api + worker →
# web/Caddy). This script pulls the latest code, rebuilds the images, restarts
# the stack (migrations run automatically via the one-shot `migrate` service),
# and health-checks the result.
#
# Usage:
#   scripts/deploy.sh                 # from your Mac: SSH into the VM and deploy
#   scripts/deploy.sh --branch main   # deploy a specific branch (default: main)
#   scripts/deploy.sh --backup        # take a pg_dump backup before deploying
#   scripts/deploy.sh --on-vm         # run the deploy locally (use when on the VM)
#   scripts/deploy.sh --logs          # tail api logs after deploy (Ctrl-C to stop)
#
# Overridable via environment:
#   KIDSPOTS_INSTANCE  (default: kidspots)
#   KIDSPOTS_ZONE      (default: australia-southeast1-b)
#   KIDSPOTS_REPO_DIR  (default: juggle)          # repo path on the VM, relative to $HOME
#   KIDSPOTS_BRANCH    (default: main)
#
# Prerequisites (remote mode): gcloud CLI authenticated with access to the VM.
# Prerequisites (--on-vm mode): run from inside the repo checkout on the VM.

set -euo pipefail

INSTANCE="${KIDSPOTS_INSTANCE:-kidspots}"
ZONE="${KIDSPOTS_ZONE:-australia-southeast1-b}"
REPO_DIR="${KIDSPOTS_REPO_DIR:-juggle}"
BRANCH="${KIDSPOTS_BRANCH:-main}"
COMPOSE_FILE="docker-compose.prod.yml"

DO_BACKUP=false
ON_VM=false
TAIL_LOGS=false

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch) BRANCH="${2:?--branch needs a value}"; shift 2 ;;
    --backup) DO_BACKUP=true; shift ;;
    --on-vm)  ON_VM=true; shift ;;
    --logs)   TAIL_LOGS=true; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

# ---------------------------------------------------------------------------
# The deploy body runs on the VM (either over SSH, or directly with --on-vm).
# It is emitted as a self-contained script so both paths run identical steps.
# ---------------------------------------------------------------------------
remote_body() {
  cat <<REMOTE
set -euo pipefail

# When invoked over SSH we start in \$HOME; --on-vm passes an absolute path.
cd "${REPO_DIR}"

COMPOSE="sudo docker compose -f ${COMPOSE_FILE}"

echo "==> Repo: \$(pwd)  |  Branch: ${BRANCH}"

if [ "${DO_BACKUP}" = "true" ]; then
  STAMP="\$(date +%F-%H%M%S)"
  echo "==> Backing up database to juggle-\${STAMP}.sql.gz"
  \$COMPOSE exec -T db pg_dump -U juggle -d juggle | gzip > "juggle-\${STAMP}.sql.gz"
  echo "    backup written: \$(pwd)/juggle-\${STAMP}.sql.gz"
fi

echo "==> Fetching latest code"
git fetch --prune origin
git checkout "${BRANCH}"
git pull --ff-only origin "${BRANCH}"
echo "    now at: \$(git rev-parse --short HEAD) \$(git log -1 --pretty=%s)"

echo "==> Building images"
\$COMPOSE build

echo "==> Starting stack (migrations run via the one-shot 'migrate' service)"
\$COMPOSE up -d

echo "==> Migration result"
\$COMPOSE logs --tail=15 migrate || true

echo "==> Waiting for API health"
ok=false
for i in \$(seq 1 30); do
  if curl -fsS -m 5 http://localhost:8000/health >/dev/null 2>&1; then
    ok=true; break
  fi
  sleep 2
done
if [ "\$ok" = "true" ]; then
  echo "    API healthy: \$(curl -fsS -m 5 http://localhost:8000/health)"
else
  echo "    !! API did not become healthy in time — check 'logs api' below" >&2
fi

echo "==> Stack status"
\$COMPOSE ps

if [ "\$ok" != "true" ]; then
  echo "==> Recent API logs (health check failed)"
  \$COMPOSE logs --tail=40 api || true
  exit 1
fi

echo "==> Deploy complete."
REMOTE
}

if [ "$ON_VM" = "true" ]; then
  echo ">> Deploying locally (on-VM mode)"
  bash -c "$(remote_body)"
else
  command -v gcloud >/dev/null 2>&1 || { echo "gcloud CLI not found; use --on-vm on the VM instead." >&2; exit 1; }
  echo ">> Deploying to VM '${INSTANCE}' (zone ${ZONE}) via gcloud SSH"
  gcloud compute ssh "${INSTANCE}" --zone="${ZONE}" --command="$(remote_body)"
fi

# Optional post-deploy log tail (remote mode only; interactive).
if [ "$TAIL_LOGS" = "true" ] && [ "$ON_VM" = "false" ]; then
  echo ">> Tailing API logs (Ctrl-C to stop)"
  gcloud compute ssh "${INSTANCE}" --zone="${ZONE}" \
    --command="cd ${REPO_DIR} && sudo docker compose -f ${COMPOSE_FILE} logs -f --tail=20 api"
fi
