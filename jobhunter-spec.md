# JobHunter — Sistema Multi-Tenant de Búsqueda y Postulación Asistida a Empleos

## 0. Contexto y filosofía

JobHunter es una plataforma multi-tenant que automatiza el **descubrimiento, filtrado y preparación de materiales** para postulaciones a empleo, manteniendo siempre un **humano en el loop** para la aprobación y envío. El sistema está diseñado para el mercado argentino (LinkedIn, Bumeran, ZonaJobs, Computrabajo, Clarín Empleos, Portal Empleo BA).

**Principio rector:** calidad sobre cantidad. El sistema NO es un auto-apply masivo. Tiene caps diarios estrictos, delays humanos, y prioriza postulaciones bien dirigidas con materiales personalizados generados por IA.

**Por qué human-in-the-loop:**
- LinkedIn detecta y banea automatización agresiva. Para perfiles de RRHH (que son los lectores de las postulaciones), una postulación genérica es descarte automático.
- Las tasas de respuesta documentadas son ~1-3% con auto-apply puro vs. ~8-15% con postulaciones bien dirigidas.
- Una cuenta de LinkedIn baneada es un costo enorme para un profesional.

---

## 1. Stack técnico

| Capa | Tecnología | Notas |
|------|------------|-------|
| Backend API | Python 3.12 + FastAPI | Mismo patrón que Cheyenne/Capresca |
| Workers | Celery + Redis | Tareas async: scraping, scoring, generación |
| Browser automation | Playwright (Python) | Headless por default, headed para postulación asistida |
| DB | PostgreSQL 16 | |
| Cache/Queue | Redis 7 | |
| Object storage | MinIO (S3-compatible) | CVs, cartas generadas en PDF |
| Frontend | React 18 + Vite + TypeScript + TailwindCSS + shadcn/ui | |
| Auth | JWT (access 15min + refresh 7d) | |
| LLM | Anthropic API | Haiku 4.5 para scoring masivo, Sonnet 4.6 para redacción |
| PDF rendering | WeasyPrint | CV/carta a PDF |
| Encryption | cryptography (Fernet) | Cookies de portales y datos sensibles |
| Deploy | Docker Compose | Igual a tu setup actual |
| Migrations | Alembic | |
| CI/CD | GitHub Actions | Mismo flujo que ya usás |

---

## 2. Arquitectura general

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Frontend  │────▶│   FastAPI    │────▶│   PostgreSQL    │
│  (React)    │     │   (REST)     │     │                 │
└─────────────┘     └──────┬───────┘     └─────────────────┘
                           │
                           ▼
                    ┌──────────────┐
                    │   Redis      │
                    │ (queue+cache)│
                    └──────┬───────┘
                           │
              ┌────────────┼────────────┬─────────────┐
              ▼            ▼            ▼             ▼
       ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐
       │ Worker:  │ │ Worker:  │ │ Worker:  │ │ Worker:  │
       │ Scraper  │ │ Scoring  │ │ Generator│ │ Applier  │
       │(Playwr.) │ │ (Haiku)  │ │ (Sonnet) │ │(Playwr.) │
       └────┬─────┘ └────┬─────┘ └────┬─────┘ └────┬─────┘
            │            │            │            │
            └────────────┴────┬───────┴────────────┘
                              ▼
                      ┌──────────────┐
                      │    MinIO     │
                      │ (PDFs, CVs)  │
                      └──────────────┘
```

**Flujo principal:**

1. **Cron (Celery beat)** dispara scraping cada N horas para cada usuario activo según sus criterios.
2. **Scraper worker** trae jobs nuevos, deduplica, persiste en `jobs` (tabla global).
3. **Scoring worker** evalúa cada job nuevo contra cada perfil activo → crea `user_job_matches` con `fit_score`.
4. **Generator worker** para matches con score ≥ threshold del usuario, genera CV adaptado + carta de presentación.
5. **Frontend** muestra al usuario la cola de matches pendientes con materiales listos.
6. **Usuario aprueba** → según portal: redirige + autofiller (default seguro) o ejecuta script de postulación con Playwright (modo avanzado, opt-in).
7. **Tracking**: status updates manuales/automáticos (respuesta recibida, entrevista, etc).

---

## 3. Modelo de datos

```sql
-- Usuarios y autenticación
users (
  id              UUID PRIMARY KEY,
  email           VARCHAR(255) UNIQUE NOT NULL,
  password_hash   VARCHAR(255) NOT NULL,
  role            VARCHAR(20) NOT NULL DEFAULT 'user', -- 'admin' | 'user'
  full_name       VARCHAR(255),
  is_active       BOOLEAN DEFAULT true,
  created_at      TIMESTAMP NOT NULL DEFAULT now(),
  last_login_at   TIMESTAMP
)

