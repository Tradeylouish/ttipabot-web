import datetime
import math

import sqlalchemy as sa
from flask import abort, redirect, render_template, request, url_for

from app import db, queries
from app.main import bp
from app.models import Attorney, ConsolidatedFirm

REGISTER_VIEWS = {
    "attorneys": "Attorneys",
    "firms": "Firms",
    "updates": "Attorney updates",
}
LEGACY_UPDATE_VIEWS = {"registrations", "movements", "lapses"}
PER_PAGE = 12

# Keep this list in the same order as the fields shown in an attorney's
# current record.  Temporal rows are created when any of these business
# fields changes, not only when the attorney changes firm.
_ATTORNEY_HISTORY_FIELDS = queries.ATTORNEY_UPDATE_FIELDS
_ATTORNEY_HISTORY_FIELD_LABELS = queries.ATTORNEY_UPDATE_FIELD_LABELS


def _annotate_attorney_history(records: list) -> list[dict]:
    """Pair each temporal record with the fields changed from its predecessor.

    ``Attorney`` rows represent stable periods, so the first row is the
    baseline and every later row can be explained by comparing it with the
    preceding row.  The comparison intentionally uses the same truthiness
    normalisation as ``temporal_db.records_unchanged``: an empty value and
    ``None`` are both treated as not listed.
    """
    entries = []
    previous = None
    for record in records:
        changed_fields = []
        if previous is not None:
            for field in _ATTORNEY_HISTORY_FIELDS:
                old_value = getattr(previous, field, None)
                new_value = getattr(record, field, None)
                if (old_value or None) != (new_value or None):
                    changed_fields.append(field)
        # A new row with no business-field changes is normally a return to
        # the register after a lapse.  A gap can also accompany a changed
        # record, in which case both events are worth showing.
        registration_resumed = (
            previous is not None
            and previous.valid_to is not None
            and (
                not changed_fields
                or previous.valid_to < record.valid_from
            )
        )
        entries.append(
            {
                "record": record,
                "changed_fields": changed_fields,
                "other_changed_labels": [
                    _ATTORNEY_HISTORY_FIELD_LABELS[field]
                    for field in changed_fields
                    if field != "firm"
                ],
                "is_initial": previous is None,
                "registration_resumed": registration_resumed,
            }
        )
        previous = record
    return entries


def _date_arg(name: str, fallback: datetime.date) -> datetime.date:
    """Read an ISO date from the query string without turning a bad URL into a 500."""
    value = request.args.get(name, "").strip()
    if not value:
        return fallback
    try:
        return datetime.date.fromisoformat(value)
    except ValueError:
        return fallback


def _with_search(query, text: str, columns):
    """Apply the register's single keyword search to a SQLAlchemy select."""
    if not text:
        return query
    pattern = f"%{text}%"
    return query.where(sa.or_(*(column.ilike(pattern) for column in columns)))


def _paginate_rows(rows, page: int, per_page: int):
    """Paginate an already materialised list (used for joins and update events)."""
    page = max(page, 1)
    total = len(rows)
    start = (page - 1) * per_page
    return rows[start : start + per_page], total, _pagination(total, page, per_page)


def _pagination(total: int, page: int, per_page: int):
    total_pages = max(1, math.ceil(total / per_page))
    return {
        "page": page,
        "total_pages": total_pages,
        "has_prev": page > 1,
        "has_next": page < total_pages,
        "prev_url": _page_url(page - 1) if page > 1 else None,
        "next_url": _page_url(page + 1) if page < total_pages else None,
    }


def _page_url(page: int) -> str:
    """Keep the current search and filters when moving through result pages."""
    args = request.args.to_dict(flat=False)
    args["page"] = [str(page)]
    return url_for(request.endpoint, **args)


