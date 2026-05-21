"""Shared helper: render a JSON Resume object to markdown.

Used by the profile download endpoint to produce a .docx from the structured CV.
Format matches what the LLM emits in `app/services/generator.py`.
"""

from __future__ import annotations


def cv_json_to_markdown(cv: dict) -> str:
    lines: list[str] = []
    basics = cv.get("basics") or {}
    name = basics.get("name", "")
    label = basics.get("label", "")
    if name:
        lines.append(f"# {name}")
    if label:
        lines.append(f"**{label}**")
    contact_bits = [
        basics.get("email"),
        basics.get("phone"),
        ", ".join(
            x for x in [
                (basics.get("location") or {}).get("city"),
                (basics.get("location") or {}).get("countryCode"),
            ] if x
        )
        or None,
        basics.get("url"),
    ]
    contact_line = " | ".join(b for b in contact_bits if b)
    if contact_line:
        lines.append("")
        lines.append(contact_line)

    if basics.get("summary"):
        lines.append("")
        lines.append("## Resumen Profesional")
        lines.append(basics["summary"])

    work = cv.get("work") or []
    if work:
        lines.append("")
        lines.append("## Experiencia Profesional")
        for w in work:
            position = w.get("position", "")
            company = w.get("company", "") or w.get("name", "")
            start = w.get("startDate", "")
            end = w.get("endDate", "actual")
            lines.append("")
            lines.append(f"### {position} — {company}")
            if start or end:
                lines.append(f"*{start} – {end}*")
            for h in w.get("highlights") or []:
                lines.append(f"- {h}")

    edu = cv.get("education") or []
    if edu:
        lines.append("")
        lines.append("## Educación")
        for e in edu:
            inst = e.get("institution", "")
            study = e.get("studyType", "")
            area = e.get("area", "")
            start = e.get("startDate", "")
            end = e.get("endDate", "")
            head = " — ".join(x for x in [study, area, inst] if x)
            lines.append(f"### {head}")
            if start or end:
                lines.append(f"*{start} – {end}*")

    skills = cv.get("skills") or []
    if skills:
        lines.append("")
        lines.append("## Skills")
        for s in skills:
            n = s.get("name", "")
            kws = ", ".join(s.get("keywords") or [])
            if n and kws:
                lines.append(f"**{n}:** {kws}")
            elif n:
                lines.append(f"- {n}")

    langs = cv.get("languages") or []
    if langs:
        lines.append("")
        lines.append("## Idiomas")
        for la in langs:
            n = la.get("language", "")
            fl = la.get("fluency", "")
            lines.append(f"- {n}{f' — {fl}' if fl else ''}")

    certs = cv.get("certifications") or []
    if certs:
        lines.append("")
        lines.append("## Certificaciones")
        for c in certs:
            n = c.get("name", "")
            iss = c.get("issuer", "")
            date = c.get("date", "")
            tail = " — ".join(x for x in [iss, date] if x)
            lines.append(f"- {n}{f' ({tail})' if tail else ''}")

    return "\n".join(lines)
