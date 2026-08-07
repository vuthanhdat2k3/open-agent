from __future__ import annotations

from app.customer_intelligence.contracts import ReportSections


def render_markdown(sections: ReportSections) -> str:
    """Render the stable 7-section briefing as canonical markdown (FR-006).

    Every external claim in the output is traceable to ``sections["sources"]``;
    absent sections render as explicit empty markers rather than fabrications.
    """
    out: list[str] = []
    out.append("# Customer Intelligence Briefing")
    out.append("")

    out.append("## Executive Summary")
    out.append(sections.get("executive_summary") or "_No summary available._")
    out.append("")

    out.append("## Company Overview")
    overview = sections.get("company_overview") or []
    if overview:
        for company in overview:
            out.append(f"### {company.get('canonical_name') or 'Unknown company'}")
            if company.get("aliases"):
                out.append(f"- Aliases: {', '.join(company['aliases'])}")
            if company.get("industry"):
                out.append(f"- Industry: {company['industry']}")
            if company.get("products"):
                out.append(f"- Products: {', '.join(company['products'])}")
            if company.get("domain"):
                out.append(f"- Domain: {company['domain']}")
    else:
        out.append("_No company matched._")
    out.append("")

    out.append("## Recent News")
    news = sections.get("recent_news") or []
    if news:
        for item in news:
            date = f" ({item.get('published_date')})" if item.get("published_date") else ""
            out.append(f"- [{item.get('title') or item.get('url')}]({item.get('url')}){date}")
            if item.get("excerpt"):
                out.append(f"  {item['excerpt'][:300]}")
    else:
        out.append("_No recent news found._")
    out.append("")

    out.append("## Contact Information")
    contacts = sections.get("contact_information") or []
    if contacts:
        for contact in contacts:
            name = contact.get("name") or "Unknown"
            role = f" — {contact.get('role')}" if contact.get("role") else ""
            email = f" ({contact.get('email')})" if contact.get("email") else ""
            out.append(f"- {name}{role}{email}")
    else:
        out.append("_No contacts found._")
    out.append("")

    out.append("## Upcoming Meetings")
    meetings = sections.get("upcoming_meetings") or []
    if meetings:
        for meeting in meetings:
            when = meeting.get("start_at") or "unscheduled"
            match = f" [{meeting.get('match_type')}]" if meeting.get("match_type") else ""
            out.append(f"- {meeting.get('title') or '(untitled)'} — {when}{match}")
            if meeting.get("attendees"):
                out.append(f"  Attendees: {', '.join(meeting['attendees'])}")
    else:
        out.append("_No upcoming meetings matched._")
    out.append("")

    out.append("## Open Questions")
    questions = sections.get("open_questions") or []
    if questions:
        for question in questions:
            out.append(f"- {question}")
    else:
        out.append("_None._")
    out.append("")

    out.append("## Sources")
    sources = sections.get("sources") or []
    if sources:
        for i, source in enumerate(sources, start=1):
            title = source.get("title") or source.get("url")
            date = f" ({source.get('published_date')})" if source.get("published_date") else ""
            publisher = f" — {source.get('publisher')}" if source.get("publisher") else ""
            out.append(f"{i}. [{title}]({source.get('url')}){date}{publisher}")
            if source.get("excerpt"):
                out.append(f"   {source['excerpt'][:300]}")
    else:
        out.append("_No sources._")

    return "\n".join(out)