-- Perfil profesional (1:1 con users)
profiles (
  user_id              UUID PRIMARY KEY REFERENCES users(id),
  full_name            VARCHAR(255),
  headline             VARCHAR(500),       -- "Lic. en Relaciones del Trabajo"
  current_location     VARCHAR(255),       -- "CABA, Argentina"
  years_experience     INT,
  linkedin_url         VARCHAR(500),
  phone                VARCHAR(50),
  email_contact        VARCHAR(255),
  cv_base_json         JSONB NOT NULL,     -- CV estructurado (ver §3.1)
  cv_base_pdf_path     VARCHAR(500),       -- ruta en MinIO al PDF original
  about_text           TEXT,               -- "Acerca de" largo
  preferred_titles     TEXT[],             -- títulos a los que aspira
  excluded_companies   TEXT[],             -- empresas a excluir
  excluded_keywords    TEXT[],             -- palabras que la descalifican
  updated_at           TIMESTAMP NOT NULL DEFAULT now()
)

-- Criterios de búsqueda (1:N por user, permite múltiples búsquedas)
search_criteria (
  id                UUID PRIMARY KEY,
  user_id           UUID NOT NULL REFERENCES users(id),
  name              VARCHAR(100),         -- "Senior HRBP CABA"
  keywords          TEXT[],
  locations         TEXT[],               -- ["CABA", "GBA Norte", "Remoto"]
  modalities        TEXT[],               -- ["presencial", "hibrido", "remoto"]
  seniority_levels  TEXT[],               -- ["mid", "senior"]
  salary_min_ars    BIGINT,
  contract_types    TEXT[],               -- ["full_time", "part_time", "freelance"]
  min_fit_score     INT DEFAULT 70,       -- threshold para generar materiales
  daily_apply_cap   INT DEFAULT 10,       -- tope de postulaciones por día
  active            BOOLEAN DEFAULT true,
  portals_enabled   TEXT[] NOT NULL,      -- ["linkedin", "bumeran", "computrabajo", ...]
  created_at        TIMESTAMP NOT NULL DEFAULT now()
)

-- Credenciales/sesiones por portal (encriptadas)
portal_sessions (
  id                    UUID PRIMARY KEY,
  user_id               UUID NOT NULL REFERENCES users(id),
  portal                VARCHAR(50) NOT NULL, -- 'linkedin', 'bumeran', etc.
  encrypted_cookies     BYTEA,                -- cookies serializadas + Fernet
  encrypted_credentials BYTEA,                -- email/pass encriptado (opcional)
  last_validated_at     TIMESTAMP,
  status                VARCHAR(20) DEFAULT 'active', -- 'active' | 'expired' | 'banned'
  UNIQUE (user_id, portal)
)

-- Jobs scrapeados (tabla GLOBAL, no por user, dedupe)
jobs (
  id                UUID PRIMARY KEY,
  source_portal     VARCHAR(50) NOT NULL,
  external_id       VARCHAR(255) NOT NULL,   -- id del portal
  external_url      TEXT NOT NULL,
  title             VARCHAR(500) NOT NULL,
  company           VARCHAR(255),
  location          VARCHAR(255),
  modality          VARCHAR(50),             -- 'presencial' | 'hibrido' | 'remoto'
  description       TEXT,                    -- markdown si es posible
  description_hash  VARCHAR(64),             -- sha256 para detección de cambios
  posted_at         TIMESTAMP,
  scraped_at        TIMESTAMP NOT NULL DEFAULT now(),
  application_type  VARCHAR(50),             -- 'easy_apply' | 'external_url' | 'in_portal'
  raw_json          JSONB,                   -- payload original para debugging
  UNIQUE (source_portal, external_id)
)

-- Match user × job (1 fila por usuario por job evaluado)
user_job_matches (
  id                 UUID PRIMARY KEY,
  user_id            UUID NOT NULL REFERENCES users(id),
  job_id             UUID NOT NULL REFERENCES jobs(id),
  criteria_id        UUID REFERENCES search_criteria(id),
  fit_score          INT NOT NULL,           -- 0-100
  scoring_reasoning  TEXT,
  strengths          TEXT[],
  red_flags          TEXT[],
  recommended_action VARCHAR(20),            -- 'apply' | 'review' | 'skip'
  status             VARCHAR(30) NOT NULL DEFAULT 'pending',
  -- 'pending' | 'approved' | 'rejected' | 'applied' | 'responded' | 'interview' | 'offer' | 'closed'
  user_notes         TEXT,
  scored_at          TIMESTAMP NOT NULL DEFAULT now(),
  UNIQUE (user_id, job_id)
)

