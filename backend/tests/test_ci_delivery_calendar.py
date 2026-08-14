from app.customer_intelligence.delivery import _calendar_provider_event_id


def test_calendar_response_uses_canonical_provider_event_id():
    assert _calendar_provider_event_id({"provider_event_id": "google-event-1"}) == "google-event-1"


def test_calendar_response_supports_legacy_event_id_keys():
    assert _calendar_provider_event_id({"id": "legacy-id"}) == "legacy-id"
    assert _calendar_provider_event_id({"event_id": "legacy-event-id"}) == "legacy-event-id"


def test_calendar_response_without_event_id_is_not_successful():
    assert _calendar_provider_event_id({"status": "confirmed"}) == ""
    assert _calendar_provider_event_id({"provider_event_id": "  "}) == ""
