import datetime

import pandas as pd
import sqlalchemy as sa

from app import db, temporal_db
from app.models import Attorney, Firm
from app.temporal_db import temporal_query


def print_head():
    attorney_query = temporal_db.temporal_query(
        temporal_db.Attorney,
        datetime.datetime.now().date()
    )
    attorneys = db.session.execute(attorney_query).scalars().all()
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

    subquery = temporal_db.temporal_query(
        model=Attorney,
        as_of_date=first_date,
        columns=[Attorney.external_id])

    diff_query = temporal_db.temporal_query(Attorney, last_date).where(Attorney.external_id.notin_(subquery))

    filters = []
    if pat:
        filters.append(Attorney.patents)
    if tm:
        filters.append(Attorney.trademarks)

    return diff_query.where(*filters)

def get_lapses_query(first_date, last_date, pat=False, tm=False):
    """
    Returns a query for attorneys whose registration lapsed between two dates.
    """

    subquery = temporal_db.temporal_query(
        model=Attorney,
        as_of_date=last_date,
        columns=[Attorney.external_id])

    diff_query = temporal_db.temporal_query(Attorney, first_date).where(Attorney.external_id.notin_(subquery))

    filters = []

    if pat:
        filters.append(Attorney.patents)
    if tm:
        filters.append(Attorney.trademarks)

    return diff_query.where(*filters)

def get_attorneys_query(query_date, order_by_param='+name', pat=False, tm=False):
    """
    Returns a query for attorneys valid on a given date, with filtering and ordering.
    """
    query = temporal_db.temporal_query(Attorney, query_date)

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

def get_movements_query(first_date, last_date, pat=False, tm=False):
    # Subqueries for attorneys valid on first_date and last_date
    first_subq = temporal_query(Attorney, first_date).subquery()
    last_subq = temporal_query(Attorney, last_date).subquery()

    # Join on external_id, filter for differing firm, exclude new registrations
    query = sa.select(Attorney).join(
    first_subq,
    Attorney.external_id == first_subq.c.external_id
    ).where(
        Attorney.valid_from <= last_date,
        sa.or_(
            Attorney.valid_to == None,
            Attorney.valid_to > last_date
        ),
        Attorney.firm != first_subq.c.firm
    )
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