def _render_index(view_override: str | None = None):
    """Render the shared register explorer for a selected view."""
    view = view_override or request.args.get("view", "attorneys")
    if view in LEGACY_UPDATE_VIEWS:
        view = "updates"
    elif view not in REGISTER_VIEWS:
        view = "attorneys"

    page = request.args.get("page", 1, type=int) or 1
    page = max(page, 1)
    query_text = request.args.get("q", "").strip()[:100]
    filter_values = set(request.args.getlist("filter"))
    pat = "pat" in filter_values
    tm = "tm" in filter_values
    # Selecting both register types is equivalent to showing the whole
    # register; it should not accidentally hide records with no type tag.
    if pat and tm:
        pat = tm = False
    no_type_filter = not pat and not tm

    today = datetime.date.today()
    oldest_date = queries.get_oldest_date()
    snapshot_date = _date_arg("as_of", today)
    from_date = _date_arg("from_date", today - datetime.timedelta(days=30))
    to_date = _date_arg("to_date", today)
    if from_date > to_date:
        from_date, to_date = to_date, from_date
    # Keep the date selectors within the recorded register span.
    snapshot_date = min(max(snapshot_date, oldest_date), today)
    from_date = min(max(from_date, oldest_date), today)
    to_date = min(max(to_date, oldest_date), today)

    if view == "attorneys":
        order_by = request.args.get("orderBy", "name")
    else:
        order_by = request.args.get("orderBy", "-attorney_count")

    update_type = request.args.get("update_type", "").strip()
    if update_type not in queries.ATTORNEY_UPDATE_TYPE_LABELS:
        update_type = ""
    requested_update_fields = set(request.args.getlist("field"))
    selected_update_fields = requested_update_fields & set(
        queries.ATTORNEY_UPDATE_FIELDS
    )
    if not selected_update_fields:
        selected_update_fields = set(queries.ATTORNEY_UPDATE_FIELDS)

    items = []
    result_total = 0
    result_context = "Current register"

    if view == "attorneys":
        attorney_query = queries.get_attorneys_query(
            snapshot_date, order_by, pat, tm
        )
        attorney_query = _with_search(
            attorney_query,
            query_text,
            [Attorney.name, Attorney.firm, Attorney.address],
        )
        attorney_pagination = db.paginate(
            attorney_query, page=page, per_page=PER_PAGE, error_out=False
        )
        items = attorney_pagination.items
        result_total = attorney_pagination.total
        result_context = f"Snapshot as at {snapshot_date.isoformat()}"
        pagination = _pagination(result_total, page, PER_PAGE)

    elif view == "firms":
        firm_query = queries.get_firms_query(snapshot_date, order_by, pat, tm)
        if query_text:
            firm_query = firm_query.where(
                ConsolidatedFirm.name.ilike(f"%{query_text}%")
            )
        firm_rows = db.session.execute(firm_query).all()
        rows = [
            {"firm": firm, "attorney_count": attorney_count}
            for firm, attorney_count in firm_rows
        ]
        items, result_total, pagination = _paginate_rows(rows, page, PER_PAGE)
        result_context = f"Snapshot as at {snapshot_date.isoformat()}"

    elif view == "updates":
        updates = queries.get_attorney_updates(
            from_date,
            to_date,
            pat,
            tm,
            fields=selected_update_fields,
            update_type=update_type or None,
        )
        if query_text:
            needle = query_text.casefold()
            updates = [
                update
                for update in updates
                if any(
                    needle in (value or "").casefold()
                    for value in (
                        update.attorney.name,
                        update.attorney.firm,
                        update.attorney.address,
                    )
                )
            ]
        items, result_total, pagination = _paginate_rows(updates, page, PER_PAGE)
        result_context = (
            f"Recorded between {from_date.isoformat()} and {to_date.isoformat()}"
        )

    if view == "attorneys":
        search_action = url_for("main.attorney_search")
    elif view == "firms":
        search_action = url_for("main.firm_search")
    else:
        search_action = url_for("main.updates")

    return render_template(
        "home.html",
        request=request,
        search_action=search_action,
        view=view,
        view_label=REGISTER_VIEWS[view],
        items=items,
        result_total=result_total,
        result_context=result_context,
        pagination=pagination,
        query_text=query_text,
        pat=pat,
        tm=tm,
        no_type_filter=no_type_filter,
        snapshot_date=snapshot_date,
        from_date=from_date,
        to_date=to_date,
        oldest_date=oldest_date,
        today_iso=today.isoformat(),
        order_by=order_by,
        active_view=view,
        update_fields=queries.ATTORNEY_UPDATE_FIELDS,
        update_field_labels=queries.ATTORNEY_UPDATE_FIELD_LABELS,
        selected_update_fields=selected_update_fields,
        update_type_labels=queries.ATTORNEY_UPDATE_TYPE_LABELS,
        selected_update_type=update_type,
        clear_url=search_action,
    )


@bp.route("/")
def index():
    return _render_index()


@bp.route("/attorneys")
def attorney_search():
    return _render_index("attorneys")


@bp.route("/firms")
def firm_search():
    return _render_index("firms")


@bp.route("/updates")
def updates():
    return _render_index("updates")


@bp.route("/about")
def about():
    return render_template(
        "about.html",
        request=request,
        active_view="about",
    )


@bp.route("/ritual")
def ritual():
    return render_template("page.html", request=request)


@bp.route("/attorney/<external_id>")
def attorney_detail(external_id):
    history = queries.get_attorney_history(external_id)
    if not history:
        abort(404)
    latest = queries.get_attorney_latest(external_id)
    return render_template(
        "attorney.html",
        request=request,
        attorney=latest,
        history=history,
        history_entries=_annotate_attorney_history(history),
        active_view="attorneys",
    )


@bp.route("/firm/<slug>")
def firm_detail(slug):
    firm_id = ConsolidatedFirm.parse_slug(slug)
    if firm_id is None:
        abort(404)
    # Redirect to canonical slug if the URL doesn't match.
    detail = queries.get_consolidated_firm_detail(firm_id)
    if not detail:
        abort(404)
    canonical = detail["firm"].slug
    if slug != canonical:
        return redirect(url_for("main.firm_detail", slug=canonical), code=301)
    return render_template(
        "firm.html",
        request=request,
        active_view="firms",
        **detail,
    )
