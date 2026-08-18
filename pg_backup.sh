#!/usr/bin/env bash
# ---------------------------------------------------------------------------
# Резервное копирование БД allkey (PostgreSQL в docker-compose.prod.yml).
# Делает сжатый дамп, проверяет его, выгружает во ВНЕШНЕЕ хранилище и удаляет
# старые локальные копии. Локально дампы лежат лишь временно — на том же сервере,
# что и база, они смысла не имеют (сгорит диск — сгорит и бэкап).
#
# НЕ запускается автоматически при деплое. Устанавливается на сервере вручную,
# порядок — в BACKUP.md. Восстановление — в RESTORE-BACKUP.md.
# ---------------------------------------------------------------------------
set -euo pipefail

# ===== Настройки (проверьте под свой сервер) ===============================
# Каталог с docker-compose.prod.yml и .env. По умолчанию — папка самого скрипта
# (если скрипт лежит в корне репозитория рядом с compose-файлом). Можно задать
# переменной окружения ALLKEY_DIR.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${ALLKEY_DIR:-$SCRIPT_DIR}"
COMPOSE_FILE="$REPO_DIR/docker-compose.prod.yml"
ENV_FILE="$REPO_DIR/.env"
DB_SERVICE="db"                              # имя сервиса БД в compose

STAGING_DIR="/var/backups/allkey"            # ВРЕМЕННАЯ локальная папка (не хранилище)
KEEP_LOCAL_DAYS=7                            # сколько дней держать локально

# Внешнее хранилище через rclone: "remote:bucket/path". Настройка remote — в BACKUP.md.
# Оставьте пустым, только если внешнее хранилище пока не настроено (не рекомендуется).
RCLONE_REMOTE="${ALLKEY_BACKUP_REMOTE:-allkey-backup:allkey/db}"
KEEP_REMOTE_DAYS=30                          # сколько дней держать во внешнем хранилище
# ===========================================================================

log()  { echo "[$(date '+%F %T')] $*"; }
fail() { log "ОШИБКА: $*"; exit 1; }

[ -f "$COMPOSE_FILE" ] || fail "нет compose-файла $COMPOSE_FILE (задайте ALLKEY_DIR)"
[ -f "$ENV_FILE" ]     || fail "нет файла окружения $ENV_FILE"

# Имена базы/пользователя/пароль берём из .env (единственный источник).
set -a; . "$ENV_FILE"; set +a
: "${POSTGRES_USER:?POSTGRES_USER не задан в .env}"
: "${POSTGRES_DB:?POSTGRES_DB не задан в .env}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD не задан в .env}"

mkdir -p "$STAGING_DIR"
TS="$(date '+%Y%m%d-%H%M%S')"
FILE="$STAGING_DIR/allkey-${POSTGRES_DB}-${TS}.sql.gz"

log "Дамп базы «$POSTGRES_DB» → $FILE"
# pg_dump выполняется ВНУТРИ контейнера БД; наружу отдаём уже сжатый поток.
# --clean --if-exists делают дамп самодостаточным для восстановления «поверх».
if ! docker compose -f "$COMPOSE_FILE" exec -T -e PGPASSWORD="$POSTGRES_PASSWORD" "$DB_SERVICE" \
        pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists \
     | gzip -c > "$FILE"; then
  rm -f "$FILE"
  fail "pg_dump не выполнился"
fi

# Защита от «пустышки»: битый/пустой дамп не должен вытеснить хорошие копии ротацией.
SIZE=$(stat -c%s "$FILE" 2>/dev/null || stat -f%z "$FILE")
[ "${SIZE:-0}" -gt 1000 ] || { rm -f "$FILE"; fail "дамп подозрительно мал ($SIZE байт) — не считаю валидным"; }
log "Дамп готов, размер ${SIZE} байт"

# Выгрузка во внешнее хранилище.
if [ -n "$RCLONE_REMOTE" ] && command -v rclone >/dev/null 2>&1; then
  log "Выгрузка во внешнее хранилище: $RCLONE_REMOTE"
  rclone copy "$FILE" "$RCLONE_REMOTE" || fail "rclone не выгрузил дамп"
  # Ротация во внешнем хранилище (можно заменить lifecycle-политикой бакета).
  rclone delete --min-age "${KEEP_REMOTE_DAYS}d" "$RCLONE_REMOTE" || log "предупреждение: не удалось почистить старые копии в хранилище"
  log "Выгружено и почищено (>${KEEP_REMOTE_DAYS} дней удалены)"
else
  log "ВНИМАНИЕ: rclone не настроен — дамп остался ТОЛЬКО локально ($FILE)."
  log "Это не резервное копирование. Настройте внешнее хранилище — см. BACKUP.md."
fi

# Ротация локальной временной папки.
log "Удаляю локальные дампы старше ${KEEP_LOCAL_DAYS} дней"
find "$STAGING_DIR" -name 'allkey-*.sql.gz' -type f -mtime +"$KEEP_LOCAL_DAYS" -print -delete

log "Готово."