-- Materiales generados (CV adaptado, carta) por match
generated_materials (
  id              UUID PRIMARY KEY,
  match_id        UUID NOT NULL REFERENCES user_job_matches(id),
  type            VARCHAR(20) NOT NULL,    -- 'cv' | 'cover_letter'
  content_md      TEXT NOT NULL,           -- markdown source
  pdf_path        VARCHAR(500),            -- ruta MinIO
  version         INT NOT NULL DEFAULT 1,  -- por si se regenera
  model_used      VARCHAR(100),            -- 'claude-sonnet-4-6'
  generated_at    TIMESTAMP NOT NULL DEFAULT now()
)

-- Postulaciones realizadas
applications (
  id              UUID PRIMARY KEY,
  match_id        UUID NOT NULL REFERENCES user_job_matches(id),
  channel         VARCHAR(50),             -- 'linkedin_easy_apply' | 'portal_form' | 'external_redirect' | 'email'
  applied_at      TIMESTAMP NOT NULL DEFAULT now(),
  cv_material_id  UUID REFERENCES generated_materials(id),
  letter_material_id UUID REFERENCES generated_materials(id),
  response_received_at TIMESTAMP,
  response_type   VARCHAR(50),             -- 'rejection' | 'interview_request' | 'info_request' | 'offer'
  notes           TEXT
)

-- Audit log (compliance)
audit_log (
  id          BIGSERIAL PRIMARY KEY,
  user_id     UUID,
  action      VARCHAR(100) NOT NULL,
  entity_type VARCHAR(50),
  entity_id   VARCHAR(100),
  payload     JSONB,
  ip_address  VARCHAR(45),
  created_at  TIMESTAMP NOT NULL DEFAULT now()
)
```

### 3.1 Esquema del CV base (`cv_base_json`)

Usar adaptación del estándar [JSON Resume](https://jsonresume.org/schema/) con extensiones:

```json
{
  "basics": {
    "name": "Luciana Ain Lopez",
    "label": "Lic. en Relaciones del Trabajo",
    "email": "...",
    "phone": "...",
    "location": { "city": "CABA", "countryCode": "AR" },
    "summary": "..."
  },
  "work": [
    {
      "company": "...",
      "position": "...",
      "startDate": "2022-03",
      "endDate": "2024-08",
      "highlights": [
        "Lideró el rediseño de la política de comp...",
        "Implementó programa de onboarding..."
      ],
      "keywords": ["compensaciones", "onboarding", "RRHH"]
    }
  ],
  "education": [...],
  "skills": [...],
  "languages": [...],
  "certifications": [...]
}
```

---

## 4. Módulos

### 4.1 Scraping

**Estructura:** un scraper por portal, todos implementan la interfaz común:

```python
# app/scrapers/base.py
from abc import ABC, abstractmethod
from typing import List
from app.schemas.jobs import RawJob, JobDetail, ScrapeCriteria

class BaseJobScraper(ABC):
    portal_name: str

    @abstractmethod
    async def search(self, criteria: ScrapeCriteria) -> List[RawJob]:
        """Lista de ofertas que matchean criteria. NO trae descripción completa."""

    @abstractmethod
    async def get_detail(self, external_id: str) -> JobDetail:
        """Descripción completa de una oferta."""
```

**Implementaciones a desarrollar (en orden de prioridad/facilidad):**

1. **Computrabajo** (Fase 1): scraping HTML simple, no requiere login para listar. `httpx + selectolax` o `BeautifulSoup`. Es el más amigable.
2. **Bumeran** (Fase 1): tiene API JSON pública para resultados de búsqueda. Inspeccionar `Network` en navegador para encontrar el endpoint. Sin auth para listar, sí para postular.
3. **ZonaJobs** (Fase 1): mismo grupo que Bumeran (JobInt), API similar. Reusar mucho del código.
4. **LinkedIn** (Fase 2, con cuidado):
   - Opción A (preferida, más segura): RSS de búsquedas guardadas + scraping mínimo de detalle.
   - Opción B: Playwright headless con sesión del usuario, búsquedas paginadas. Cap de requests/min estricto. Delays randomizados (3-8s entre acciones).
   - **Importante:** rotar User-Agent, respetar `robots.txt`, NO scrapear perfiles, solo listings de jobs públicos.
5. **Clarín Empleos** (Fase 2): scraping HTML.
6. **Portal Empleo BA** (Fase 2): scraping HTML del sitio del GCBA.

**Configuración por scraper:**
```yaml
# config/scrapers.yml
linkedin:
  enabled: true
  rate_limit_per_min: 6
  delay_min_ms: 3000
  delay_max_ms: 8000
  max_results_per_search: 50
  user_agents_pool: [...]
