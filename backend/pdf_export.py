"""PDF export for the curriculum, content plan and assessments.

ReportLab's built-in Type-1 fonts are Latin-1 only, and agent output routinely contains
arrows, em-dashes and curly quotes. Rather than shipping a TTF, `_clean()` maps the
characters that actually show up and drops anything else unmappable — a PDF with a plain
hyphen beats one with black boxes or a UnicodeEncodeError mid-render.
"""

from __future__ import annotations

import html
from datetime import datetime, timezone
from io import BytesIO
from typing import Any

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from backend.schemas import ProgrammeState

# --------------------------------------------------------------------------- text
_REPLACEMENTS = {
    "→": "->", "←": "<-", "↔": "<->", "⇒": "=>",
    "–": "-", "—": " - ", "−": "-",
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "•": "-", "·": "-", "…": "...",
    "≥": ">=", "≤": "<=", "×": "x", "✓": "v", "✗": "x",
    " ": " ", "​": "",
}


def _clean(value: Any) -> str:
    """Make arbitrary agent output safe for a Latin-1 PDF font, and for XML markup."""
    if value is None:
        return ""
    text = str(value)
    for bad, good in _REPLACEMENTS.items():
        text = text.replace(bad, good)
    # Drop anything still outside Latin-1 rather than crashing the render.
    text = text.encode("latin-1", "replace").decode("latin-1").replace("?", "?")
    return html.escape(text, quote=False)


# ------------------------------------------------------------------------- styles
_SS = getSampleStyleSheet()
TITLE = ParagraphStyle("t", parent=_SS["Title"], fontSize=19, spaceAfter=2, leading=23)
SUBTITLE = ParagraphStyle("st", parent=_SS["Normal"], fontSize=9,
                          textColor=colors.HexColor("#5b6672"), spaceAfter=12)
H2 = ParagraphStyle("h2", parent=_SS["Heading2"], fontSize=13, spaceBefore=14,
                    spaceAfter=6, textColor=colors.HexColor("#1f4e79"))
H3 = ParagraphStyle("h3", parent=_SS["Heading3"], fontSize=11, spaceBefore=9, spaceAfter=3)
BODY = ParagraphStyle("b", parent=_SS["Normal"], fontSize=9.5, leading=13.5,
                      alignment=TA_LEFT, spaceAfter=3)
META = ParagraphStyle("m", parent=BODY, fontSize=8.5,
                      textColor=colors.HexColor("#5b6672"), spaceAfter=5)
BULLET = ParagraphStyle("bu", parent=BODY, leftIndent=11, bulletIndent=2, spaceAfter=2)
NOTE = ParagraphStyle("n", parent=BODY, fontSize=8.5, textColor=colors.HexColor("#8a5a00"))

_TABLE = TableStyle([
    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef2f6")),
    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1f4e79")),
    ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
    ("FONTSIZE", (0, 0), (-1, -1), 8.5),
    ("VALIGN", (0, 0), (-1, -1), "TOP"),
    ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#c9d3dd")),
    ("LEFTPADDING", (0, 0), (-1, -1), 5),
    ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ("TOPPADDING", (0, 0), (-1, -1), 3),
    ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
])


def _bullets(items: list, style: ParagraphStyle = BULLET) -> list:
    return [Paragraph(_clean(i), style, bulletText="-") for i in items if str(i).strip()]


def _footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 7.5)
    canvas.setFillColor(colors.HexColor("#8b98a5"))
    canvas.drawString(
        18 * mm, 12 * mm,
        "AI-generated draft - requires human review before use. Not a final business decision.",
    )
    canvas.drawRightString(A4[0] - 18 * mm, 12 * mm, f"Page {canvas.getPageNumber()}")
    canvas.restoreState()


def _document(buffer: BytesIO, title: str) -> SimpleDocTemplate:
    return SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=18 * mm, rightMargin=18 * mm,
        topMargin=16 * mm, bottomMargin=20 * mm,
        title=title, author="AI Learning Academy",
    )


