"""Base interface for portal-specific appliers (Fase 3 — scripted apply)."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass
class ApplyResult:
    success: bool
    channel: str
    error: str | None = None
    extra: dict[str, Any] | None = None


class BaseApplier(ABC):
    portal_name: str = "base"

    @abstractmethod
    async def apply(
        self,
        *,
        external_url: str,
        cv_pdf_path: str,
        cover_letter_text: str,
        session_cookies: dict[str, str],
        profile: Any,
    ) -> ApplyResult:
        ...
