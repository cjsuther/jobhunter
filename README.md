# JobHunter

Sistema multi-tenant de búsqueda y postulación asistida a empleos para el mercado argentino, con scoring y generación de materiales por Claude (Haiku + Sonnet). Spec completo en [`jobhunter-spec.md`](./jobhunter-spec.md).

**Filosofía**: human-in-the-loop. El sistema descubre, filtra, scorea y prepara materiales — vos aprobás y postulás. Caps diarios estrictos. Nada de auto-apply masivo (es la diferencia entre 8-15 % de response rate y una cuenta de LinkedIn baneada).

## Stack

| Capa | Tecnología |
|---|---|
| Backend | Python 3.12 + FastAPI |
| Workers | Celery + Redis (4 queues: scrape / scoring / generation / apply) |
| DB | PostgreSQL 16 + Alembic |
| Storage | MinIO (S3-compatible) para PDFs y CVs |
| LLM | Anthropic SDK — Haiku 4.5 (scoring), Sonnet 4.6 (generación + parseo CV) |
| Browser | Playwright + Chromium (Bumeran/ZonaJobs son SPAs) |
| PDF | WeasyPrint · DOCX: python-docx |
| Frontend | React 18 + Vite + TypeScript + TailwindCSS + React Query |
| Encryption | Fernet (cookies de portales, API keys per-user) |
| Deploy | Docker Compose |

## Quick start (la forma fácil)

En una Mac limpia, **una sola línea**:

```bash
curl -fsSL https://raw.githubusercontent.com/cjsuther/jobhunter/main/scripts/deploy.sh | bash
```

Lo que hace:
1. Verifica que tengas `git`, `docker` y `docker compose`. Falla con mensaje claro si falta algo.
2. Si Docker Desktop está instalado pero cerrado, lo abre y espera a que levante.
3. Clona el repo en `~/jobhunter` (sobreescribible con `JOBHUNTER_DIR=~/loquesea bash ...`).
4. **Genera secretos aleatorios** para Postgres / JWT / Fernet / MinIO en `.env`.
5. `docker compose build` (la primera vez tarda 5-10 min por Chromium).
6. Migra la base + levanta el stack completo.
7. Imprime endpoints y próximos pasos.

Después del script: cre&aacute; el admin y configurá tu Anthropic API key desde la UI (ver "Primera vez" abajo).

## Quick start (manual)

Si preferís entender qué pasa o ya tenés el repo clonado:

```bash
git clone https://github.com/cjsuther/jobhunter.git
cd jobhunter
cp .env.example .env
# Editar .env: generar MASTER_ENCRYPTION_KEY con
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# Generar JWT_SECRET y POSTGRES_PASSWORD con
#   python -c "import secrets; print(secrets.token_urlsafe(48))"
docker compose build
docker compose up -d
docker compose exec api alembic upgrade head
```

Para correr el deploy script desde un clone existente:
```bash
./scripts/deploy.sh
```

## Primera vez

Después de que el stack está corriendo:

**1. Crear el admin**:
```bash
docker compose exec api python -m app.scripts.bootstrap_admin
```
Por default usa `BOOTSTRAP_ADMIN_EMAIL` / `BOOTSTRAP_ADMIN_PASSWORD` del `.env` (default `admin@jobhunter.local` / `admin1234`). Es idempotente.

**2. Login** en <http://localhost:5173> con esas credenciales.

**3. Configurar tu Anthropic API key**:
- Settings → "API key de Anthropic" → pegá tu `sk-ant-...`.
- "Probar" hace un ping de 1 token a Haiku (~$0.0001) para validarla.
- Se guarda **encriptada con Fernet** en la tabla `user_secrets`. Cae al `.env` como fallback si no la configurás.

**4. Crear un perfil profesional**:
- Settings → "+ Nuevo perfil" (podés tener varios; ej. "HRBP CABA" y "Reclutamiento Tech Remoto" con CVs distintos).
- Subí tu CV en PDF → Sonnet lo parsea a JSON Resume → revisás y guardás.
- Configurá criterios de búsqueda (keywords, ubicaciones, portales).

**5. Probar un scraper** (recomendado antes de crear búsquedas reales):
- Scrapers → elegí portal + keywords + ubicación → "Probar búsqueda".
- Si trae resultados, los selectores funcionan. Si trae 0 o error, te avisa.

**6. Correr una búsqueda**:
- Settings → tu búsqueda → "Correr ahora", o esperá el cron de 6h.
- Mirá `/queue` para ver el progreso en tiempo real.
- Los matches aparecen en el Dashboard una vez scoreados.

## Endpoints del frontend

| Ruta | Qué hace |
|---|---|
| `/dashboard` | Cola de matches con filtros por perfil, score mínimo y portal. Widget de costos arriba. |
| `/matches/:id` | Detalle del match: JD completa, análisis del scoring, generación on-demand de CV/carta, edición inline, descargas PDF/DOCX. |
| `/queue` | Workers + colas Redis en vivo. Tareas activas con elapsed time, cancelar tareas, vaciar colas. Auto-refresca cada 3s. |
| `/scrapers` | Tester interactivo de scrapers — corre un search sin persistir nada, útil para validar selectores. |
| `/tracking` | Funnel de conversión y aplicaciones. |
| `/settings` | API key, perfiles, CVs, criterios de búsqueda. |

