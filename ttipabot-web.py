from pathlib import Path

import sqlalchemy as sa
import sqlalchemy.orm as so

from app import create_app, db
from app.csv_handler import migrate_csvs
from app.models import Attorney, Firm

app = create_app()

@app.shell_context_processor
def make_shell_context():
    return {'sa': sa, 'so': so, 'db': db, 'User': Attorney, 'Firm': Firm}

