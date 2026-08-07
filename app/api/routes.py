import datetime

import sqlalchemy as sa
from flask import request

from app import db, queries
from app.api import bp
from app.models import Attorney, IncorporatedFirm, ConsolidatedFirm


def get_filters(args) -> tuple[bool, bool]:
    filters = args.getlist("filter")
    pat = "pat" in filters
    tm = "tm" in filters
    return pat, tm


def to_date(date_str: str) -> datetime.date:
    return datetime.date.fromisoformat(date_str)


@bp.route("/registrations")
def registrations():
    pat, tm = get_filters(request.args)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)

    first_date = request.args.get("first_date", default=None, type=to_date)
    last_date = request.args.get(
        "last_date", default=datetime.date.today(), type=to_date
    )

    # Rather than provide a default first_date to args.get, calculate it here based on last_date if not provided
    first_date = (
        last_date - datetime.timedelta(days=7) if not first_date else first_date
    )

    query = queries.get_registrations_query(first_date, last_date, pat, tm)

    endpoint_kwargs = {
        "first_date": first_date.isoformat(),
        "last_date": last_date.isoformat(),
        "filter": request.args.getlist("filter"),
    }
    return Attorney.to_collection_dict(
        query, page, per_page, "api.registrations", **endpoint_kwargs
    )


@bp.route("/movements")
def movements():
    from app.models import Movement

    pat, tm = get_filters(request.args)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)

    first_date = request.args.get("first_date", default=None, type=to_date)
    last_date = request.args.get(
        "last_date", default=datetime.date.today(), type=to_date
    )

    first_date = (
        last_date - datetime.timedelta(days=7) if not first_date else first_date
    )

    query = queries.get_movements_query(first_date, last_date, pat, tm)

    result = db.session.execute(query)
    rows = result.fetchall()
    movements = [Movement(*row) for row in rows]

    endpoint_kwargs = {
        "first_date": first_date.isoformat(),
        "last_date": last_date.isoformat(),
        "filter": request.args.getlist("filter"),
    }
    return Attorney.to_collection_dict_from_rows(
        movements, page, per_page, len(movements), "api.movements", **endpoint_kwargs
    )


@bp.route("/lapses")
def lapses():
    pat, tm = get_filters(request.args)

    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)

    first_date = request.args.get("first_date", default=None, type=to_date)
    last_date = request.args.get(
        "last_date", default=datetime.date.today(), type=to_date
    )

    # Rather than provide a default first_date to args.get, calculate it here based on last_date if not provided
    first_date = (
        last_date - datetime.timedelta(days=7) if not first_date else first_date
    )

    query = queries.get_lapses_query(first_date, last_date, pat, tm)

    endpoint_kwargs = {
        "first_date": first_date.isoformat(),
        "last_date": last_date.isoformat(),
        "filter": request.args.getlist("filter"),
    }
    return Attorney.to_collection_dict(
        query, page, per_page, "api.lapses", **endpoint_kwargs
    )


@bp.route("/attorneys")
def attorneys():
    pat, tm = get_filters(request.args)
    date = request.args.get("date", default=datetime.date.today(), type=to_date)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    order_by_param = request.args.get("orderBy", default="-name_length", type=str)

    query = queries.get_attorneys_query(date, order_by_param, pat, tm)

    endpoint_kwargs = {
        "date": date.isoformat(),
        "filter": request.args.getlist("filter"),
        "orderBy": order_by_param,
    }
    return Attorney.to_collection_dict(
        query, page, per_page, "api.attorneys", **endpoint_kwargs
    )


@bp.route("/firms")
def firms():
    date = request.args.get("date", default=datetime.date.today(), type=to_date)
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 10, type=int)
    order_by_param = request.args.get("orderBy", default="-attorney_count", type=str)

    query = queries.get_firms_query(date, order_by_param)

    # Execute query and get results
    results = db.session.execute(query).all()

    # Calculate pagination
    total = len(results)
    total_pages = (total + per_page - 1) // per_page
    start = (page - 1) * per_page
    end = start + per_page
    page_items = results[start:end]

    # Build items with attorney_count
    items = []
    for firm, attorney_count in page_items:
        item = {
            "name": firm.name,
            "attorney_count": attorney_count,
        }
        items.append(item)

    return {
        "items": items,
        "_meta": {
            "page": page,
            "per_page": per_page,
            "total_pages": total_pages,
            "total_items": total,
        },
        "_links": {
            "self": f"/api/firms?page={page}&per_page={per_page}&date={date.isoformat()}&orderBy={order_by_param}",
            "next": f"/api/firms?page={page + 1}&per_page={per_page}&date={date.isoformat()}&orderBy={order_by_param}"
            if page < total_pages
            else None,
            "prev": f"/api/firms?page={page - 1}&per_page={per_page}&date={date.isoformat()}&orderBy={order_by_param}"
            if page > 1
            else None,
        },
    }


@bp.route("/oldest-date")
def oldest_date():
    """Returns the oldest date in the database."""
    oldest = db.session.execute(
        sa.select(sa.func.min(Attorney.valid_from))
    ).scalar_one_or_none()
    if oldest:
        return {"oldest_date": oldest.isoformat()}
    return {"oldest_date": datetime.date.today().isoformat()}


@bp.route("/boom")
def boom():
    raise RuntimeError("SMTP handler smoke test")
