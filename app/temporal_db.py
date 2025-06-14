from app import db
import sqlalchemy as sa
from app.models import Attorney, Firm

def temporal_read(model, as_of_date, *criterion):
    """
    Query records valid as of a given date, with optional additional filters.
    """
    query = (
        sa.select(model)
        .where(
            model.valid_from <= as_of_date,
            sa.or_(
                model.valid_to == None,
                model.valid_to > as_of_date
            ),
            *criterion
        )
    )
    return db.session.execute(query).scalars().all()

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
    # Build a set of incoming external_ids
    incoming_ids = {rec.external_id for rec in records}

    # Find all currently valid records as of as_of_date
    current_valid = db.session.execute(
        sa.select(model)
        .where(
            model.valid_from <= as_of_date,
            sa.or_(
                model.valid_to == None,
                model.valid_to > as_of_date
            )
        )
    ).scalars().all()

    # Mark as lapsed any record not in the incoming list
    for existing in current_valid:
        if existing.external_id not in incoming_ids:
            existing.valid_to = as_of_date

    # Now process incoming records
    for rec in records:
        ext_id = rec.external_id
        # Find currently valid record for this external_id
        existing = next((e for e in current_valid if e.external_id == ext_id), None)

        if not existing:
            db.session.add(rec)
        else:
            # Compare all fields except id, valid_from, valid_to
            fields = [col.name for col in model.__table__.columns
                      if col.name not in ("id", "valid_from", "valid_to")]
            changed = any(getattr(existing, f) != getattr(rec, f) for f in fields)
            if changed:
                # Close out old record
                existing.valid_to = as_of_date
                # Insert new record
                rec.valid_from = as_of_date
                rec.valid_to = None
                db.session.add(rec)
    db.session.commit()

# Example usage:
# attorneys = [Attorney(...), ...]
# temporal_write(Attorney, attorneys, as_of_date)
# results = temporal_read(Attorney, as_of_date, Attorney.name == "John Doe")