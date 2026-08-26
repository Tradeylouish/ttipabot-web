import datetime

from app import db, queries
from app.models import Attorney


def test_attorney_updates_classify_temporal_records(app):
    db.session.add_all(
        [
            Attorney(
                external_id="updates-attorney",
                name="Updated Attorney",
                email="before@example.com",
                firm="First Firm",
                patents=True,
                valid_from=datetime.date(2024, 1, 1),
                valid_to=datetime.date(2024, 2, 1),
            ),
            Attorney(
                external_id="updates-attorney",
                name="Updated Attorney",
                email="after@example.com",
                firm="First Firm",
                patents=True,
                valid_from=datetime.date(2024, 2, 1),
                valid_to=datetime.date(2024, 3, 1),
            ),
            Attorney(
                external_id="updates-attorney",
                name="Updated Attorney",
                email="after@example.com",
                firm="Second Firm",
                patents=True,
                valid_from=datetime.date(2024, 3, 5),
                valid_to=None,
            ),
            Attorney(
                external_id="new-attorney",
                name="New Attorney",
                trademarks=True,
                valid_from=datetime.date(2024, 1, 10),
                valid_to=None,
            ),
        ]
    )
    db.session.commit()

    events = queries.get_attorney_updates(
        datetime.date(2024, 1, 1), datetime.date(2024, 4, 1)
    )
    events_by_key = {
        (event.attorney.external_id, event.update_type): event for event in events
    }

    assert events_by_key["updates-attorney", "new_registration"].update_date == datetime.date(2024, 1, 1)
    assert events_by_key["updates-attorney", "update"].update_date == datetime.date(2024, 2, 1)
    assert events_by_key["updates-attorney", "update"].changed_fields == ("email",)
    assert events_by_key["updates-attorney", "lapse"].update_date == datetime.date(2024, 3, 1)
    assert events_by_key["updates-attorney", "reregistration"].update_date == datetime.date(2024, 3, 5)
    assert events_by_key["new-attorney", "new_registration"].update_date == datetime.date(2024, 1, 10)


def test_attorney_updates_apply_type_and_field_filters(app):
    db.session.add_all(
        [
            Attorney(
                external_id="filter-attorney",
                name="Filter Attorney",
                email="before@example.com",
                firm="Same Firm",
                patents=True,
                valid_from=datetime.date(2024, 1, 1),
                valid_to=datetime.date(2024, 2, 1),
            ),
            Attorney(
                external_id="filter-attorney",
                name="Filter Attorney",
                email="after@example.com",
                firm="Same Firm",
                patents=True,
                valid_from=datetime.date(2024, 2, 1),
                valid_to=None,
            ),
        ]
    )
    db.session.commit()

    email_updates = queries.get_attorney_updates(
        datetime.date(2024, 1, 1),
        datetime.date(2024, 4, 1),
        fields=["email"],
        update_type="update",
    )
    assert len(email_updates) == 1
    assert email_updates[0].changed_fields == ("email",)

    firm_updates = queries.get_attorney_updates(
        datetime.date(2024, 1, 1),
        datetime.date(2024, 4, 1),
        fields=["firm"],
        update_type="update",
    )
    assert firm_updates == []