## Arquitectura: modelo de datos

```
users (1) ──── (N) profiles
                    │
                    ├── (N) search_criteria  → habilitan portales para scraping
                    │
                    └── (N) user_job_matches → 1 row por (profile, job) scoreado
                              │
                              └── (N) generated_materials  (CV/carta, versionados)
                                          │
                                          └── (N) applications  (postulaciones efectivas)

jobs   (global, deduped por source_portal + external_id — un mismo job puede aparecer en N perfiles)
```

Cada usuario tiene N perfiles. Cada perfil tiene su CV propio, su perfil profesional, y sus búsquedas. Un mismo job se puede scorear desde varios perfiles del mismo usuario (la unique constraint es `(profile_id, job_id)`).

## Scrapers implementados

| Portal | Modo | Estado |
|---|---|---|
| Computrabajo | HTTP + selectolax (HTML estable) | ✓ |
| Bumeran | Playwright (Chromium headless — SPA) | ✓ |
| ZonaJobs | Playwright (mismo JobInt que Bumeran) | ✓ |
| LinkedIn | HTTP guest API + JSON-LD para detalle | ✓ |
| Clarín Empleos | Stub | Fase 2 |
| Portal Empleo BA | Stub | Fase 2 |

Los selectores HTML cambian cada par de meses. Si un scraper deja de funcionar, probalo en `/scrapers` para ver el output exacto y ajustá los selectores en `backend/app/scrapers/<portal>.py`.

## LLM: cuándo se llama

| Operación | Modelo | Trigger |
|---|---|---|
| **Parseo de CV** | Sonnet 4.6 | POST de PDF en Settings |
| **Scoring** | Haiku 4.5 | Automático tras cada scrape, por cada criteria que matchee el job |
| **Generación de CV adaptado** | Sonnet 4.6 | Manual (botón "Generar/Regenerar" en match detail) |
| **Generación de carta** | Sonnet 4.6 | Manual (botón "Generar/Regenerar") |

La generación **NO es automática** — se dispara solo cuando el usuario lo pide desde la UI. Esto mantiene el gasto de Sonnet bajo control.

**Cost tracking**: cada llamada al SDK persiste tokens (input / output / cache write / cache read) y calcula `cost_usd` con la tabla de precios en `app/services/llm_pricing.py`. El widget del dashboard agrega hoy / 7d / 30d / total y desglosa por modelo y propósito.

## Caps y safety

- **Caps diarios por portal** (hardcoded en `app/workers/apply_tasks.py`):
  - LinkedIn: 15/día
  - Bumeran / ZonaJobs / Computrabajo / Clarín / PortalEmpleoBA: 25/día
- **Delays randomizados** entre requests del scraper (3-8s LinkedIn, 1.5-3.5s otros).
- **Rotación de User-Agent** en cada request.
- **Modo `assisted` (default)**: el sistema prepara los materiales, vos clickeás "Postular" y se abre el portal en una pestaña nueva. No hay auto-submission. Modo `scripted` (Fase 3) requiere opt-in explícito por portal.
- **Audit log** en `audit_log` para acciones sensibles.
- **Encryption at rest**: cookies de portales y API keys de usuarios en `BYTEA` encriptado con Fernet.

## Migrations

Aplican automáticamente cuando arranca el contenedor `api` (`alembic upgrade head` en el `command`). Manual:
```bash
docker compose exec api alembic upgrade head
docker compose exec api alembic current
docker compose exec api alembic history
```

Crear una nueva:
```bash
docker compose exec api alembic revision --autogenerate -m "descripción"
# Revisar el archivo generado en backend/alembic/versions/
docker compose exec api alembic upgrade head
```

## Tests

```bash
cd backend
python3.12 -m venv .venv
.venv/bin/pip install -e ".[dev]"
.venv/bin/pytest -q
.venv/bin/ruff check app tests
.venv/bin/mypy app    # no es blocker (continue-on-error en CI)
```

Los tests usan SQLite en memoria. Incluyen:
- `tests/integration/test_auth.py` — login, register, refresh.
- `tests/integration/test_multitenant.py` — aislamiento cross-tenant de profiles y criteria.
- `tests/integration/test_health.py` — health endpoint.
- `tests/unit/test_encryption.py` — Fernet roundtrip.
- `tests/unit/test_tokens.py` — JWT.

CI corre `ruff` + `mypy` (warn-only) + `pytest` y `tsc` para el frontend en cada PR (`.github/workflows/test.yml`).

## Estructura

