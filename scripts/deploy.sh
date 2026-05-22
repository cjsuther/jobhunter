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
if ! command -v git >/dev/null 2>&1; then
  fail "git no está instalado. En macOS, corré: xcode-select --install"
fi
if ! command -v docker >/dev/null 2>&1; then
  fail "docker no está instalado. Descargá Docker Desktop de https://docker.com/products/docker-desktop"
fi

# If the Docker daemon isn't responding, try to launch Docker Desktop on macOS
# and wait for it to become ready. Linux servers don't have Desktop — fall back
# to the same "start it yourself" failure there.
start_docker_if_needed() {
  if docker info >/dev/null 2>&1; then
    return 0
  fi
  if [[ "$(uname -s)" == "Darwin" ]] && [[ -d "/Applications/Docker.app" ]]; then
    info "Docker no está corriendo — iniciando Docker Desktop"
    open -a Docker
    # Docker Desktop typically needs 20-50s on first start.
    for i in $(seq 1 60); do
      if docker info >/dev/null 2>&1; then
        ok "Docker Desktop arriba (tras ${i}s)"
        return 0
      fi
      sleep 2
    done
    fail "Docker Desktop no respondió después de 120s. Abrilo manualmente y volvé a correr."
  fi
  fail "Docker no está corriendo. Iniciá el daemon (Docker Desktop en Mac, 'systemctl start docker' en Linux) y reintentá."
}
start_docker_if_needed

docker compose version >/dev/null 2>&1 || fail "Necesitás Docker Compose v2 (incluido en Docker Desktop reciente)."
command -v python3 >/dev/null 2>&1 || warn "python3 no encontrado — se va a pedir si llega el momento de generar secretos."
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

# Helper: generate a random value (first-run secret bootstrap).
gen_fernet() {
  # 32 random bytes → url-safe base64 — exactly what cryptography.fernet expects.
  python3 -c "import base64, os; print(base64.urlsafe_b64encode(os.urandom(32)).decode())"
}
gen_token() {
  python3 -c "import secrets; print(secrets.token_urlsafe(${1:-48}))"
}

# Replace a KEY=value line in .env in-place. macOS sed needs '' after -i.
replace_env() {
  local key="$1" value="$2"
  local esc_value="${value//|/\\|}"
  sed -i.bak "s|^${key}=.*|${key}=${esc_value}|" .env && rm -f .env.bak
}

if [[ ! -f .env ]]; then
  cp .env.example .env
  info "Generando secretos de infraestructura (Postgres / JWT / Fernet / MinIO)…"
  if ! command -v python3 >/dev/null 2>&1; then
    fail "Necesito python3 para generar secretos. En macOS: 'brew install python' o usá Xcode CLT."
  fi
  pg_pass="$(gen_token 24)"
  replace_env "POSTGRES_PASSWORD" "$pg_pass"
  replace_env "JWT_SECRET" "$(gen_token 64)"
  replace_env "MASTER_ENCRYPTION_KEY" "$(gen_fernet)"
  replace_env "MINIO_SECRET_KEY" "$(gen_token 24)"
  replace_env "DATABASE_URL" \
    "postgresql+psycopg://jobhunter:${pg_pass}@postgres:5432/jobhunter"
  replace_env "DATABASE_URL_SYNC" \
    "postgresql+psycopg://jobhunter:${pg_pass}@postgres:5432/jobhunter"
  # ANTHROPIC_API_KEY stays as the placeholder — it's optional now: configure it
  # from Settings → API key de Anthropic in the UI after first boot.
  ok ".env creado con secretos aleatorios"
  warn "ANTHROPIC_API_KEY quedó como placeholder."
  warn "Podés configurarla desde la UI (Settings → API key de Anthropic) o editar .env ahora."
  if [[ "${JOBHUNTER_SKIP_EDIT:-0}" != "1" ]]; then
    printf "\033[36m▸\033[0m Enter para abrir .env en %s, cualquier otra tecla + Enter para saltar: " "${EDITOR:-nano}"
    read -r choice
    if [[ -z "$choice" ]]; then
      "${EDITOR:-nano}" .env
    fi
  fi
else
  ok ".env ya existe — no se toca"
fi

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
echo "Próximos pasos (solo primera vez):"
echo "  1. Crear el admin:"
echo "       docker compose exec api python -m app.scripts.bootstrap_admin"
echo "     (lee BOOTSTRAP_ADMIN_EMAIL / BOOTSTRAP_ADMIN_PASSWORD del .env;"
echo "      default: admin@jobhunter.local / admin1234)"
echo "  2. Entrar al frontend, login, y en Settings → API key de Anthropic"
echo "     pegar tu sk-ant-... (la podés crear en https://console.anthropic.com)."
