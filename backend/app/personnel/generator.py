"""docx generation engine (ТЗ §6).

Thin wrapper over docxtpl: load a template from the module's `templates/`
directory, render it with a nested context, return the bytes. No docx is built
from code — the accountant edits the .docx in Word and the engine only fills
placeholders.
"""
from __future__ import annotations

from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Optional

TEMPLATES_DIR = Path(__file__).parent / "templates"


def render_template(template_filename: str, context: dict) -> BytesIO:
    """Render `templates/<template_filename>` with `context` and return an
    in-memory .docx (BytesIO positioned at 0)."""
    from docxtpl import DocxTemplate

    path = TEMPLATES_DIR / template_filename
    if not path.is_file():
        raise FileNotFoundError(f"Шаблон не найден: {template_filename}")

    tpl = DocxTemplate(str(path))
    tpl.render(context)
    buffer = BytesIO()
    tpl.save(buffer)
    buffer.seek(0)
    return buffer


def _initials(first: str, middle: str) -> str:
    out = ""
    if first:
        out += first.strip()[:1].upper()
    if middle:
        out += middle.strip()[:1].upper()
    return out


def output_filename(last_name: str, first_name: str, middle_name: str,
                    doc_label: str, on: Optional[date] = None) -> str:
    """'Иванов_ИИ_ПриказПриём_2026-08-05.docx' (ТЗ §6)."""
    stamp = (on or date.today()).isoformat()
    initials = _initials(first_name, middle_name)
    return f"{last_name}_{initials}_{doc_label}_{stamp}.docx"
