from __future__ import annotations

import pytest

from app.customer_intelligence.agent_classifier import _parse


def test_agent_output_requires_known_label_and_preserves_company_confidence():
    result = _parse(
        {
            "primary_label": "customer",
            "intents": ["quote_request"],
            "summary": "The sender asks for a quote.",
            "company": {"name": "Acme", "domain": "acme.example", "confidence": 0.91},
            "calendar": {"has_event_request": False, "confidence": 0.02},
            "confidence": 0.94,
            "reason_codes": ["CUSTOMER_INTENT", "COMPANY_DOMAIN_IN_BODY"],
        }
    )
    assert result.label == "customer"
    assert result.company_name == "Acme"
    assert result.company_confidence == 0.91
    assert result.intents == ("quote_request",)


def test_agent_output_fails_closed_on_unknown_label():
    with pytest.raises(ValueError, match="unknown classifier label"):
        _parse({"primary_label": "auto_send", "confidence": 1})


def test_agent_output_fails_closed_on_invalid_confidence():
    with pytest.raises(ValueError, match="invalid classifier confidence"):
        _parse({"primary_label": "normal", "confidence": 2})
