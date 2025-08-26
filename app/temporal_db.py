import sqlalchemy as sa

from app import db
from app.models import Attorney, Firm


def temporal_query(model, as_of_date, *criterion, columns=None):
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
        sa.or_(
            model.valid_to == None,
            model.valid_to > as_of_date
        ),
        *criterion
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
            # Comparison relies on appropriate __eq__ method being defined in model
            if existing != rec:
                existing.valid_to = as_of_date
                rec.valid_from = as_of_date
                rec.valid_to = None
                db.session.add(rec)
    db.session.commit()