import csv
import datetime
from dataclasses import dataclass
from itertools import pairwise

import sqlalchemy as sa

from app import db, temporal_db
from app.models import Attorney, ConsolidatedFirm, IncorporatedFirm
from app.temporal_db import temporal_query

ATTORNEY_UPDATE_FIELDS = (
    "name",
    "firm",
    "phone",
    "email",
    "address",
    "additional_information",
    "patents",
    "trademarks",
)
ATTORNEY_UPDATE_FIELD_LABELS = {
    "name": "Name",
    "firm": "Firm",
    "phone": "Phone",
    "email": "Email",
    "address": "Address",
    "additional_information": "Additional information",
    "patents": "Patent registration",
    "trademarks": "Trade mark registration",
}
ATTORNEY_UPDATE_TYPE_LABELS = {
    "new_registration": "New registration",
    "update": "Update",
    "lapse": "Lapse",
    "reregistration": "Re-registration",
}


@dataclass(frozen=True)
class AttorneyUpdate:
    """A dated event derived from an attorney's temporal records."""

    attorney: Attorney
    update_type: str
    update_date: datetime.date
    changed_fields: tuple[str, ...] = ()

    @property
    def update_type_label(self) -> str:
        return ATTORNEY_UPDATE_TYPE_LABELS[self.update_type]

    @property
    def changed_field_labels(self) -> tuple[str, ...]:
        return tuple(
            ATTORNEY_UPDATE_FIELD_LABELS[field] for field in self.changed_fields
        )


def _changed_attorney_fields(previous: Attorney, current: Attorney) -> tuple[str, ...]:
    return tuple(
        field
        for field in ATTORNEY_UPDATE_FIELDS
        if (getattr(previous, field, None) or None)
        != (getattr(current, field, None) or None)
    )


def get_attorney_updates(
    first_date,
    last_date,
    pat=False,
    tm=False,
    fields=None,
    update_type=None,
):
    """Return attorney registration events recorded in an inclusive date range.

    Temporal rows are stable periods, so a contiguous successor row represents
    an ordinary update.  A successor after a gap represents a re-registration,
    with a lapse event emitted for the end of the previous period.  A final row
    with ``valid_to`` set emits a lapse event even when there is no successor.

    ``fields`` limits ordinary updates to events changing at least one of the
    requested business fields.  Registration, re-registration and lapse events
    are not excluded by that filter because they are not field updates.
    """
    records = db.session.execute(
        sa.select(Attorney).order_by(
            Attorney.external_id.asc(), Attorney.valid_from.asc(), Attorney.id.asc()
        )
    ).scalars().all()

    records_by_attorney = {}
    for record in records:
        records_by_attorney.setdefault(record.external_id, []).append(record)

    events = []
    for attorney_records in records_by_attorney.values():
        first_record = attorney_records[0]
        events.append(
            AttorneyUpdate(
                attorney=first_record,
                update_type="new_registration",
                update_date=first_record.valid_from,
            )
        )

        for previous, current in pairwise(attorney_records):
            changed_fields = _changed_attorney_fields(previous, current)
            if previous.valid_to is not None and previous.valid_to < current.valid_from:
                events.append(
                    AttorneyUpdate(
                        attorney=previous,
                        update_type="lapse",
                        update_date=previous.valid_to,
                    )
                )
                events.append(
                    AttorneyUpdate(
                        attorney=current,
                        update_type="reregistration",
                        update_date=current.valid_from,
                    )
                )
            else:
                events.append(
                    AttorneyUpdate(
                        attorney=current,
                        update_type="update",
                        update_date=current.valid_from,
                        changed_fields=changed_fields,
                    )
                )

        last_record = attorney_records[-1]
        if last_record.valid_to is not None:
            events.append(
                AttorneyUpdate(
                    attorney=last_record,
                    update_type="lapse",
                    update_date=last_record.valid_to,
                )
            )

    if pat or tm:
        events = [
            event
            for event in events
            if (event.attorney.patents if pat else False)
            or (event.attorney.trademarks if tm else False)
        ]

    if fields:
        if isinstance(fields, str):
            fields = (fields,)
        selected_fields = set(fields) & set(ATTORNEY_UPDATE_FIELDS)
        events = [
            event
            for event in events
            if event.update_type != "update"
            or set(event.changed_fields).intersection(selected_fields)
        ]

    if update_type:
        events = [event for event in events if event.update_type == update_type]

    event_order = {
        "new_registration": 0,
        "update": 1,
        "lapse": 2,
        "reregistration": 3,
    }
    return sorted(
        (
            event
            for event in events
            if first_date <= event.update_date <= last_date
        ),
        key=lambda event: (
            -event.update_date.toordinal(),
            event_order[event.update_type],
            event.attorney.name or "",
            event.attorney.external_id or "",
        ),
    )


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

    return diff_query.where(sa.or_(*filters)) if filters else diff_query


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

    return diff_query.where(sa.or_(*filters)) if filters else diff_query


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
        query = query.where(sa.or_(*filters))

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
    if pat or tm:
        type_filters = []
        if pat:
            type_filters.append(last_subq.c.patents)
        if tm:
            type_filters.append(last_subq.c.trademarks)
        query = query.where(sa.or_(*type_filters))

    return query


