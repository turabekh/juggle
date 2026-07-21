#!/usr/bin/env bash
# Nightly production DB backup -> GCS.
#
# Deployed to the kidspots.store VM at /usr/local/bin/kidspots-backup.sh and run
# by root cron (02:00 Perth / 18:00 UTC):
#   0 18 * * * /usr/local/bin/kidspots-backup.sh >> /var/log/kidspots-backup.log 2>&1
#
# Streams pg_dump | gzip straight to the bucket (no local disk). Old dumps are
# auto-pruned by the bucket's 30-day lifecycle rule. The VM's service account
# needs storage read-write scope + objectAdmin on the bucket (see docs/DEPLOY.md).
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin

BUCKET="${KIDSPOTS_BACKUP_BUCKET:-gs://lotscope-501014-kidspots-db-backups}"
COMPOSE="${KIDSPOTS_COMPOSE_FILE:-/home/turaboy/juggle/docker-compose.prod.yml}"
STAMP="$(date -u +%F-%H%M%S)"
DEST="${BUCKET}/juggle-${STAMP}.sql.gz"

docker compose -f "$COMPOSE" exec -T db pg_dump -U juggle -d juggle \
  | gzip \
  | gcloud storage cp - "$DEST"

echo "$(date -u '+%F %T') backup OK -> ${DEST}"