bumeran:
  enabled: true
  rate_limit_per_min: 30
  api_base: "https://www.bumeran.com.ar/api/..."
# ...
```

**Deduplicación:**
- Clave primaria: `(source_portal, external_id)`.
- Cross-portal: detectar duplicados por hash de `(normalized_title, company, location)`. Si ya existe en otro portal, agregar referencia pero no duplicar el match scoring.

**Scheduling:**
- Celery beat schedule por usuario activo, frecuencia configurable (default: cada 6 horas).
- Una task por `(user_id, criteria_id, portal)` para paralelizar.

### 4.2 Scoring / Matching

**Worker flow:**
1. Para cada job nuevo, encolar task `score_job_for_user(job_id, user_id)` por cada usuario activo cuyos criterios matcheen el portal y keywords básicas.
2. Worker llama a la API de Anthropic con Haiku 4.5.
3. Persiste resultado en `user_job_matches`.
4. Si `fit_score >= criteria.min_fit_score`, encola task `generate_materials(match_id)`.

**Prompt de scoring (system):**

```
Sos un asistente de búsqueda laboral experto en el mercado argentino. Tu trabajo
es evaluar el fit entre un perfil profesional y una oferta de empleo, devolviendo
un score 0-100 y razonamiento conciso.

PERFIL DEL CANDIDATO:
- Nombre: {profile.full_name}
- Headline: {profile.headline}
- Ubicación: {profile.current_location}
- Años de experiencia: {profile.years_experience}
- Resumen: {profile.about_text}
- Experiencia laboral: {profile.cv_base_json.work | summarize}
- Educación: {profile.cv_base_json.education | summarize}
- Skills: {profile.cv_base_json.skills}
- Idiomas: {profile.cv_base_json.languages}

CRITERIOS:
- Títulos preferidos: {profile.preferred_titles}
- Empresas excluidas: {profile.excluded_companies}
- Keywords descalificantes: {profile.excluded_keywords}
- Modalidades aceptadas: {criteria.modalities}
- Salario mínimo: {criteria.salary_min_ars} ARS

REGLAS DE SCORING:
- 90-100: match excepcional, aplicar sí o sí
- 75-89: muy buen fit, aplicar
- 60-74: fit razonable, revisar antes de aplicar
- 40-59: fit débil, probablemente no aplicar
- 0-39: descartar

Penalizaciones automáticas (restar al score):
- Empresa en lista de excluidas: -100 (descartar)
- Keyword descalificante en JD: -100 (descartar)
- Modalidad incompatible: -30
- Seniority muy por encima/debajo: -20
- Ubicación incompatible (si no es remoto): -20

Respondé SOLO con JSON válido, sin markdown ni texto extra:
```

**Prompt de scoring (user):**

```
OFERTA:
- Título: {job.title}
- Empresa: {job.company}
- Ubicación: {job.location}
- Modalidad: {job.modality}
- Descripción:
{job.description}

Devolvé:
{
  "fit_score": <int 0-100>,
  "reasoning": "<2-3 oraciones explicando el score>",
  "strengths": ["<3 razones máximo de match>"],
  "red_flags": ["<motivos de duda o descarte si aplica>"],
  "recommended_action": "apply" | "review" | "skip"
}
```

**Costos estimados:**
- Haiku 4.5: ~$0.001 USD por scoring (input ~2k tokens, output ~300 tokens).
- 200 jobs/día × 5 usuarios = 1000 scorings/día = ~$1/día. Negligible.

### 4.3 Generador de materiales

**Trigger:** match con `fit_score >= criteria.min_fit_score` y `recommended_action != 'skip'`.

**Genera dos artefactos:**
1. CV adaptado (markdown → PDF con WeasyPrint)
2. Carta de presentación (markdown → PDF y texto plano para forms)

**Prompt para CV adaptado (Sonnet 4.6):**

```
Sos un experto en redacción de CVs para el mercado laboral argentino.
Tu trabajo es ADAPTAR un CV base a una oferta específica, SIN INVENTAR
información. Solo podés:
- Reordenar bullets de experiencia para destacar los más relevantes
- Reformular bullets para resaltar palabras clave de la oferta (sin mentir)
- Ajustar el resumen profesional al rol específico
- Reordenar skills para poner primero los relevantes

NUNCA agregues experiencia, títulos o skills que no estén en el CV base.