```
backend/
├── app/
│   ├── main.py                FastAPI + middleware + router wiring
│   ├── config.py              Settings (env vars)
│   ├── celery_app.py          Celery + beat schedule (scrape cada 6h)
│   ├── db.py                  SQLAlchemy engine + session
│   ├── auth/                  JWT + bcrypt + dependencies
│   ├── models/                ORM (User, Profile, SearchCriteria, Job,
│   │                              UserJobMatch, GeneratedMaterial,
│   │                              Application, AuditLog, LLMCall, UserSecret,
│   │                              PortalSession)
│   ├── schemas/               Pydantic (request/response)
│   ├── routers/               account, auth, profiles, criteria, matches,
│   │                          tracking, queue, scrapers, costs, admin
│   ├── services/              llm, scoring, generator, cv_parser, pdf,
│   │                          docx_render, encryption, storage, api_keys,
│   │                          llm_pricing, audit
│   ├── scrapers/              base + 6 portales
│   ├── appliers/              base (Fase 3)
│   ├── workers/               scrape / score / generate / apply tasks
│   └── scripts/               bootstrap_admin
├── alembic/                   migrations 0001..0004
├── tests/
├── pyproject.toml
└── Dockerfile                 instala Chromium para Playwright

frontend/
├── src/
│   ├── App.tsx                router + nav
│   ├── pages/                 Login, Dashboard, MatchDetail, Tracking,
│   │                          Queue, Scrapers, Settings
│   ├── components/            MatchCard, CostsWidget, CVUploader,
│   │                          CriteriaForm, ProfileEditor, AnthropicKeyPanel
│   ├── lib/                   api, auth, utils
│   └── types/api.ts
├── package.json
└── Dockerfile

scripts/deploy.sh              one-line install para Mac/Linux
docker-compose.yml             postgres + redis + minio + api + 4 workers + beat + web
                               (+ flower opcional con --profile monitoring)
.env.example                   plantilla
.github/workflows/test.yml     CI
```

## Variables de entorno

Las críticas (el deploy script las auto-genera en el primer run):

| Variable | Para qué | Default |
|---|---|---|
| `DATABASE_URL` | Conexión a Postgres | `postgresql+psycopg://jobhunter:<pwd>@postgres:5432/jobhunter` |
| `JWT_SECRET` | Firma de tokens JWT | random 64 bytes |
| `MASTER_ENCRYPTION_KEY` | Fernet key para encriptar API keys y cookies | random 32 bytes |
| `ANTHROPIC_API_KEY` | Fallback de LLM si el usuario no configuró la suya | placeholder (opcional) |
| `BOOTSTRAP_ADMIN_EMAIL` | Email del admin inicial | `admin@jobhunter.local` |
| `BOOTSTRAP_ADMIN_PASSWORD` | Pwd del admin inicial | `admin1234` |
| `LLM_MODEL_SCORING` | Modelo para scoring | `claude-haiku-4-5-20251001` |
| `LLM_MODEL_GENERATION` | Modelo para generación y parseo de CV | `claude-sonnet-4-6` |

Ver `.env.example` para la lista completa.

## Operación

**Ver logs en vivo de un servicio**:
```bash
docker compose logs -f api
docker compose logs -f worker-scoring
docker compose logs -f worker-scraper worker-scoring worker-generator worker-applier
```

**Reiniciar un componente sin afectar el resto**:
```bash
docker compose restart api
docker compose restart worker-scoring
```

**Flower (inspección avanzada de Celery)**:
```bash
docker compose --profile monitoring up -d flower
open http://localhost:5555
```

**Bajar todo (sin perder datos en volumes)**:
```bash
docker compose down
```

**Reset total (BORRA datos)**:
```bash
docker compose down -v   # elimina pgdata, miniodata, flowerdata
```

**Re-correr el deploy script** (pull + rebuild + restart):
```bash
~/jobhunter/scripts/deploy.sh
```
Si tenés cambios locales sin commitear, se guardan automáticamente con `git stash`.

## Roadmap

**Fase 1 (MVP)** — listo
- Stack completo, multi-profile, scoring + generación end-to-end, dashboard funcional, cola observable, descarga PDF/DOCX, API key configurable desde UI, cost tracking.

**Fase 2** (pendiente)
- Scrapers Clarín Empleos y Portal Empleo BA.
- Easy Apply de LinkedIn con sesión del usuario (riesgo alto de baneo, requiere opt-in).
- Telegram bot para approvals desde el celular.
- A/B testing de cartas (¿cuál tipo de carta convierte mejor?).

**Fase 3**
- Modo `scripted` para Bumeran / ZonaJobs / Computrabajo (Playwright autoenvía).
- OAuth de Gmail para auto-detección de respuestas de reclutadores.
- Recomendaciones de mejora del CV base ("este perfil rindió mejor con X cambio").

## Notas

- El `.env` con tu API key real **no se commitea** (está en `.gitignore`). Si lo querés versionar de alguna forma, usá un secrets manager externo.
- Anthropic no entrena con datos de la API por default — igual evitamos mandar DNI, dirección exacta o teléfono en los prompts.
- El sistema fue diseñado siguiendo el spec (`jobhunter-spec.md`), que describe la arquitectura, prompts y decisiones más en profundidad.
