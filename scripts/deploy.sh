#!/usr/bin/env bash
#
# Build & deploy the kidspots.store production stack.
#
# Production is a single Google Compute Engine VM running the Docker Compose
# stack in docker-compose.prod.yml (db → migrate → api + worker → web/Caddy).
# The repo is PRIVATE and the VM has no GitHub credentials, so we do not
# `git pull` on the VM. Instead we ship the exact tree of a branch from this
# machine (which is already authenticated) as a `git archive` tarball, extract
# it over the VM checkout, then rebuild and restart. The one-shot `migrate`
# service applies migrations automatically. The VM's .env (gitignored, holds
# secrets + DOMAIN) is never in the archive, so it is preserved untouched.
#
# Usage:
#   scripts/deploy.sh                 # deploy latest local `main` to the VM
#   scripts/deploy.sh --branch foo    # deploy a different local branch
#   scripts/deploy.sh --backup        # pg_dump the DB on the VM before deploying
#   scripts/deploy.sh --logs          # tail api logs after deploy (Ctrl-C to stop)
#   scripts/deploy.sh --iap           # tunnel SSH/SCP through IAP
#
# SSH to the VM is IP-restricted (firewall `kidspots-ssh-allow`), and home IPs move.
# Rather than reopening the firewall every time yours changes, use --iap: the allowlist
# already includes Google's IAP range (35.235.240.0/20), so the tunnel works from
# anywhere you can authenticate. Needs roles/iap.tunnelResourceAccessor.
#
# Overridable via environment:
#   KIDSPOTS_INSTANCE  (default: kidspots)
#   KIDSPOTS_ZONE      (default: australia-southeast1-b)
#   KIDSPOTS_REPO_DIR  (default: juggle)   # checkout path on the VM, relative to $HOME;
#                                          # its basename is the compose project name,
#                                          # so keep it stable or you orphan the DB volume.
#
# Prerequisites: run from inside this repo; gcloud CLI authenticated with SSH
# access to the VM; git.

set -euo pipefail

INSTANCE="${KIDSPOTS_INSTANCE:-kidspots}"
ZONE="${KIDSPOTS_ZONE:-australia-southeast1-b}"
REPO_DIR="${KIDSPOTS_REPO_DIR:-juggle}"
BRANCH="main"
COMPOSE_FILE="docker-compose.prod.yml"
PROJECT="$(basename "$REPO_DIR")"          # docker compose project name on the VM
API_CONTAINER="${PROJECT}-api-1"
REMOTE_TARBALL="juggle-deploy.tar.gz"

DO_BACKUP=false
TAIL_LOGS=false
USE_IAP="${KIDSPOTS_USE_IAP:-false}"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --branch) BRANCH="${2:?--branch needs a value}"; shift 2 ;;
    --backup) DO_BACKUP=true; shift ;;
    --logs)   TAIL_LOGS=true; shift ;;
    --iap)    USE_IAP=true; shift ;;
    -h|--help) sed -n '2,39p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1" >&2; exit 2 ;;
  esac
done

# Passed to every gcloud compute ssh/scp call.
IAP_FLAG=()
[ "$USE_IAP" = "true" ] && IAP_FLAG=(--tunnel-through-iap)

command -v gcloud >/dev/null 2>&1 || { echo "gcloud CLI not found." >&2; exit 1; }
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || { echo "Run from inside the repo." >&2; exit 1; }
git rev-parse --verify -q "$BRANCH" >/dev/null || { echo "Branch '$BRANCH' not found locally." >&2; exit 1; }

REPO_ROOT="$(git rev-parse --show-toplevel)"
HEAD_SHA="$(git rev-parse --short "$BRANCH")"
HEAD_MSG="$(git log -1 --pretty=%s "$BRANCH")"
TARBALL="$(mktemp -t juggle-deploy.XXXXXX).tar.gz"
trap 'rm -f "$TARBALL"' EXIT

echo ">> Deploying branch '${BRANCH}' (${HEAD_SHA} ${HEAD_MSG})"
echo ">>   to VM '${INSTANCE}' (zone ${ZONE}), path ~/${REPO_DIR}"

