from __future__ import annotations

from io import BytesIO

from app.customer_intelligence.renderer import (
    render_docx,
    render_html,
    render_markdown,
    render_pdf,
)

SECTIONS = {
    "executive_summary": "Acme is ready for a discovery meeting.",
    "company_overview": [{
        "canonical_name": "Acme Corporation",
        "aliases": ["Acme"],
        "industry": "Manufacturing",
        "products": ["Industrial systems"],
        "domain": "acme.example",
    }],
    "recent_news": [{
        "title": "Acme expands",
        "url": "https://acme.example/news",
        "published_date": "2026-08-14",
        "excerpt": "Acme announced an expansion.",
    }],
    "contact_information": [{"name": "Alex", "role": "Buyer", "email": "alex@acme.example"}],
    "upcoming_meetings": [{
        "title": "Acme discovery",
        "start_at": "2026-08-20T10:00:00+00:00",
        "attendees": ["alex@acme.example"],
        "match_type": "confirmed_match",
    }],
    "open_questions": ["Confirm the agenda."],
    "sources": [{
        "title": "Acme About",
        "url": "https://acme.example/about",
        "publisher": "Acme",
        "published_date": "2026-08-13",
        "excerpt": "Company source.",
    }],
}


def test_html_renderer_has_stable_sections_and_escapes_values() -> None:
    html = render_html(SECTIONS)

    assert html.startswith("<!doctype html>")
    for heading in ("Executive Summary", "Company Overview", "Recent News", "Contact Information", "Upcoming Meetings", "Open Questions", "Sources"):
        assert f"<h2>{heading}</h2>" in html
    assert "Acme Corporation" in html
    assert "https://acme.example/about" in html
    assert "<script>" not in render_html({"executive_summary": "<script>alert(1)</script>"})


def test_pdf_and_docx_renderers_preserve_report_text() -> None:
    pdf = render_pdf(render_html(SECTIONS))
    assert pdf.startswith(b"%PDF")
    from pypdf import PdfReader

    pdf_text = "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)
    assert "Acme Corporation" in pdf_text
    assert "Confirm the agenda" in pdf_text

    docx = render_docx(SECTIONS)
    assert docx.startswith(b"PK")
    from docx import Document

    document = Document(BytesIO(docx))
    docx_text = "\n".join(paragraph.text for paragraph in document.paragraphs)
    assert "Acme Corporation" in docx_text
    assert "Confirm the agenda" in docx_text


def test_markdown_renderer_remains_canonical() -> None:
    markdown = render_markdown(SECTIONS)
    assert markdown.startswith("# Customer Intelligence Briefing")
    assert sum(line.startswith("## ") for line in markdown.splitlines()) == 7
