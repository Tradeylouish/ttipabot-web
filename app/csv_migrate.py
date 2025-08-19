import datetime
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

from app import current_app, db, temporal_db
from app.models import Attorney


def parse_date_from_filename(filename: str) -> datetime.date:
    """Extracts date from filename, expects format YYYY-MM-DD.csv"""
    stem = Path(filename).stem
    return datetime.datetime.strptime(stem, "%Y-%m-%d").date()

def normalize_external_id(row):
    ext_id = row.get("external_id")
    if not ext_id:
        ext_id = str(row.get("name")).strip().lower()[:36]
    return ext_id

def migrate_csvs(csv_dir: Path) -> None:
    """Imports CSV files into the DB using pandas for efficient processing."""
    if not csv_dir.exists():
        raise FileNotFoundError("CSV directory does not exist.")

    csv_files = sorted(csv_dir.glob('*.csv'), key=lambda f: parse_date_from_filename(f.name))

    for csv_file in csv_files:
        print(f"Migrating {csv_file.name}")
        attorneys = csv_to_attorneys(csv_file)
        temporal_db.temporal_write(Attorney, attorneys, parse_date_from_filename(csv_file.name))
        
def csv_to_attorneys(csv_file: Path) -> list[Attorney]:
    csv_date = parse_date_from_filename(csv_file.name)
    df = pd.read_csv(csv_file)

    # Map DataFrame columns to Attorney fields
    column_map = {
        'Name': 'name',
        'Phone': 'phone',
        'Email': 'email',
        'Firm': 'firm',
        'Address': 'address',
    }
    df = df.rename(columns=column_map)

    # Normalize external_id
    df['external_id'] = None
    df['external_id'] = df.apply(normalize_external_id, axis=1)

    # Prepare boolean fields
    df['patents'] = df.get('Registered as', '').apply(lambda x: 'Patents' in str(x))
    df['trademarks'] = df.get('Registered as', '').apply(lambda x: 'Trade marks' in str(x))
    df.drop(columns=['Registered as'], inplace=True)
    
    # Add valid_from
    df['valid_from'] = csv_date
    
    return [Attorney(**row) for row in df.to_dict(orient='records')]