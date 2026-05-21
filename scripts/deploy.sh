#!/usr/bin/env bash
# JobHunter deployer for macOS / Linux.
#
# - Clones the repo on first run; on subsequent runs does a fast-forward pull.
# - Copies .env.example → .env the first time and pauses so you can fill in your
#   ANTHROPIC_API_KEY (and any other values you want to override).
# - Rebuilds the Docker images, runs Alembic migrations, and brings up the full
#   stack in detached mode.
#
# Usage:
#   bash scripts/deploy.sh                 # from inside the repo
#   bash ~/jobhunter-deploy.sh             # if you saved it standalone
#
# Override the target directory:
#   JOBHUNTER_DIR=~/code/jobhunter bash deploy.sh
#
# Quiet mode (skip the .env editor prompt on first run):
#   JOBHUNTER_SKIP_EDIT=1 bash deploy.sh

set -euo pipefail

REPO_URL="${JOBHUNTER_REPO:-https://github.com/cjsuther/jobhunter.git}"
TARGET_DIR="${JOBHUNTER_DIR:-$HOME/jobhunter}"
BRANCH="${JOBHUNTER_BRANCH:-main}"

bold()  { printf "\033[1m%s\033[0m\n" "$*"; }
info()  { printf "\033[36m▸\033[0m %s\n" "$*"; }
warn()  { printf "\033[33m⚠\033[0m %s\n" "$*"; }
ok()    { printf "\033[32m✓\033[0m %s\n" "$*"; }
fail()  { printf "\033[31m✗\033[0m %s\n" "$*" >&2; exit 1; }

require() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 no está instalado o no está en PATH"
}

# ---- 0. Prerequisites ------------------------------------------------------
bold "1/5  Verificando dependencias"
require git
require docker
docker info >/dev/null 2>&1 || fail "Docker no está corriendo. Abrí Docker Desktop y volvé a intentar."
docker compose version >/dev/null 2>&1 || fail "Necesitás Docker Compose v2 (incluido en Docker Desktop reciente)."
ok "git, docker y docker compose listos"

# ---- 1. Clone or update ----------------------------------------------------
bold "2/5  Sincronizando código"
if [[ -d "$TARGET_DIR/.git" ]]; then
  cd "$TARGET_DIR"
  info "Repo existente en $TARGET_DIR — actualizando rama '$BRANCH'"
  # Don't blow away local edits. If the user has uncommitted changes, stash & restore.
  if ! git diff-index --quiet HEAD --; then
    warn "Hay cambios locales sin commitear. Los guardo con 'git stash' antes del pull."
    git stash push -u -m "deploy.sh autostash $(date +%FT%T)"
    STASHED=1
  else
    STASHED=0
  fi
  git fetch origin "$BRANCH"
  git checkout "$BRANCH"
  git pull --ff-only origin "$BRANCH"
  if [[ "${STASHED:-0}" == "1" ]]; then
    warn "Tus cambios locales quedaron en 'git stash list'. Restauralos con 'git stash pop' si lo necesitás."
  fi
else
  info "Clonando $REPO_URL en $TARGET_DIR"
  git clone --branch "$BRANCH" "$REPO_URL" "$TARGET_DIR"
  cd "$TARGET_DIR"
fi
ok "Código en $(pwd) — commit $(git rev-parse --short HEAD)"

# ---- 2. .env ---------------------------------------------------------------
bold "3/5  Verificando .env"
if [[ ! -f .env ]]; then
  cp .env.example .env
  warn "Se creó .env desde .env.example."
  warn "Necesitás editar al menos ANTHROPIC_API_KEY antes de continuar."
  if [[ "${JOBHUNTER_SKIP_EDIT:-0}" != "1" ]]; then
    info "Apretá Enter para abrir .env en ${EDITOR:-nano}, o Ctrl+C para hacerlo manual."
    read -r _
    "${EDITOR:-nano}" .env
  fi
fi
if grep -q "sk-ant-REPLACE_ME\|sk-ant-xxxxx" .env 2>/dev/null; then
  warn "Tu .env todavía tiene el placeholder de ANTHROPIC_API_KEY."
  warn "Las llamadas a Claude van a fallar hasta que pongas una key real."
fi
ok ".env listo"

# ---- 3. Build --------------------------------------------------------------
bold "4/5  Build de imágenes Docker"
docker compose build
ok "Imágenes actualizadas"

# ---- 4. Migrations + up ---------------------------------------------------
bold "5/5  Levantando stack"
# Start postgres + redis + minio first so the API has its deps when migrating.
docker compose up -d postgres redis minio
# Wait for postgres to be healthy (compose declares a healthcheck).
info "Esperando que Postgres esté healthy"
for _ in {1..30}; do
  if docker compose ps postgres --format json 2>/dev/null | grep -q '"Health":"healthy"'; then
    break
  fi
  sleep 1
done
# Apply migrations using a one-shot container.
info "Aplicando migraciones Alembic"
docker compose run --rm api alembic upgrade head
# Bring everything else up.
docker compose up -d
ok "Stack arriba"

echo
bold "▸ JobHunter listo"
docker compose ps
echo
echo "Endpoints:"
echo "  API docs:    http://localhost:8000/api/docs"
echo "  Frontend:    http://localhost:5173"
echo "  MinIO:       http://localhost:9001"
echo "  Flower:      docker compose --profile monitoring up -d flower → http://localhost:5555"
echo
echo "Si es tu primera vez, creá el admin:"
echo "  docker compose exec api python -m app.scripts.bootstrap_admin"
