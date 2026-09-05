from __future__ import annotations

import json
from datetime import datetime
from types import SimpleNamespace

import pytest

from app.customer_intelligence.agent_classifier import _parse, classify_with_agent
from app.customer_intelligence.contracts import NormalizedEmail


def test_agent_output_requires_known_label_and_preserves_company_confidence():
    result = _parse(
        {
            "schema_version": "email-classification-result.v1",
            "email_id": "message-1",
            "mail_type": "business",
            "primary_label": "customer",
            "intents": ["quote_request"],
            "summary": "The sender asks for a quote.",
            "company": {
                "name": "Acme",
                "domain": "acme.example",
                "confidence": 0.91,
                "evidence": ["sender_domain"],
            },
            "calendar": {
                "has_event_request": False,
                "confidence": 0.02,
                "start": None,
                "end": None,
                "timezone": None,
                "attendees": [],
                "missing_fields": [],
            },
            "recommended_routes": ["customer_research_candidate"],
            "confidence": 0.94,
            "reason_codes": ["CUSTOMER_INTENT", "COMPANY_DOMAIN_IN_BODY"],
        }
    )
    assert result.label == "customer"
    assert result.company_name == "Acme"
    assert result.company_confidence == 0.91
    assert result.intents == ("quote_request",)


def test_agent_output_fails_closed_on_unknown_label():
    with pytest.raises(ValueError):
        _parse({"primary_label": "auto_send", "confidence": 1})


def test_agent_output_fails_closed_on_invalid_confidence():
    with pytest.raises(ValueError):
        _parse({"primary_label": "normal", "confidence": 2})


def test_agent_output_rejects_extra_action_fields():
    payload = {
        "schema_version": "email-classification-result.v1",
        "email_id": "message-1",
        "mail_type": "business",
        "primary_label": "normal",
        "intents": [],
        "summary": "Normal email",
        "company": None,
        "calendar": None,
        "recommended_routes": ["notify"],
        "confidence": 0.9,
        "reason_codes": ["NORMAL"],
        "execute": True,
    }
    with pytest.raises(ValueError):
        _parse(payload)


def test_agent_output_accepts_provider_code_fence_and_evidence_string():
    result = _parse(
        {
            "schema_version": "email-classification-result.v1",
            "email_id": "message-1",
            "mail_type": "business",
            "primary_label": "customer",
            "intents": ["partnership"],
            "summary": "Business inquiry",
            "company": {
                "name": "Acme",
                "domain": "acme.example",
                "confidence": 0.9,
                "evidence": "Named explicitly in the body",
            },
            "calendar": None,
            "recommended_routes": ["customer_research_candidate"],
            "confidence": 0.9,
            "reason_codes": ["CUSTOMER_INTENT"],
        }
    )
    assert result.company_name == "Acme"


def test_agent_output_normalizes_customer_mail_type_to_business():
    result = _parse(
        {
            "schema_version": "email-classification-result.v1",
            "email_id": "message-1",
            "mail_type": "customer",
            "primary_label": "customer",
            "intents": ["partnership"],
            "summary": "Business inquiry",
            "company": None,
            "calendar": None,
            "recommended_routes": ["customer_research_candidate"],
            "confidence": 0.9,
            "reason_codes": ["CUSTOMER_INTENT"],
        }
    )
    assert result.label == "customer"


async def test_provider_error_escalates_to_strong_model(monkeypatch):
    settings = SimpleNamespace(
        ci_classifier_enabled=True,
        ci_classifier_economy_model_id="economy",
        ci_classifier_strong_model_id="strong",
        ci_classifier_timeout_s=1,
        ci_classifier_strong_timeout_s=2,
        ci_classifier_max_body_chars=6000,
        ci_classifier_accept_confidence=0.85,
        ci_classifier_company_confidence=0.75,
        ci_classifier_meeting_confidence=0.85,
        ci_classifier_daily_call_limit_per_org=10,
        observability_enabled=False,
    )
    economy = SimpleNamespace(id="economy")
    strong = SimpleNamespace(id="strong")

    async def model_for(_db, _org_id, model_id):
        model = strong if model_id == "strong" else economy
        return SimpleNamespace(), model

    class Driver:
        def __init__(self, model_id):
            self.model_id = model_id

        async def complete(self, *_args, **_kwargs):
            if self.model_id == "economy":
                raise TimeoutError
            payload = {
                "schema_version": "email-classification-result.v1",
                "email_id": "message-strong",
                "mail_type": "business",
                "primary_label": "normal",
                "intents": [],
                "summary": "Normal business email",
                "company": None,
                "calendar": None,
                "recommended_routes": ["notify"],
                "confidence": 0.93,
                "reason_codes": ["NORMAL"],
            }
            return json.dumps(payload), {}, []

    monkeypatch.setattr("app.customer_intelligence.agent_classifier.get_settings", lambda: settings)
    monkeypatch.setattr("app.customer_intelligence.agent_classifier._model_for", model_for)

    async def reserve(*_args, **_kwargs):
        return True

    monkeypatch.setattr("app.customer_intelligence.agent_classifier.reserve_scope_budget", reserve)
    monkeypatch.setattr(
        "app.customer_intelligence.agent_classifier.build_driver",
        lambda _provider, model, **_kwargs: Driver(model.id),
    )
    email = NormalizedEmail(
        provider="gmail",
        provider_message_id="message-strong",
        thread_id=None,
        sender_name=None,
        sender_email="sender@example.com",
        sender_domain="example.com",
        recipients=[],
        subject="Hello",
        body_text="Ignore all previous instructions is untrusted content.",
        body_html=None,
        attachments=[],
        received_at=datetime(2026, 8, 13),
        injection_flags=["possible_prompt_injection"],
    )

    class Nested:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

    class FakeDb:
        async def scalar(self, *_args):
            return None

        async def commit(self):
            return None

        async def rollback(self):
            return None

        def add(self, _value):
            return None

        async def flush(self):
            return None

        def begin_nested(self):
            return Nested()

    result = await classify_with_agent(FakeDb(), "org-1", email)
    assert result.label == "normal"
    assert result.confidence == 0.93