CV BASE (JSON):
{profile.cv_base_json}

OFERTA:
Título: {job.title}
Empresa: {job.company}
Descripción: {job.description}

Devolvé el CV adaptado en MARKDOWN siguiendo este formato exacto:

# {Nombre completo}
**{Headline adaptado al rol}**

📧 email | 📱 teléfono | 📍 ubicación | 🔗 LinkedIn

## Resumen Profesional
{2-3 oraciones, adaptado al rol}

## Experiencia Profesional

### {Cargo} — {Empresa}
*{Fecha inicio} – {Fecha fin}*
- {Bullet 1, priorizando relevancia al rol}
- {Bullet 2}
- {Bullet 3}

## Educación
...

## Skills
**Técnicas:** ...
**Idiomas:** ...

## Certificaciones
...
```

**Prompt para carta de presentación (Sonnet 4.6):**

```
Sos un asistente que escribe cartas de presentación breves, naturales y
profesionales en español rioplatense para postulaciones laborales en Argentina.

REGLAS:
- 150-200 palabras MÁXIMO
- Tono profesional pero cálido, sin robotización
- NUNCA usar frases hechas tipo "Por medio de la presente", "Adjunto mi CV"
- NUNCA mencionar IA, ChatGPT, Claude, o que la carta fue generada
- Demostrar conocimiento específico del rol (mencionar 1-2 cosas concretas de la oferta)
- Cerrar con disposición a entrevista, sin servilismo

CANDIDATO:
{profile resumen + headline + 2-3 bullets más relevantes}

OFERTA:
Título: {job.title}
Empresa: {job.company}
Descripción: {job.description}

Devolvé SOLO la carta en markdown, sin preámbulo.
```

**Versionado:** si el usuario pide regenerar (botón "Regenerar carta"), creamos un nuevo `generated_materials` con `version + 1`. Nunca pisamos versiones anteriores.

### 4.4 Cola de revisión (Frontend + API)

**Vista principal (Dashboard):**
- Tabla/cards de matches en estado `pending`, ordenados por `fit_score DESC` y `scored_at DESC`.
- Filtros: portal, score mínimo, fecha, search criteria.
- Cada card muestra: título, empresa, ubicación, modalidad, score, badges de strengths/red flags.

**Detalle de match:**
- Panel izquierdo: JD completa con scroll.
- Panel derecho con tabs:
  - Análisis (reasoning, strengths, red flags)
  - CV adaptado (preview PDF + botón descargar + regenerar)
  - Carta (preview PDF + botón descargar + regenerar + copiar texto)
  - Notas (textarea libre)
- Botones de acción al final:
  - **Postular** (abre flow de postulación, ver §4.5)
  - **Marcar como aplicada manualmente** (si el usuario aplicó por afuera)
  - **Descartar** (con razón opcional)

### 4.5 Postulación asistida

**Modos disponibles (configurable por usuario, default = `assisted`):**

#### Modo `assisted` (default, seguro)
1. Usuario clickea "Postular" en frontend.
2. Backend marca `match.status = 'approved'`.
3. Frontend abre nueva pestaña con `job.external_url`.
4. Extensión del navegador (opcional, ver §5) o autofiller manual completa el form.
5. Usuario confirma envío en el portal.
6. Vuelve al dashboard y clickea "Confirmar enviada" → crea `application` row.

#### Modo `scripted` (opt-in, riesgo medio)
Solo para portales con flow conocido y estable. Por usuario hay que activarlo explícitamente y aceptar términos.

Implementación por portal:

**LinkedIn Easy Apply (más sensible):**
- Solo aplica a ofertas con `application_type = 'easy_apply'`.
- Usa la sesión del usuario (`portal_sessions.encrypted_cookies`).
- Cap diario hardcoded: 15 postulaciones/día/usuario.
- Delays: 30-90s entre postulaciones.
- Browser headed por default (visible) para que el usuario pueda intervenir.
- Si encuentra preguntas no respondibles automáticamente (preguntas custom del recruiter), pausa y notifica al usuario.

**Bumeran/ZonaJobs/Computrabajo:**
- Cap diario: 25 postulaciones/día/usuario.
- Delays: 15-45s entre postulaciones.
- Sube CV y carta generados.
- Llena campos custom mapeando contra el perfil del usuario.

**Pseudocódigo del applier worker:**

```python
async def apply_to_job(match_id: UUID):
    match = await get_match(match_id)
    user = await get_user(match.user_id)

    # Verificar caps diarios
    today_count = await count_applications_today(user.id, match.job.source_portal)
    cap = get_daily_cap(match.job.source_portal)
    if today_count >= cap:
        await mark_match_status(match_id, 'queued_for_tomorrow')
        return

    # Obtener materiales
    cv_pdf = await get_material(match_id, type='cv')
    letter_md = await get_material(match_id, type='cover_letter')

    # Cargar sesión del portal
    session = await get_portal_session(user.id, match.job.source_portal)
    if not session or session.status != 'active':
        await notify_user(user.id, 'session_expired', match.job.source_portal)
        return

    # Ejecutar applier específico
    applier = APPLIERS[match.job.source_portal]
    result = await applier.apply(
        external_url=match.job.external_url,
        cv_pdf_path=cv_pdf.pdf_path,
        cover_letter_text=letter_md,
        session_cookies=decrypt(session.encrypted_cookies),
        profile=user.profile
    )

    if result.success:
        await create_application(match_id, channel=result.channel)
        await mark_match_status(match_id, 'applied')
    else:
        await log_failure(match_id, result.error)
        await notify_user(user.id, 'application_failed', match_id)
