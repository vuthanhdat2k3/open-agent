from types import SimpleNamespace

from app.api.v1.routes.customer_intelligence import (
    _owned_active_connection_by_other_user,
    _reclaim_owner,
)


def test_disconnected_connection_can_be_reclaimed() -> None:
    connection = SimpleNamespace(
        created_by_user_id="previous-user",
        status="disconnected",
        credentials_enc=None,
    )

    assert not _owned_active_connection_by_other_user(connection, "new-user")
    assert _reclaim_owner(connection, "new-user") == "new-user"


def test_active_connection_with_credentials_remains_reserved() -> None:
    connection = SimpleNamespace(
        created_by_user_id="previous-user",
        status="connected",
        credentials_enc="encrypted",
    )

    assert _owned_active_connection_by_other_user(connection, "new-user")
    assert _reclaim_owner(connection, "new-user") == "previous-user"


def test_connection_without_credentials_is_reclaimable_even_if_status_is_stale() -> None:
    connection = SimpleNamespace(
        created_by_user_id="previous-user",
        status="connected",
        credentials_enc=None,
    )

    assert not _owned_active_connection_by_other_user(connection, "new-user")
    assert _reclaim_owner(connection, "new-user") == "new-user"
