import sqlalchemy as sa
import datetime
import pandas as pd
from app import db, temporal_db
from app.models import Attorney

def print_head():
    attorneys = temporal_db.temporal_read(
        temporal_db.Attorney,
        '2025-05-15'
    )
    print(attorneys)

def dump_attorneys_to_csv(csv_path: str):
    """Dump the entire attorneys table to a CSV file with headers."""
    # Query all attorneys
    attorneys = db.session.execute(sa.select(Attorney)).scalars().all()
    # Convert to list of dicts
    rows = [
        {
            "id": a.id,
            "external_id": a.external_id,
            "name": a.name,
            "phone": a.phone,
            "email": a.email,
            "firm": a.firm,
            "address": a.address,
            "patents": a.patents,
            "trademarks": a.trademarks,
            "valid_from": a.valid_from,
            "valid_to": a.valid_to,
        }
        for a in attorneys
    ]
    # Write to CSV
    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)