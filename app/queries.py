import csv
import datetime

import sqlalchemy as sa

from app import db, temporal_db
from app.models import Attorney, IncorporatedFirm, ConsolidatedFirm
from app.temporal_db import temporal_query


def print_head():
    attorney_query = temporal_db.temporal_query(
        temporal_db.Attorney, datetime.datetime.now().date()
    )
    attorneys = db.session.execute(attorney_query).scalars().all()
    print(attorneys)


def dump_attorneys_to_csv(csv_path: str):
    """Dump the entire attorneys table to a CSV file with headers."""
    attorneys = db.session.execute(sa.select(Attorney)).scalars().all()
    fieldnames = [
        "id", "external_id", "name", "phone", "email", "firm", "address",
        "additional_information", "patents", "trademarks",
        "valid_from", "valid_to",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for a in attorneys:
            writer.writerow({
                "id": a.id,
                "external_id": a.external_id,
                "name": a.name,
                "phone": a.phone,
                "email": a.email,
                "firm": a.firm,
                "address": a.address,
                "additional_information": a.additional_information,
                "patents": a.patents,
                "trademarks": a.trademarks,
                "valid_from": a.valid_from,
                "valid_to": a.valid_to,
            })


def dump_firms_to_csv(csv_path: str):
    """Dump the entire firms table to a CSV file with headers."""
    firms = db.session.execute(sa.select(IncorporatedFirm)).scalars().all()
    fieldnames = [
        "id", "external_id", "name", "phone", "email", "website",
        "address", "patents", "trademarks",
    ]
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for firm in firms:
            writer.writerow({
                "id": firm.id,
                "external_id": firm.external_id,
                "name": firm.name,
                "phone": firm.phone,
                "email": firm.email,
                "website": firm.website,
                "address": firm.address,
                "patents": firm.patents,
                "trademarks": firm.trademarks,
            })


def get_registrations_query(first_date, last_date, pat=False, tm=False):
    """
    Returns a query for new attorneys registered between two dates.
    """

    subquery = temporal_db.temporal_query(
        model=Attorney, as_of_date=first_date, columns=[Attorney.external_id]
    )

    diff_query = temporal_db.temporal_query(Attorney, last_date).where(
        Attorney.external_id.notin_(subquery)
    )

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
        model=Attorney, as_of_date=last_date, columns=[Attorney.external_id]
    )

    diff_query = temporal_db.temporal_query(Attorney, first_date).where(
        Attorney.external_id.notin_(subquery)
    )

    filters = []

    if pat:
        filters.append(Attorney.patents)
    if tm:
        filters.append(Attorney.trademarks)

    return diff_query.where(*filters)


def get_attorneys_query(query_date, order_by_param="+name", pat=False, tm=False):
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
        order_by_field = order_by_param.lstrip(" +-")
        direction = sa.desc if order_by_param.startswith("-") else sa.asc

        order_map = {
            "name": Attorney.name,
            "name_length": sa.func.char_length(Attorney.name),
            "firm": sa.func.lower(Attorney.firm),
        }

        order_column = order_map.get(order_by_field)
        if order_column is not None:
            query = query.order_by(direction(order_column))

    return query


def get_movements_query(first_date, last_date, pat=False, tm=False):
    # Subqueries for attorneys valid on first_date and last_date
    first_subq = temporal_db.temporal_query(Attorney, first_date).subquery()
    last_subq = temporal_db.temporal_query(Attorney, last_date).subquery()

    # Join on external_id to find attorneys who changed firms
    query = (
        sa.select(
            first_subq.c.name.label("old_name"),
            first_subq.c.firm.label("old_firm"),
            last_subq.c.name.label("new_name"),
            last_subq.c.firm.label("new_firm"),
            last_subq.c.valid_from.label("movement_date"),
        )
        .join(last_subq, first_subq.c.external_id == last_subq.c.external_id)
        .where(first_subq.c.firm != last_subq.c.firm)
        .order_by(last_subq.c.valid_from.asc())
    )

    # Apply filters if specified
    if pat:
        query = query.where(last_subq.c.patents)
    if tm:
        query = query.where(last_subq.c.trademarks)

    return query


def get_firms_query(date, order_by_param="-attorney_count"):
    """
    Returns a query for consolidated firms, ordered by attorney count.
    """
    # Get attorney counts per consolidated firm as of the given date
    filters = [
        Attorney.valid_from <= date,
        sa.or_(Attorney.valid_to.is_(None), Attorney.valid_to >= date),
        Attorney.consolidated_firm_id.isnot(None),
    ]
    
    count_subquery = (
        sa.select(
            Attorney.consolidated_firm_id.label('firm_id'),
            sa.func.count(Attorney.id).label('attorney_count')
        )
        .where(sa.and_(*filters))
        .group_by(Attorney.consolidated_firm_id)
    ).subquery()
    
    # Join with consolidated firms and order by attorney count
    direction = sa.desc if order_by_param.startswith("-") else sa.asc
    
    query = (
        sa.select(ConsolidatedFirm, sa.func.coalesce(count_subquery.c.attorney_count, 0).label('attorney_count'))
        .outerjoin(count_subquery, ConsolidatedFirm.id == count_subquery.c.firm_id)
        .order_by(direction(sa.func.coalesce(count_subquery.c.attorney_count, 0)))
    )

    return query
