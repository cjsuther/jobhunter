"""Parse uploaded CV PDF to JSON Resume format via Sonnet."""

from __future__ import annotations

import base64
import json
from typing import Any
from uuid import UUID

from app.config import get_settings
from app.services.llm import complete

_SYSTEM = """Sos un asistente que extrae estructura de un CV en PDF y la
devuelve en formato JSON Resume (https://jsonresume.org/schema).

REGLAS:
- NO inventes información que no esté en el PDF.
- Si un campo no figura, omitilo o dejalo como string vacío/array vacío.
- Devolvé SOLO JSON válido, sin markdown ni explicaciones.

Estructura mínima esperada:
{
  "basics": {"name", "label", "email", "phone", "location": {"city", "countryCode"}, "summary"},
  "work": [{"company", "position", "startDate", "endDate", "highlights": [], "keywords": []}],
  "education": [{"institution", "studyType", "area", "startDate", "endDate"}],
  "skills": [{"name", "keywords": []}],
  "languages": [{"language", "fluency"}],
  "certifications": []
}
"""


async def parse_cv_pdf(pdf_bytes: bytes, *, user_id: UUID | None = None) -> dict[str, Any]:
    """Send the PDF to the LLM and return the parsed CV JSON.

    Uses the Anthropic file input API (base64-encoded PDF document content block).
    """
    settings = get_settings()
    b64 = base64.b64encode(pdf_bytes).decode("ascii")
    user_content = [
        {
            "type": "document",
            "source": {"type": "base64", "media_type": "application/pdf", "data": b64},
        },
        {"type": "text", "text": "Extraé el CV a JSON Resume."},
    ]
    raw = await complete(
        model=settings.llm_model_generation,
        system=_SYSTEM,
        user=user_content,
        max_tokens=4096,
        temperature=0.1,
        user_id=user_id,
        purpose="cv_parse",
    )
    raw = raw.strip()
    # Strip possible code fences just in case.
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:].strip()
    return json.loads(raw)
