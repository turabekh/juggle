#!/usr/bin/env bash
# Restore-recoverability test: restore the latest GCS backup into a throwaway
# database, verify schema + row counts, then drop it. NEVER touches the live
# `juggle` DB. Run on the VM: ./kidspots-restore-test.sh
set -euo pipefail
export PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin:/snap/bin

BUCKET="${KIDSPOTS_BACKUP_BUCKET:-gs://lotscope-501014-kidspots-db-backups}"
COMPOSE="${KIDSPOTS_COMPOSE_FILE:-/home/turaboy/juggle/docker-compose.prod.yml}"
PSQL=(sudo docker compose -f "$COMPOSE" exec -T db psql -U juggle)

LATEST="$(gcloud storage ls "${BUCKET}/" | grep '\.sql\.gz$' | sort | tail -1)"
echo "Latest backup: $LATEST"

echo "== (re)create throwaway restore_test DB =="
"${PSQL[@]}" -d postgres -c "DROP DATABASE IF EXISTS restore_test;" >/dev/null
"${PSQL[@]}" -d postgres -c "CREATE DATABASE restore_test;" >/dev/null

echo "== restore into restore_test (streamed from GCS) =="
gcloud storage cp "$LATEST" - | gunzip | "${PSQL[@]}" -d restore_test >/tmp/restore.out 2>&1 || true
ERRS="$(grep -c '^ERROR' /tmp/restore.out || true)"
echo "restore ERROR lines: ${ERRS}"
[ "${ERRS}" != "0" ] && { echo "--- sample errors ---"; grep '^ERROR' /tmp/restore.out | head -5; }

echo "== table counts (restore_test vs live juggle) =="
RT="$("${PSQL[@]}" -d restore_test -tAc "select count(*) from information_schema.tables where table_schema='public';")"
LV="$("${PSQL[@]}" -d juggle        -tAc "select count(*) from information_schema.tables where table_schema='public';")"
echo "restore_test tables: ${RT} | live juggle tables: ${LV}"

echo "== key row counts in the restored DB =="
for t in user_account organisation program session booking payment; do
  n="$("${PSQL[@]}" -d restore_test -tAc "select count(*) from \"$t\";" 2>/dev/null || echo "ERR")"
  echo "  ${t}: ${n}"
done

echo "== drop throwaway DB =="
"${PSQL[@]}" -d postgres -c "DROP DATABASE restore_test;" >/dev/null
echo "restore_test dropped. Live juggle DB untouched."
