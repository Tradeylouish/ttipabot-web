import datetime

import pandas as pd
import sqlalchemy as sa

from app import db, temporal_db
from app.models import Attorney, Firm


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

def dump_firms_to_csv(csv_path: str):
    """Dump the entire firms table to a CSV file with headers."""
    # Query all firms
    firms = db.session.execute(sa.select(Firm)).scalars().all()
    # Convert to list of dicts
    rows = [
        {
            "id": f.id,
            "external_id": f.external_id,
            "name": f.name,
            "phone": f.phone,
            "email": f.email,
            "website": f.website,
            "address": f.address,
            "patents": f.patents,
            "trademarks": f.trademarks,
        }
        for f in firms
    ]
    # Write to CSV
    df = pd.DataFrame(rows)
    df.to_csv(csv_path, index=False)

def get_registrations_query(first_date, last_date, pat=False, tm=False):
    """
    Returns a query for new attorneys registered between two dates.
    """
    filters = []
    if pat:
        filters.append(Attorney.patents)
    if tm:
        filters.append(Attorney.trademarks)

    subquery = sa.select(Attorney.external_id).where(Attorney.valid_from < first_date)
    filters.append(Attorney.external_id.notin_(subquery))
    filters.append(Attorney.valid_from >= first_date)
    filters.append(Attorney.valid_from <= last_date)

    return sa.select(Attorney).where(*filters)

def get_lapses_query(first_date, last_date, pat=False, tm=False):
    """
    Returns a query for attorneys whose registration lapsed between two dates.
    """
    a2 = sa.orm.aliased(Attorney)
    subquery = (
        sa.select(a2)
        .where(a2.external_id == Attorney.external_id)
        .where(a2.valid_from > Attorney.valid_from)
        .exists()
    )

    filters = [
        Attorney.valid_to.between(first_date, last_date),
        sa.not_(subquery)
    ]

    if pat:
        filters.append(Attorney.patents)
    if tm:
        filters.append(Attorney.trademarks)

    return sa.select(Attorney).where(*filters)

def get_attorneys_query(query_date, order_by_param='+name', pat=False, tm=False):
    """
    Returns a query for attorneys valid on a given date, with filtering and ordering.
    """
    query = sa.select(Attorney).where(
        Attorney.valid_from <= query_date,
        sa.or_(Attorney.valid_to >= query_date, Attorney.valid_to.is_(None))
    )

    filters = []
    if pat:
        filters.append(Attorney.patents)
    if tm:
        filters.append(Attorney.trademarks)
    if filters:
        query = query.where(*filters)

    if order_by_param:
        order_by_field = order_by_param.lstrip(' +-')
        direction = sa.desc if order_by_param.startswith('-') else sa.asc

        print(order_by_field)
        order_map = {
            'name': Attorney.name,
            'name_length': sa.func.char_length(Attorney.name),
            'firm': sa.func.lower(Attorney.firm)
        }
        
        order_column = order_map.get(order_by_field)
        if order_column is not None:
            query = query.order_by(direction(order_column))

    return query

def get_movements_query(first_date=None, last_date=None, pat=False, tm=False):
    """
    Returns a query for attorney movements between firms.
    """
    a1 = sa.orm.aliased(Attorney, name="a1") # new record
    a2 = sa.orm.aliased(Attorney, name="a2") # old record

    subquery = (
        sa.select(Attorney.id)
        .where(Attorney.external_id == a1.external_id)
        .where(Attorney.valid_from > a2.valid_from)
        .where(Attorney.valid_from < a1.valid_from)
        .exists()
    )

    query = (
        sa.select(a2, a1)
        .join(a1, a1.external_id == a2.external_id)
        .where(a1.firm != a2.firm)
        .where(sa.not_(subquery))
        .order_by(a1.valid_from.desc())
    )

    if first_date and last_date:
        query = query.where(a1.valid_from.between(first_date, last_date))

    if pat:
        query = query.where(a1.patents)
    if tm:
        query = query.where(a1.trademarks)
        
    return query

def get_firms_query(date, order_by_param='+name', pat=False, tm=False):
    """
    Returns a query for firms, with filtering and ordering options.
    """
    query = sa.select(Firm)

    filters = []
    if pat:
        filters.append(Firm.patents)
    if tm:
        filters.append(Firm.trademarks)
    if filters:
        query = query.where(*filters)

    if order_by_param:
        order_by_field = order_by_param.lstrip(' +-')
        direction = sa.desc if order_by_param.startswith('-') else sa.asc

        print(order_by_field)
        order_map = {
            'name': Firm.name,
            'attorney_count': sa.func.char_length(Firm.name)
        }
        
        order_column = order_map.get(order_by_field)
        if order_column is not None:
            query = query.order_by(direction(order_column))

    return query