```

### 4.6 Tracking

**Funnel:**
```
Scrapeadas → Scoreadas → Matches (≥threshold) → Aprobadas → Aplicadas → Respondidas → Entrevistas → Ofertas
```

**Vistas:**
- Dashboard de funnel (numbers + conversion rates por etapa).
- Lista de aplicaciones con timeline (aplicada → respuesta → entrevista → ...).
- Performance por portal (cuál tiene mejor response rate).
- Por search criteria (cuál estrategia está rindiendo).

**Updates de status:**
- Manual desde frontend (usuario marca "Me llamaron", "Me rechazaron", etc.).
- Auto-detección opcional (Fase 3): scrapear inbox de mail del usuario buscando respuestas (requiere OAuth de Gmail/Outlook). Por ahora omitido.

---

## 5. API REST

Convención: prefijo `/api/v1`. Auth via `Authorization: Bearer <jwt>`.

### Auth
- `POST /auth/register` (solo admin puede crear usuarios en MVP)
- `POST /auth/login` → `{access_token, refresh_token}`
- `POST /auth/refresh`
- `POST /auth/logout`
- `GET /auth/me`

### Profile
- `GET /profile`
- `PUT /profile` (campos personales)
- `POST /profile/cv` (upload PDF, parsea con LLM y devuelve `cv_base_json` para editar)
- `PUT /profile/cv` (guardar `cv_base_json` editado)

### Search Criteria
- `GET /criteria`
- `POST /criteria`
- `PUT /criteria/{id}`
- `DELETE /criteria/{id}`
- `POST /criteria/{id}/run` (dispara scrape inmediato)

### Portal Sessions
- `GET /portals/sessions` (listar portales conectados)
- `POST /portals/sessions/{portal}` (subir cookies exportadas o flow guiado)
- `DELETE /portals/sessions/{portal}`

### Jobs y Matches
- `GET /matches?status=pending&portal=linkedin&min_score=70&limit=20&offset=0`
- `GET /matches/{id}` (detalle con job + materiales)
- `POST /matches/{id}/approve`
- `POST /matches/{id}/reject` (body: `{reason}`)
- `POST /matches/{id}/apply` (encola applier)
- `POST /matches/{id}/mark-applied` (manual, sin script)
- `POST /matches/{id}/regenerate-cv`
- `POST /matches/{id}/regenerate-letter`
- `PUT /matches/{id}/status` (update libre: 'responded', 'interview', etc.)

### Tracking
- `GET /tracking/funnel?from=2026-01-01&to=2026-12-31`
- `GET /tracking/applications`
- `GET /tracking/by-portal`

### Admin (solo `role=admin`)
- `GET /admin/users`
- `POST /admin/users` (crear usuario)
- `PUT /admin/users/{id}` (activar/desactivar, cambiar rol)
- `GET /admin/stats` (uso global del sistema)
- `GET /admin/audit-log`

---

## 6. Frontend

### 6.1 Estructura de páginas

```
/login
/onboarding
  /onboarding/cv
  /onboarding/criteria
  /onboarding/portals
/dashboard                      ← cola de matches pendientes
/matches/:id                    ← detalle de match
/tracking                       ← funnel y aplicaciones
/settings
  /settings/profile
  /settings/criteria
  /settings/portals
  /settings/notifications
/admin                          ← solo admin
  /admin/users
  /admin/stats