echo "==> Building archive of ${BRANCH}"
git -C "$REPO_ROOT" archive --format=tar.gz -o "$TARBALL" "$BRANCH"
echo "    $(du -h "$TARBALL" | cut -f1) tarball"

echo "==> Copying to VM"
gcloud compute scp "${IAP_FLAG[@]}" "$TARBALL" "${INSTANCE}:~/${REMOTE_TARBALL}" --zone="${ZONE}"

# ---------------------------------------------------------------------------
# Remote deploy: extract over the checkout (.env is not in the archive, so it
# survives), rebuild, restart, then gate on the api container's own healthcheck.
# ---------------------------------------------------------------------------
gcloud compute ssh "${IAP_FLAG[@]}" "${INSTANCE}" --zone="${ZONE}" --command="$(cat <<REMOTE
set -euo pipefail
cd "${REPO_DIR}"
COMPOSE="sudo docker compose -f ${COMPOSE_FILE}"

if [ "${DO_BACKUP}" = "true" ]; then
  STAMP="\$(date +%F-%H%M%S)"
  echo "==> Backing up database to ~/juggle-predeploy-\${STAMP}.sql.gz"
  \$COMPOSE exec -T db pg_dump -U juggle -d juggle | gzip > ~/juggle-predeploy-\${STAMP}.sql.gz
fi

ENV_MD5_BEFORE="\$(md5sum .env 2>/dev/null | cut -d' ' -f1 || echo none)"
echo "==> Extracting new code (preserving .env)"
tar xzf ~/${REMOTE_TARBALL}
ENV_MD5_AFTER="\$(md5sum .env 2>/dev/null | cut -d' ' -f1 || echo none)"
[ "\$ENV_MD5_BEFORE" = "\$ENV_MD5_AFTER" ] && echo "    .env preserved (\$ENV_MD5_AFTER)" || echo "    !! .env changed unexpectedly" >&2
rm -f ~/${REMOTE_TARBALL}

echo "==> Building + starting stack (migrations run via one-shot 'migrate')"
\$COMPOSE up -d --build

echo "==> Migration result"
\$COMPOSE logs --tail=6 migrate || true

echo "==> Waiting for api container health"
ok=false
for i in \$(seq 1 40); do
  st="\$(sudo docker inspect --format '{{.State.Health.Status}}' ${API_CONTAINER} 2>/dev/null || echo missing)"
  if [ "\$st" = "healthy" ]; then ok=true; break; fi
  sleep 3
done

echo "==> Stack status"
\$COMPOSE ps

if [ "\$ok" != "true" ]; then
  echo "    !! api did not become healthy — recent logs:" >&2
  \$COMPOSE logs --tail=40 api || true
  exit 1
fi
echo "==> api healthy. Deploy complete."
REMOTE
)"

echo ">> Verifying public endpoint over HTTPS"
IP="$(gcloud compute instances describe "${INSTANCE}" --zone="${ZONE}" \
       --format='value(networkInterfaces[0].accessConfigs[0].natIP)')"
site="$(curl -sS -m 20 --resolve "kidspots.store:443:${IP}" -o /dev/null -w '%{http_code}' https://kidspots.store/ || echo 000)"
api="$(curl -sS -m 20 --resolve "kidspots.store:443:${IP}" -o /dev/null -w '%{http_code}' https://kidspots.store/api/v1/flags || echo 000)"
echo "   https://kidspots.store/  -> ${site}   (expect 200)"
echo "   /api/v1/flags            -> ${api}   (expect 401 = alive, auth-gated)"

if [ "$TAIL_LOGS" = "true" ]; then
  echo ">> Tailing api logs (Ctrl-C to stop)"
  gcloud compute ssh "${IAP_FLAG[@]}" "${INSTANCE}" --zone="${ZONE}" \
    --command="cd ${REPO_DIR} && sudo docker compose -f ${COMPOSE_FILE} logs -f --tail=20 api"
fi
