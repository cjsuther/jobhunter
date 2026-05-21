# JobHunter

Sistema multi-tenant de búsqueda y postulación asistida a empleos para el mercado argentino. Ver [`jobhunter-spec.md`](./jobhunter-spec.md) para el spec completo.

Este repo es el scaffolding de **Fase 1 (MVP)** según el roadmap del spec.

## Stack

- **Backend**: Python 3.12 + FastAPI + Celery + SQLAlchemy + Alembic
- **Workers**: Celery (scrape / scoring / generation / apply) + Redis broker
- **DB**: PostgreSQL 16
- **Storage**: MinIO (S3-compatible) para CVs y PDFs generados
- **LLM**: Anthropic SDK — Haiku 4.5 (scoring), Sonnet 4.6 (generación)
- **Frontend**: React 18 + Vite + TypeScript + Tailwind + shadcn/ui
- **Deploy**: Docker Compose

## Estructura

```
backend/         FastAPI + Celery + scrapers + appliers
frontend/        React + Vite
docker-compose.yml
.env.example     plantilla de variables
.env             local (no commitear)
```

Ver `jobhunter-spec.md` §10 para el árbol completo.

## Levantar el stack en local

1. Copiá `.env.example` a `.env` y completá los valores (en este repo ya hay un `.env` con keys de desarrollo + placeholder para `ANTHROPIC_API_KEY`).
2. Pegá tu API key real en `.env`:
   ```
   ANTHROPIC_API_KEY=sk-ant-...
   ```
3. Levantar todo:
   ```bash
   docker compose up --build
   ```
4. Servicios:
   - API: <http://localhost:8000> (docs: `/api/docs`)
   - Frontend: <http://localhost:5173>
   - MinIO console: <http://localhost:9001> (user/pass según `.env`)
   - Postgres: `localhost:5432`
   - Redis: `localhost:6379`

5. Crear el primer admin (lee `BOOTSTRAP_ADMIN_*` de `.env`; idempotente):
   ```bash
   docker compose exec api python -m app.scripts.bootstrap_admin
   ```
   O pasando flags:
   ```bash
   docker compose exec api python -m app.scripts.bootstrap_admin \
     --email admin@jobhunter.local --password admin1234
   ```

## Tests

```bash
cd backend
pip install -e ".[dev]"
pytest -q
ruff check app tests
```

Los tests usan SQLite en memoria — incluyen suite de `multitenant` que verifica que un usuario no puede ver/tocar recursos de otro.

## Estado de Fase 1

- [x] Repo + Docker Compose
- [x] Modelo de datos + migration inicial
- [x] Auth JWT + `get_current_user` / `require_admin`
- [x] CRUD profile + criteria
- [x] Endpoints de matches, tracking, admin
- [x] Servicios LLM (scoring + generación) + WeasyPrint PDF
- [x] Encryption (Fernet)
- [x] Celery workers (scrape / score / generate / apply) — esqueleto
- [x] Frontend: login + dashboard + match detail + tracking + settings
- [x] CI: ruff + mypy + pytest + tsc

### Pendiente para cerrar Fase 1

- [ ] Scrapers reales para Bumeran y Computrabajo (selectores y endpoints frescos)
- [ ] Wire end-to-end scraper → scoring → generator → dashboard con un usuario de prueba
- [ ] Tests de las llamadas LLM mockeadas con factory_boy

### Fase 2 / 3 — ver spec §9

LinkedIn, ZonaJobs, Clarín, Portal Empleo BA, modo `scripted`, tracking avanzado, OAuth de Gmail para detección de respuestas, etc.

## Notas operativas

- **Caps diarios** se aplican en `app/workers/apply_tasks.py` (`DAILY_CAPS_DEFAULT`).
- **Anthropic prompt cache** — el system prompt del scoring va con `cache_control` para amortizar costos cuando se evalúan muchos jobs por usuario.
- **Cookies de portales** se guardan encriptadas con Fernet (`MASTER_ENCRYPTION_KEY`).
- **Audit log** disponible vía `app/services/audit.py`; falta cablearlo en los endpoints sensibles.
