import datetime
import sqlalchemy as sa
from flask import current_app

from app import db


# Fields that define a record's business state for change detection. These are
# exactly the fields the scraper populates on an incoming (unflushed) record.
# They intentionally exclude:
#   - id                     surrogate primary key; differs on every new row
#   - valid_from / valid_to  temporal metadata; differs by construction between
#                           versions (Attorney only)
#   - consolidated_firm_id   set later by data_migrator, never by the scraper;
#                           an incoming record always has None here while the
#                           stored row has a value, so comparing it would flag
#                           every record as changed on every scrape.
_BUSINESS_FIELDS = {
    "attorneys": (
        "external_id", "name", "phone", "email", "firm", "address",
        "additional_information", "patents", "trademarks",
    ),
    "firms": (
        "external_id", "name", "phone", "email", "website", "directors",
        "address", "patents", "trademarks",
    ),
}


def records_unchanged(existing, incoming) -> bool:
    """Return True if ``existing`` and ``incoming`` are equal on business fields.

    ``existing`` is a stored ORM row and ``incoming`` is a freshly-built
    instance from the scraper. Used by the temporal/merge write paths to decide
    whether a new temporal version or an update is warranted. Values are
    normalized with ``v or None`` so empty strings and falsy booleans compare
    equal to None, matching the semantics of the previous per-model ``__eq__``
    methods.
    """
    fields = _BUSINESS_FIELDS[type(existing).__tablename__]
    for f in fields:
        if (getattr(existing, f, None) or None) != (
            getattr(incoming, f, None) or None
        ):
            return False
    return True


def temporal_write_with_ids(model, records: list, as_of_date) -> tuple:
    """
    Insert or update records in a temporal table.
    Returns a tuple of (new_ids, changed_ids) for records that were inserted or updated.
    
    For each record:
      - If a valid record with the same external_id exists as of as_of_date,
        and any other field differs, set its valid_to to as_of_date and insert new.
      - If no valid record exists, insert new.
    Additionally:
      - For any currently valid record in the DB whose external_id is NOT in the incoming list,
        set its valid_to to as_of_date (mark as lapsed).
    
    Safety guard: a single scrape should not be able to mass-lapse a large
    fraction of the register. If the number of records to lapse exceeds
    ``MASS_LAPSE_THRESHOLD`` (absolute) or ``MASS_LAPSE_FRACTION`` of the
    currently-valid set, the lapse is aborted (those ``valid_to`` updates are
    not applied) and an error is logged. The new/changed writes still proceed,
    so a real registration/movement is never lost; only the destructive
    "mark-missing-as-lapsed" step is skipped pending investigation.
    """
    MASS_LAPSE_THRESHOLD = 5
    MASS_LAPSE_FRACTION = 0.01

    # Deduplicate incoming records by external_id. The register has been known
    # to return duplicates; without this, both copies would match the same
    # existing row and each be inserted, producing two currently-valid rows
    # for one attorney.
    seen = set()
    deduped = []
    for rec in records:
        if rec.external_id in seen:
            current_app.logger.warning(
                "temporal_write_with_ids: ignoring duplicate incoming record "
                "for external_id=%s", rec.external_id,
            )
            continue
        seen.add(rec.external_id)
        deduped.append(rec)
    records = deduped

    incoming_ids = {rec.external_id for rec in records}
    current_query = temporal_query(model, as_of_date)
    current_valid = db.session.execute(current_query).scalars().all()

    new_ids = []
    changed_ids = []
    lapsed_ids = []

    # Mark as lapsed any record not in the incoming list
    to_lapse = [e for e in current_valid if e.external_id not in incoming_ids]

    if to_lapse:
        lapse_fraction = len(to_lapse) / max(len(current_valid), 1)
        if (
            len(to_lapse) > MASS_LAPSE_THRESHOLD
            and lapse_fraction > MASS_LAPSE_FRACTION
        ):
            # Refuse to mass-lapse. This is the signature of a partial scrape /
            # parse failure, not a real register event. Log loudly and skip the
            # destructive step; new/changed writes below still proceed.
            current_app.logger.error(
                "temporal_write_with_ids: refusing to mass-lapse %d of %d "
                "currently-valid %s records (%.1f%%) on %s. This looks like a "
                "partial scrape or parse failure, not a real lapse. SKIPPING "
                "the lapse step. Affected external_ids: %s",
                len(to_lapse),
                len(current_valid),
                model.__tablename__,
                lapse_fraction * 100,
                as_of_date.isoformat(),
                [e.external_id for e in to_lapse],
            )
            to_lapse = []
        else:
            current_app.logger.info(
                "temporal_write_with_ids: lapping %d %s record(s) on %s: %s",
                len(to_lapse),
                model.__tablename__,
                as_of_date.isoformat(),
                [e.external_id for e in to_lapse],
            )

    for existing in to_lapse:
        existing.valid_to = as_of_date
        lapsed_ids.append(existing.id)

    for rec in records:
        ext_id = rec.external_id
        existing = next((e for e in current_valid if e.external_id == ext_id), None)

        if not existing:
            db.session.add(rec)
            db.session.flush()
            new_ids.append(rec.id)
        else:
            # A new temporal version is only written when business fields differ.
            if not records_unchanged(existing, rec):
                existing.valid_to = as_of_date
                rec.valid_from = as_of_date
                rec.valid_to = None
                db.session.add(rec)
                db.session.flush()
                changed_ids.append(rec.id)
    
    db.session.commit()
    current_app.logger.info(
        "temporal_write_with_ids(%s, %s): incoming=%d current_valid=%d "
        "new=%d changed=%d lapsed=%d",
        model.__tablename__,
        as_of_date.isoformat(),
        len(records),
        len(current_valid),
        len(new_ids),
        len(changed_ids),
        len(lapsed_ids),
    )
    return (new_ids, changed_ids)


def temporal_query(
    model, as_of_date: datetime.date, criterion: list = None, columns=None
):
    """
    Query records valid as of a given date, with optional additional filters.
    Optionally select specific columns.
    """
    if columns is not None:
        query = sa.select(*columns)
    else:
        query = sa.select(model)

    query = query.where(
        model.valid_from <= as_of_date,
        sa.or_(model.valid_to == None, model.valid_to > as_of_date),
        *(criterion or []),
    )
    return query


def temporal_write(model, records: list, as_of_date):
    """
    Insert or update records in a temporal table.
    For each record:
      - If a valid record with the same external_id exists as of as_of_date,
        and any other field differs, set its valid_to to as_of_date and insert new.
      - If no valid record exists, insert new.
    Additionally:
      - For any currently valid record in the DB whose external_id is NOT in the incoming list,
        set its valid_to to as_of_date (mark as lapsed).
    """

    incoming_ids = {rec.external_id for rec in records}
    current_query = temporal_query(model, as_of_date)
    current_valid = db.session.execute(current_query).scalars().all()

    # Mark as lapsed any record not in the incoming list
    for existing in current_valid:
        if existing.external_id not in incoming_ids:
            existing.valid_to = as_of_date

    for rec in records:
        ext_id = rec.external_id
        existing = next((e for e in current_valid if e.external_id == ext_id), None)

        if not existing:
            db.session.add(rec)
        else:
            # A new temporal version is only written when business fields differ.
            if not records_unchanged(existing, rec):
                existing.valid_to = as_of_date
                rec.valid_from = as_of_date
                rec.valid_to = None
                db.session.add(rec)
    db.session.commit()
