"""Score a job against a user profile using Claude Haiku."""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from app.config import get_settings
from app.services.llm import complete

_SYSTEM = """Sos un asistente de búsqueda laboral experto en el mercado argentino.
Tu trabajo es evaluar el fit entre un perfil profesional y una oferta de empleo,
devolviendo un score 0-100 y razonamiento conciso.

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
{
  "fit_score": <int 0-100>,
  "reasoning": "<2-3 oraciones>",
  "strengths": ["<hasta 3 razones>"],
  "red_flags": ["<motivos de duda o descarte>"],
  "recommended_action": "apply" | "review" | "skip"
}
"""


def _summarize_profile(profile: dict[str, Any], criteria: dict[str, Any]) -> str:
    cv = profile.get("cv_base_json", {}) or {}
    work = cv.get("work", []) or []
    work_brief = "\n".join(
        f"- {w.get('position', '')} en {w.get('company', '')} "
        f"({w.get('startDate', '')} a {w.get('endDate', 'actual')})"
        for w in work[:6]
    )
    return f"""PERFIL DEL CANDIDATO:
- Nombre: {profile.get('full_name', '')}
- Headline: {profile.get('headline', '')}
- Ubicación: {profile.get('current_location', '')}
- Años de experiencia: {profile.get('years_experience', '')}
- Resumen: {profile.get('about_text', '')}
- Experiencia laboral:
{work_brief}
- Educación: {json.dumps(cv.get('education', []), ensure_ascii=False)}
- Skills: {json.dumps(cv.get('skills', []), ensure_ascii=False)}
- Idiomas: {json.dumps(cv.get('languages', []), ensure_ascii=False)}

CRITERIOS:
- Títulos preferidos: {profile.get('preferred_titles')}
- Empresas excluidas: {profile.get('excluded_companies')}
- Keywords descalificantes: {profile.get('excluded_keywords')}
- Modalidades aceptadas: {criteria.get('modalities')}
- Salario mínimo: {criteria.get('salary_min_ars')} ARS
"""


async def score_job(
    profile: dict[str, Any],
    criteria: dict[str, Any],
    job: dict[str, Any],
    *,
    user_id: UUID | None = None,
) -> dict[str, Any]:
    """Return parsed scoring JSON."""
    settings = get_settings()
    system = _SYSTEM + "\n\n" + _summarize_profile(profile, criteria)
    user = f"""OFERTA:
- Título: {job.get('title', '')}
- Empresa: {job.get('company', '')}
- Ubicación: {job.get('location', '')}
- Modalidad: {job.get('modality', '')}
- Descripción:
{job.get('description', '')}
"""
    raw = await complete(
        model=settings.llm_model_scoring,
        system=system,
        user=user,
        max_tokens=600,
        temperature=0.2,
        cache_system=True,
        user_id=user_id,
        purpose="scoring",
    )
    if raw.startswith("```"):
        raw = raw.strip("`").lstrip("json").strip()
    return json.loads(raw)