def get_firms_query(date, order_by_param="-attorney_count", pat=False, tm=False):
    """
    Returns a query for consolidated firms, ordered by attorney count.
    """
    # Get attorney counts per consolidated firm as of the given date
    filters = [
        Attorney.valid_from <= date,
        sa.or_(Attorney.valid_to.is_(None), Attorney.valid_to > date),
        Attorney.consolidated_firm_id.isnot(None),
    ]
    if pat or tm:
        type_filters = []
        if pat:
            type_filters.append(Attorney.patents)
        if tm:
            type_filters.append(Attorney.trademarks)
        filters.append(sa.or_(*type_filters))
    
    count_subquery = (
        sa.select(
            Attorney.consolidated_firm_id.label('firm_id'),
            sa.func.count(Attorney.id).label('attorney_count')
        )
        .where(sa.and_(*filters))
        .group_by(Attorney.consolidated_firm_id)
    ).subquery()
    
    # Join with consolidated firms and order by the requested register field.
    # ``attorney_count`` remains the API/default ordering, while the public
    # directory can also offer an alphabetical firm index.
    direction = sa.desc if order_by_param.startswith("-") else sa.asc
    order_field = order_by_param.lstrip(" +-")
    attorney_count = sa.func.coalesce(count_subquery.c.attorney_count, 0)
    order_column = (
        sa.func.lower(ConsolidatedFirm.name)
        if order_field == "name"
        else attorney_count
    )

    query = (
        sa.select(ConsolidatedFirm, attorney_count.label('attorney_count'))
        .outerjoin(count_subquery, ConsolidatedFirm.id == count_subquery.c.firm_id)
        .order_by(direction(order_column), sa.func.lower(ConsolidatedFirm.name))
    )
    if pat or tm:
        query = query.where(
            ConsolidatedFirm.id.in_(sa.select(count_subquery.c.firm_id))
        )

    return query


def get_attorney_history(external_id: str):
    """
    Returns all temporal records for an attorney, ordered by valid_from ascending.
    Each record represents a period where the attorney's details (including firm) were stable.
    """
    return (
        db.session.execute(
            sa.select(Attorney)
            .where(Attorney.external_id == external_id)
            .order_by(Attorney.valid_from.asc(), Attorney.id.asc())
        )
        .scalars()
        .all()
    )


def get_attorney_latest(external_id: str):
    """Returns the most recent record for an attorney (by valid_from desc)."""
    return (
        db.session.execute(
            sa.select(Attorney)
            .where(Attorney.external_id == external_id)
            .order_by(Attorney.valid_from.desc(), Attorney.id.desc())
        )
        .scalars()
        .first()
    )