def _header(state: ProgrammeState, doc_title: str, subtitle: str = "") -> list:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    bits = [
        f"Run {state.run_id}",
        f"status: {state.status}",
        f"revisions: {state.revision_count}",
        f"generated {stamp}",
    ]
    flow = [Paragraph(_clean(doc_title), TITLE)]
    if subtitle:
        flow.append(Paragraph(_clean(subtitle), SUBTITLE))
    flow += [
        Paragraph(_clean(" | ".join(bits)), META),
        Paragraph("<b>Manager request:</b> " + _clean(state.manager_request), BODY),
        Spacer(1, 6),
    ]
    return flow


def _render(state: ProgrammeState, doc_title: str, subtitle: str, body: list) -> bytes:
    buffer = BytesIO()
    doc = _document(buffer, doc_title)
    doc.build(_header(state, doc_title, subtitle) + body,
              onFirstPage=_footer, onLaterPages=_footer)
    return buffer.getvalue()


# ---------------------------------------------------------------------- documents
def curriculum_pdf(state: ProgrammeState) -> bytes:
    c = state.curriculum or {}
    modules = c.get("modules") or []
    flow: list = []

    flow.append(Paragraph("Programme overview", H2))
    rows = [["Modules", "Total hours", "Pathways"],
            [str(len(modules)), str(c.get("total_duration_hours", "-")),
             str(len(c.get("pathways") or {}))]]
    table = Table(rows, colWidths=[45 * mm, 45 * mm, 84 * mm])
    table.setStyle(_TABLE)
    flow += [table, Spacer(1, 8)]

    if c.get("sequencing_rationale"):
        flow += [Paragraph("Sequencing rationale", H3),
                 Paragraph(_clean(c["sequencing_rationale"]), BODY)]

    pathways = c.get("pathways") or {}
    if pathways:
        flow.append(Paragraph("Learner pathways", H2))
        prows = [["Pathway", "Module sequence"]]
        prows += [[_clean(name), _clean(" -> ".join(ids or []))] for name, ids in pathways.items()]
        pt = Table([[Paragraph(cell, BODY) for cell in r] for r in prows],
                   colWidths=[48 * mm, 126 * mm])
        pt.setStyle(_TABLE)
        flow += [pt, Spacer(1, 6)]

    flow.append(Paragraph("Modules", H2))
    for m in modules:
        block = [
            Paragraph(f"{_clean(m.get('module_id'))} - {_clean(m.get('title'))}", H3),
            Paragraph(_clean(
                f"{m.get('duration_hours', '-')}h | level: {m.get('target_level', '-')} | "
                f"pathway: {m.get('pathway', 'all')} | mode: {m.get('delivery_mode', '-')} | "
                f"topic: {m.get('topic', '-')} | "
                f"prerequisites: {', '.join(m.get('prerequisites') or []) or 'none'}"
            ), META),
        ]
        block += _bullets(m.get("learning_objectives") or [])
        flow.append(KeepTogether(block))

    return _render(state, "Curriculum",
                   c.get("programme_title", "AI Upskilling Programme"), flow)


def content_plan_pdf(state: ProgrammeState) -> bytes:
    cp = state.content_plan or {}
    titles = {m.get("module_id"): m.get("title")
              for m in (state.curriculum or {}).get("modules") or []}
    modules = cp.get("modules") or []
    gaps = [m for m in modules if m.get("gap")]
    flow: list = []

    flow.append(Paragraph("Reuse summary", H2))
    if cp.get("reuse_summary"):
        flow.append(Paragraph(_clean(cp["reuse_summary"]), BODY))
    rows = [["Modules", "Reuse existing", "Content gaps", "Library chunks searched", "Top-k"],
            [str(len(modules)), str(len(modules) - len(gaps)), str(len(gaps)),
             str(cp.get("library_chunks_searched", "-")), str(cp.get("top_k", "-"))]]
    table = Table(rows, colWidths=[26 * mm, 34 * mm, 30 * mm, 50 * mm, 34 * mm])
    table.setStyle(_TABLE)
    flow += [table, Spacer(1, 8), Paragraph("Per-module mapping", H2)]

    for m in modules:
        mid = m.get("module_id")
        label = titles.get(mid) or m.get("module_title") or ""
        badge = "CONTENT GAP" if m.get("gap") else "REUSE EXISTING"
        block = [
            Paragraph(f"{_clean(mid)} - {_clean(label)}  [{badge}]", H3),
        ]
        materials = m.get("recommended_materials") or []
        if materials:
            mrows = [["Source", "Topic / level", "Why relevant"]]
            for r in materials:
                mrows.append([
                    Paragraph(_clean(r.get("source")), BODY),
                    Paragraph(_clean(f"{r.get('topic', '-')} / {r.get('level', '-')}"), BODY),
                    Paragraph(_clean(r.get("why_relevant")), BODY),
                ])
            header = [Paragraph(f"<b>{h}</b>", BODY) for h in mrows[0]]
            mt = Table([header] + mrows[1:], colWidths=[46 * mm, 30 * mm, 98 * mm])
            mt.setStyle(_TABLE)
            block.append(mt)
        else:
            block.append(Paragraph("No suitable existing material was retrieved.", META))
        if m.get("gap_note"):
            block.append(Paragraph("<b>Gap:</b> " + _clean(m["gap_note"]), NOTE))
        flow += [KeepTogether(block), Spacer(1, 4)]

    backlog = cp.get("content_gaps") or []
    if backlog:
        flow += [Paragraph(f"Authoring backlog ({len(backlog)} items)", H2)]
        flow += _bullets(backlog)

    return _render(state, "Content Plan",
                   (state.curriculum or {}).get("programme_title", ""), flow)


