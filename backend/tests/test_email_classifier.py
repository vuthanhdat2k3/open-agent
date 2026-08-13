from datetime import datetime

from app.customer_intelligence.classifier import classify_email, extract_calendar_payload
from app.customer_intelligence.contracts import NormalizedEmail
from app.customer_intelligence.ingest import notification_preview


def _email(*, subject: str, body: str = "", domain: str = "example.com", flags=None):
    return NormalizedEmail(
        provider="gmail",
        provider_message_id="message-1",
        thread_id=None,
        sender_name=None,
        sender_email=f"sender@{domain}",
        sender_domain=domain,
        recipients=[],
        subject=subject,
        body_text=body,
        body_html=None,
        attachments=[],
        received_at=datetime.utcnow(),
        injection_flags=flags or [],
    )


def test_classifier_routes_spam_calendar_customer_and_guard_risk():
    assert classify_email(_email(subject="WIN prize casino giveaway")).label == "spam"
    assert classify_email(_email(subject="Meeting", body="Let's meet at 10:30 on 12/08")).label == "calendar"
    # A sender domain is only evidence; agent classification is required
    # before routing a research case.
    assert classify_email(_email(subject="Partnership inquiry", domain="acme.example")).label == "normal"
    assert classify_email(_email(subject="Hello", flags=["prompt_injection"])).label == "security_risk"
    payload = extract_calendar_payload(_email(subject="Meeting", body="Let's meet at 10:30 on 12/08"))
    assert payload is not None
    assert payload["start"].endswith("10:30:00+00:00")


def test_notification_preview_is_bounded_and_single_line_body():
    preview = notification_preview("Subject", "hello\n\nworld " * 200, max_chars=20)
    assert preview.startswith("Subject\nhello world")
    assert len(preview.split("\n", 1)[1]) <= 21
