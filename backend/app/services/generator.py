"""Generate adapted CV and cover letter for a match."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.config import get_settings
from app.services.llm import complete

_CV_SYSTEM = """Sos un experto en redacción de CVs para el mercado laboral
argentino. Tu trabajo es ADAPTAR un CV base a una oferta específica, SIN INVENTAR
información. Solo podés:
- Reordenar bullets de experiencia para destacar los más relevantes
- Reformular bullets para resaltar palabras clave de la oferta (sin mentir)
- Ajustar el resumen profesional al rol específico
- Reordenar skills para poner primero los relevantes

NUNCA agregues experiencia, títulos o skills que no estén en el CV base.

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
"""

_LETTER_SYSTEM = """Sos un asistente que escribe cartas de presentación breves,
naturales y profesionales en español rioplatense para postulaciones laborales en
Argentina.

REGLAS:
- 150-200 palabras MÁXIMO
- Tono profesional pero cálido, sin robotización
- NUNCA usar frases hechas tipo "Por medio de la presente", "Adjunto mi CV"
- NUNCA mencionar IA, ChatGPT, Claude, o que la carta fue generada
- Demostrar conocimiento específico del rol (mencionar 1-2 cosas concretas de la oferta)
- Cerrar con disposición a entrevista, sin servilismo

Devolvé SOLO la carta en markdown, sin preámbulo.
"""


async def generate_cv_markdown(
    profile: dict[str, Any], job: dict[str, Any], *, user_id: UUID | None = None
) -> str:
    settings = get_settings()
    user = f"""CV BASE (JSON):
{json.dumps(profile.get('cv_base_json', {}), ensure_ascii=False, indent=2)}

OFERTA:
Título: {job.get('title', '')}
Empresa: {job.get('company', '')}
Descripción: {job.get('description', '')}
"""
    return await complete(
        model=settings.llm_model_generation,
        system=_CV_SYSTEM,
        user=user,
        max_tokens=2500,
        temperature=0.5,
        user_id=user_id,
        purpose="cv_generation",
    )


async def generate_cover_letter(
    profile: dict[str, Any], job: dict[str, Any], *, user_id: UUID | None = None
) -> str:
    settings = get_settings()
    cv = profile.get("cv_base_json", {}) or {}
    work = cv.get("work", []) or []
    top_bullets: list[str] = []
    for w in work[:2]:
        for h in (w.get("highlights") or [])[:2]:
            top_bullets.append(f"- {h}")
    user = f"""CANDIDATO:
- Nombre: {profile.get('full_name', '')}
- Headline: {profile.get('headline', '')}
- Resumen: {profile.get('about_text', '')}
- Highlights más relevantes:
{chr(10).join(top_bullets)}

OFERTA:
Título: {job.get('title', '')}
Empresa: {job.get('company', '')}
Descripción: {job.get('description', '')}
"""
    return await complete(
        model=settings.llm_model_generation,
        system=_LETTER_SYSTEM,
        user=user,
        max_tokens=600,
        temperature=0.7,
        user_id=user_id,
        purpose="letter_generation",
    )