def get_consolidated_firm_detail(firm_id: int):
    """
    Returns the ConsolidatedFirm record along with its related attorneys,
    incorporated firms, and aliases (distinct firm-field spellings from related attorneys).
    """
    firm = db.session.execute(
        sa.select(ConsolidatedFirm).where(ConsolidatedFirm.id == firm_id)
    ).scalars().first()

    if not firm:
        return None

    # Related incorporated firms
    inc_firms = db.session.execute(
        sa.select(IncorporatedFirm).where(
            IncorporatedFirm.consolidated_firm_id == firm_id
        )
    ).scalars().all()

    # Related attorneys (currently valid)
    today = datetime.date.today()
    current_attorneys = db.session.execute(
        temporal_query(
            Attorney,
            today,
            criterion=[Attorney.consolidated_firm_id == firm_id],
        )
    ).scalars().all()

    # Aliases: distinct firm-field values from ALL attorney records linked to this firm
    alias_rows = db.session.execute(
        sa.select(Attorney.firm)
        .where(
            Attorney.consolidated_firm_id == firm_id,
            Attorney.firm.isnot(None),
        )
        .distinct()
        .order_by(Attorney.firm)
    ).scalars().all()
    aliases = [a for a in alias_rows if a and a.strip()]

    # All attorneys ever linked (for history), grouped by external_id with their most
    # recent record for display
    all_attorney_records = db.session.execute(
        sa.select(Attorney)
        .where(Attorney.consolidated_firm_id == firm_id)
        .order_by(Attorney.external_id, Attorney.valid_from.desc())
    ).scalars().all()

    # Group by external_id, keeping the latest record for each
    latest_by_id = {}
    for a in all_attorney_records:
        if a.external_id not in latest_by_id:
            latest_by_id[a.external_id] = a

    return {
        "firm": firm,
        "incorporated_firms": inc_firms,
        "current_attorneys": current_attorneys,
        "aliases": aliases,
        "all_attorneys": sorted(latest_by_id.values(), key=lambda a: a.name or ""),
    }


def get_dashboard_stats():
    """Returns overview statistics for the home page dashboard."""
    today = datetime.date.today()

    # Total currently-valid attorneys
    total_attorneys = db.session.execute(
        temporal_query(Attorney, today, columns=[sa.func.count(Attorney.id)])
    ).scalar()

    # Total consolidated firms
    total_firms = db.session.execute(
        sa.select(sa.func.count(ConsolidatedFirm.id))
    ).scalar()

    # Total incorporated firms
    total_inc_firms = db.session.execute(
        sa.select(sa.func.count(IncorporatedFirm.id))
    ).scalar()

    # Recent movements (last 30 days)
    thirty_days_ago = today - datetime.timedelta(days=30)
    from app.models import Movement
    mov_query = get_movements_query(thirty_days_ago, today)
    mov_result = db.session.execute(mov_query).fetchall()
    recent_movements = [Movement(*row) for row in mov_result]

    # Top firms by attorney count
    firms_query = get_firms_query(today, "-attorney_count")
    firm_results = db.session.execute(firms_query).fetchall()[:10]
    top_firms = [
        {"name": f.name, "id": f.id, "slug": f.slug, "attorney_count": ac}
        for f, ac in firm_results
    ]

    # New registrations in last 30 days
    reg_query = get_registrations_query(thirty_days_ago, today)
    new_regs = db.session.execute(
        sa.select(sa.func.count())
        .select_from(reg_query.subquery())
    ).scalar()

    # Lapses in last 30 days
    lap_query = get_lapses_query(thirty_days_ago, today)
    lapses = db.session.execute(
        sa.select(sa.func.count())
        .select_from(lap_query.subquery())
    ).scalar()

    return {
        "total_attorneys": total_attorneys,
        "total_firms": total_firms,
        "total_inc_firms": total_inc_firms,
        "recent_movements": recent_movements,
        "top_firms": top_firms,
        "new_registrations_30d": new_regs,
        "lapses_30d": lapses,
    }


def get_oldest_date() -> datetime.date:
    """Return the earliest ``valid_from`` recorded in the register."""
    oldest = db.session.execute(
        sa.select(sa.func.min(Attorney.valid_from))
    ).scalar_one_or_none()
    return oldest or datetime.date.today()