```

### 6.2 Componentes clave

- `<MatchCard>`: card en dashboard con score badge color-coded (verde 80+, amarillo 60-79, gris <60).
- `<JobDescription>`: render markdown del JD con highlight automático de keywords del perfil.
- `<MaterialPreview>`: viewer de PDF + botones (descargar, regenerar, copiar texto).
- `<FunnelChart>`: visualización del funnel con Recharts.
- `<PortalConnector>`: flow para subir cookies de un portal (instrucciones paso a paso + drag&drop de archivo de cookies exportado).

### 6.3 Stack frontend

- React 18 + TypeScript + Vite
- TailwindCSS + shadcn/ui
- React Query para fetching/caching
- React Router v6
- Recharts para gráficos
- React Hook Form + Zod para forms
- date-fns en español

---

## 7. Multi-tenancy y seguridad

### 7.1 Aislamiento de datos
- **Toda query filtrada por `user_id`** vía dependencia FastAPI:
  ```python
  async def get_current_user(token: str = Depends(oauth2_scheme)) -> User: ...

  async def get_user_or_403(
      user_id: UUID,
      current: User = Depends(get_current_user)
  ) -> User:
      if current.role != 'admin' and current.id != user_id:
          raise HTTPException(403)
      return current
  ```
- Tests obligatorios: cada endpoint debe tener un test que verifique que User A no puede acceder a recursos de User B.

### 7.2 Encriptación de datos sensibles
- **Cookies de portales**: Fernet con clave maestra en env (`MASTER_ENCRYPTION_KEY`). Nunca en logs.
- **Credenciales de portales** (si el usuario las guarda): mismo esquema. Default: NO guardar credenciales, solo cookies.
- **CVs**: en MinIO con bucket por usuario y políticas de acceso restrictivo.

### 7.3 LLM y datos personales
- Anthropic API: Anthropic NO entrena con datos de la API por default. Igual, en system prompts NUNCA incluir DNI, dirección exacta, teléfono. El nombre y email son OK porque son datos profesionales que ya están en el CV.

### 7.4 Rate limiting
- Por usuario: 100 req/min al API en general, 10/min en endpoints de scoring/generación.
- Por IP: 1000 req/min.
- Implementar con `slowapi` (FastAPI).

### 7.5 Audit log
Toda acción sensible loggeada:
- Login/logout
- Cambio de profile/CV
- Postulación enviada
- Cambio de credenciales de portal
- Acciones admin

### 7.6 Compliance con ToS de portales
- LinkedIn: cap estricto, delays humanos, NO scrape de perfiles (solo jobs públicos), respetar rate limits, robots.txt.
- Documentar claramente al usuario el riesgo de baneo y obtener consentimiento explícito.
- Disclaimer en T&C de la plataforma.

---

## 8. Deployment

### 8.1 docker-compose.yml (estructura)

```yaml
services:
  api:
    build: ./backend
    command: uvicorn app.main:app --host 0.0.0.0 --port 8000
    environment: [...]
    depends_on: [postgres, redis, minio]

  worker-scraper:
    build: ./backend
    command: celery -A app.celery worker -Q scrape -c 4
    depends_on: [postgres, redis]

  worker-scoring:
    build: ./backend
    command: celery -A app.celery worker -Q scoring -c 8

  worker-generator:
    build: ./backend
    command: celery -A app.celery worker -Q generation -c 4

  worker-applier:
    build: ./backend
    command: celery -A app.celery worker -Q apply -c 2  # baja concurrencia

  beat:
    build: ./backend
    command: celery -A app.celery beat

  web:
    build: ./frontend
    ports: ["80:80"]

  postgres:
    image: postgres:16
    volumes: [pgdata:/var/lib/postgresql/data]

  redis:
    image: redis:7-alpine

  minio:
    image: minio/minio
    command: server /data --console-address ":9001"
    volumes: [miniodata:/data]