def assessments_pdf(state: ProgrammeState) -> bytes:
    a = state.assessments or {}
    titles = {m.get("module_id"): m.get("title")
              for m in (state.curriculum or {}).get("modules") or []}
    per_module = a.get("per_module") or []
    flow: list = []

    if a.get("certification_note"):
        flow += [Paragraph("Certification", H2),
                 Paragraph(_clean(a["certification_note"]), BODY)]

    flow.append(Paragraph("Assessments by module", H2))
    for entry in per_module:
        mid = entry.get("module_id")
        block = [Paragraph(f"{_clean(mid)} - {_clean(titles.get(mid, ''))}", H3)]

        for n, q in enumerate(entry.get("quiz") or [], 1):
            block.append(Paragraph(f"<b>Q{n}.</b> " + _clean(q.get("question")), BODY))
            for opt in q.get("options") or []:
                marker = "[x]" if str(opt) == str(q.get("answer")) else "[ ]"
                block.append(Paragraph(f"{marker} {_clean(opt)}", BULLET))
            if q.get("rationale"):
                block.append(Paragraph("<i>" + _clean(q["rationale"]) + "</i>", META))

        ex = entry.get("coding_exercise") or {}
        if ex:
            block.append(Paragraph("Coding exercise: " + _clean(ex.get("title")), H3))
            if ex.get("brief"):
                block.append(Paragraph(_clean(ex["brief"]), BODY))
            if ex.get("estimated_minutes"):
                block.append(Paragraph(_clean(f"Estimated: {ex['estimated_minutes']} minutes"), META))
            criteria = ex.get("acceptance_criteria") or []
            if criteria:
                block.append(Paragraph("Acceptance criteria:", META))
                block += _bullets(criteria)

        rubric = entry.get("practical_rubric") or []
        if rubric:
            levels: list[str] = []
            for r in rubric:
                for k in (r.get("levels") or {}):
                    if k not in levels:
                        levels.append(k)
            rows = [["Criterion"] + [l.title() for l in levels]]
            for r in rubric:
                lv = r.get("levels") or {}
                rows.append([_clean(r.get("criterion"))] + [_clean(lv.get(l, "")) for l in levels])
            widths = [40 * mm] + [(134 * mm / max(1, len(levels)))] * len(levels)
            header_row = [Paragraph(f"<b>{c}</b>", BODY) for c in rows[0]]
            body_rows = [[Paragraph(c, BODY) for c in row] for row in rows[1:]]
            rt = Table([header_row] + body_rows, colWidths=widths)
            rt.setStyle(_TABLE)
            block += [Paragraph("Practical rubric", H3), rt]

        flow += [KeepTogether(block), Spacer(1, 6)]

    return _render(state, "Assessments",
                   (state.curriculum or {}).get("programme_title", ""), flow)


EXPORTS = {
    "curriculum": ("curriculum", curriculum_pdf),
    "content_plan": ("content_plan", content_plan_pdf),
    "assessments": ("assessments", assessments_pdf),
}