```

### 8.2 Variables de entorno (`.env.example`)

```
DATABASE_URL=postgresql://...
REDIS_URL=redis://redis:6379/0
ANTHROPIC_API_KEY=sk-...
MASTER_ENCRYPTION_KEY=<base64>
JWT_SECRET=<random>
MINIO_ENDPOINT=minio:9000
MINIO_ACCESS_KEY=...
MINIO_SECRET_KEY=...
SENTRY_DSN=...
ENVIRONMENT=production
```

### 8.3 CI/CD (GitHub Actions)
Reusar el patrón que ya tenés:
- `test.yml`: pytest + ruff + mypy en PRs
- `deploy.yml`: build + push imágenes + ssh deploy en merge a `main`

---

## 9. Roadmap de implementación

### Fase 1 — MVP (2 semanas)
**Objetivo:** un usuario (Luciana) recibiendo matches diarios de Bumeran y Computrabajo con cartas generadas.

- [ ] Setup repo, Docker Compose, CI básico
- [ ] Modelo de datos + migrations
- [ ] Auth (JWT)
- [ ] CRUD básico de profile + criteria
- [ ] Onboarding: subir CV PDF → parseo a JSON con LLM → editar
- [ ] Scrapers: Bumeran + Computrabajo
- [ ] Worker de scoring con Haiku
- [ ] Worker de generación (solo carta, sin CV adaptado en F1)
- [ ] Frontend básico: login, dashboard, detalle de match
- [ ] Modo `assisted` only (redirect a portal)

### Fase 2 — Producción multi-usuario (3 semanas)
**Objetivo:** 5 usuarios usándolo, todos los portales, CV adaptado.

- [ ] Scrapers: ZonaJobs, LinkedIn (RSS + Playwright cuidadoso), Clarín, Portal Empleo BA
- [ ] Generación de CV adaptado (PDF con WeasyPrint)
- [ ] Tracking completo (funnel, métricas por portal)
- [ ] Admin: gestión de usuarios
- [ ] Notificaciones (email + opcional WhatsApp via Twilio)
- [ ] Tests completos (pytest, >80% coverage en módulos críticos)

### Fase 3 — Power features (opcional, 2-3 semanas)
- [ ] Modo `scripted` para Bumeran/ZonaJobs/Computrabajo
- [ ] LinkedIn Easy Apply scripted (con caps estrictos)
- [ ] Auto-detección de respuestas (OAuth Gmail)
- [ ] A/B testing de cartas
- [ ] Recomendaciones de mejora del CV base ("este perfil rindió mejor con X")
- [ ] Telegram bot para approvals desde el celular

---

## 10. Anexo: estructura de carpetas sugerida

```
jobhunter/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── config.py
│   │   ├── celery.py
│   │   ├── auth/
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── routers/
│   │   │   ├── auth.py
│   │   │   ├── profile.py
│   │   │   ├── criteria.py
│   │   │   ├── matches.py
│   │   │   ├── tracking.py
│   │   │   └── admin.py
│   │   ├── services/
│   │   │   ├── llm.py            # cliente Anthropic
│   │   │   ├── scoring.py
│   │   │   ├── generator.py
│   │   │   └── encryption.py
│   │   ├── scrapers/
│   │   │   ├── base.py
│   │   │   ├── bumeran.py
│   │   │   ├── zonajobs.py
│   │   │   ├── computrabajo.py
│   │   │   ├── linkedin.py
│   │   │   ├── clarin.py
│   │   │   └── portal_empleo_ba.py
│   │   ├── appliers/
│   │   │   ├── base.py
│   │   │   ├── linkedin.py
│   │   │   ├── bumeran.py
│   │   │   └── ...
│   │   └── workers/
│   │       ├── scrape_tasks.py
│   │       ├── score_tasks.py
│   │       ├── generate_tasks.py
│   │       └── apply_tasks.py
│   ├── alembic/
│   ├── tests/
│   ├── pyproject.toml
│   └── Dockerfile
├── frontend/
│   ├── src/
│   │   ├── pages/
│   │   ├── components/
│   │   ├── hooks/
│   │   ├── lib/
│   │   └── App.tsx
│   ├── package.json
│   ├── vite.config.ts
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
├── README.md
└── .github/workflows/
```

---

## 11. Notas finales para Claude Code

1. **Empezar siempre por la Fase 1.** No avanzar a Fase 2 hasta que el MVP corra end-to-end con un usuario.
2. **No implementar scrapers como primera tarea.** Antes: modelo de datos, auth, profile, criteria, frontend básico. Los scrapers son los más frágiles y conviene tener el resto estable primero.
3. **Tests de seguridad multi-tenant son obligatorios.** Cada endpoint que reciba `user_id` debe tener test de cross-tenant access.
4. **Anthropic API:** usar el SDK oficial `anthropic-sdk-python`, modelo `claude-haiku-4-5-20251001` para scoring y `claude-sonnet-4-6` para generación. Wrappear en `app/services/llm.py` con retry exponencial.
5. **Playwright en Docker:** usar `mcr.microsoft.com/playwright/python:v1.x-jammy` como base de los workers que usan browser. Headless por default; headed solo en modo `scripted` con `xvfb`.
6. **Encriptación:** usar `cryptography.fernet` con la `MASTER_ENCRYPTION_KEY`. Rotación de clave: implementar comando admin para re-encriptar todo si hay leak.
7. **Logs:** structlog en JSON, nunca loggear tokens, cookies, ni contenido completo de CVs.
8. **Sentry:** integrar desde día uno para capturar excepciones en workers (los errores en Celery son fáciles de perder).

---

**Fin del spec.**
