"""Reconstruct attorney temporal history from preserved scrape JSON snapshots.

When the nightly scraper is broken for a stretch (as happened 2026-06-26 ->
2026-07-05), the temporal ``attorneys`` table stops gaining the per-day version
rows that record firm moves / address changes / re-registrations. Today's
scrape then lumps every change onto a single ``valid_from = today``.

If the scrape JSON files for the broken days were preserved (they are, in
``scrapes/``), we can replay them and rebuild the correct history.

This module computes the *ideal* history for the crash window and applies it
to the DB: closing the predecessor row at the right date, inserting a new
version row dated to the day the change actually appeared, and back-dating
genuine new registrations to the day they first appeared.

Contract
--------
- The DB is assumed correct up through ``from_date`` (exclusive of changes on
  ``from_date`` itself).
- Snapshots for every day in ``[from_date, to_date]`` must be available on
  disk; missing snapshots raise ``FileNotFoundError``.
- Only attorneys whose ideal history (for the window) differs from the DB's
  current state are touched.
- A row is only ever modified/deleted within the window: its ``valid_to`` may
  be moved, its ``valid_from`` may be moved (for rows whose ``valid_from``
  falls inside the window), or a new row may be inserted. Pre-window rows
  (``valid_from < from_date``) keep their ``valid_from``; at most their
  ``valid_to`` is adjusted to fall within the window.
"""
import datetime
import json
from pathlib import Path

import sqlalchemy as sa
from flask import current_app

from app import db
from app.models import Attorney
from app.scraper import convert_to_models, extract_html_data, separate_data

# Business fields, mirroring temporal_db._BUSINESS_FIELDS["attorneys"]. We
# snapshot them as a tuple so two records compare by value.
_BUSINESS = (
    "name",
    "phone",
    "email",
    "firm",
    "address",
    "additional_information",
    "patents",
    "trademarks",
)


def _fields_tuple(rec):
    return tuple((getattr(rec, f) or None) for f in _BUSINESS)


def _load_snapshot(path: Path) -> dict:
    """Return ``{external_id: Attorney (detached)}`` for one snapshot JSON."""
    data = json.loads(path.read_text(encoding="utf-8"))
    results = extract_html_data(data["Results"])
    att_raw, _ = separate_data(results)
    models, _ = convert_to_models(att_raw, [])
    by_id = {}
    for a in models:
        # Deduplicate by external_id (the register has served duplicates); keep
        # the populated one. If both populated, last wins -- same id, same
        # business fields typically.
        if a.external_id not in by_id or (
            by_id[a.external_id].name in (None, "") and a.name not in (None, "")
        ):
            by_id[a.external_id] = a
    return by_id


def _pre_window_rows(from_date: datetime.date) -> dict:
    """``{external_id: [row, ...]}`` for rows valid as of ``from_date``.

    Returns a list per id because a broken-recovery DB can have multiple
    rows open at once (one genuine, one spurious); the caller picks the one
    whose fields match the baseline snapshot.
    """
    rows = (
        db.session.execute(
            sa.select(Attorney).where(
                Attorney.valid_from <= from_date,
                sa.or_(Attorney.valid_to == None, Attorney.valid_to > from_date),
            )
        )
        .scalars()
        .all()
    )
    out = {}
    for r in rows:
        out.setdefault(r.external_id, []).append(r)
    return out


def _genuine_predecessors(from_date: datetime.date) -> dict:
    """``{external_id: row}`` for the latest DB row closed at or before ``from_date``.

    These are rows that lapsed for real *before* the reconstruction window
    (e.g. ``valid_to = 2026-05-26`` when the window starts 2026-06-25). Their
    lapse is already correctly recorded, so when the attorney is absent from
    the baseline snapshot we know not to manufacture a second close entry --
    any open-as-of-from_date rows for that attorney are spurious and get
    deleted outright.
    """
    rows = (
        db.session.execute(
            sa.select(Attorney).where(
                Attorney.valid_to != None,
                Attorney.valid_to <= from_date,
            ).order_by(Attorney.external_id, Attorney.valid_from.desc())
        )
        .scalars()
        .all()
    )
    out = {}
    for r in rows:
        # keep the latest (order_by desc -> first seen is latest)
        if r.external_id not in out:
            out[r.external_id] = r
    return out


def _window_rows(from_date: datetime.date, to_date: datetime.date) -> dict:
    """``{external_id: [row, ...]}`` for all rows touching the window.

    Includes pre-window rows whose ``valid_to`` falls inside the window, and
    rows whose ``valid_from`` falls inside the window.
    """
    rows = (
        db.session.execute(
            sa.select(Attorney).where(
                sa.or_(
                    # Rows opened during the window
                    sa.and_(Attorney.valid_from > from_date, Attorney.valid_from <= to_date),
                    # Pre-window rows that close during the window
                    sa.and_(
                        Attorney.valid_from <= from_date,
                        Attorney.valid_to != None,
                        Attorney.valid_to > from_date,
                        Attorney.valid_to <= to_date,
                    ),
                    # Pre-window rows still open (valid_to NULL or > to_date)
                    sa.and_(
                        Attorney.valid_from <= from_date,
                        sa.or_(Attorney.valid_to == None, Attorney.valid_to > to_date),
                    ),
                )
            ).order_by(Attorney.external_id, Attorney.valid_from)
        )
        .scalars()
        .all()
    )
    out = {}
    for r in rows:
        out.setdefault(r.external_id, []).append(r)
    return out


def _snap_dates_in_range(scrapes_dir: Path, from_date, to_date) -> list:
    dates = []
    d = from_date
    while d <= to_date:
        p = scrapes_dir / f"{d.isoformat()}.json"
        if not p.exists():
            raise FileNotFoundError(
                f"Missing snapshot for {d.isoformat()}: {p}. History "
                f"reconstruction requires a snapshot for every day in the "
                f"window."
            )
        dates.append((d, p))
        d += datetime.timedelta(days=1)
    return dates


def _build_ideal_history(ext_id, snapshots, baseline, pre_window, genuine_predecessors, from_date):
    """Compute the ideal history for one external_id across the window.

    Returns a list of dicts: ``{valid_from, valid_to, fields, source, pre_row}``.
    ``valid_from`` is None for the pre-window row (means: keep existing
    valid_from). ``valid_to`` is None for the still-open final row.
    ``pre_row`` is the DB row to preserve/adjust for the first ideal entry
    (or None if the first entry is a fresh insert).

    ``baseline`` is the first snapshot (the register's actual state on
    ``from_date``). It is the authoritative source of truth for whether an
    attorney was on the register at the window's start.

    ``genuine_predecessors`` is ``{ext_id: row}`` for the latest DB row that
    closed at or before ``from_date`` (a real lapse from before the window).
    If such a row exists for an attorney who is absent from the baseline, the
    lapse is *already* recorded in the DB, so any other rows open at
    ``from_date`` are spurious and will be deleted (not closed again).
    """
    history = []
    open_rec = None
    pre = pre_window.get(ext_id, [])
    genuine = genuine_predecessors.get(ext_id)

    baseline_rec = baseline.get(ext_id)
    if baseline_rec is not None:
        # Attorney on the register at from_date. The genuine predecessor is
        # the open DB row whose business fields match the baseline.
        candidate = None
        for r in pre:
            if _fields_tuple(r) == _fields_tuple(baseline_rec):
                candidate = r
                break
        if candidate is None and pre:
            candidate = pre[0]
        open_rec = {
            "valid_from": None,
            "fields": _fields_tuple(baseline_rec),
            "source": "pre-window",
            "pre_row": candidate,
        }
    else:
        # Attorney absent from baseline at from_date. Two sub-cases:
        #  (a) A genuine pre-window row already closed at/before from_date
        #      (``genuine`` is set): the lapse is already recorded, so any
        #      rows still open at from_date are spurious and get deleted by
        #      the apply step. The ideal history begins with (re)appearance
        #      only; no synthetic close entry is emitted.
        #  (b) No genuine closed predecessor (the attorney was wrongly left
        #      open at from_date): close the earliest open row at from_date
        #      so the lapse is recorded, then start (re)appearance.
        open_rec = None
        if genuine is None and pre:
            earliest = min(pre, key=lambda r: r.valid_from)
            history.append({
                "valid_from": None,
                "valid_to": from_date,
                "fields": _fields_tuple(earliest),
                "source": "pre-window (absent from baseline; closing at from_date)",
                "pre_row": earliest,
            })
        # If genuine is set, the lapse is already recorded; open_rec stays None
        # and any spurious open rows will be deleted by the apply step.

    for d, snap in snapshots:  # snap is {ext_id: Attorney}
        rec = snap.get(ext_id)
        if open_rec is None:
            if rec is not None:
                # (Re)appearance on d
                open_rec = {
                    "valid_from": d,
                    "fields": _fields_tuple(rec),
                    "source": d.isoformat(),
                }
            # else still absent -- nothing
        else:
            if rec is None:
                # Lapse on d
                history.append({**open_rec, "valid_to": d})
                open_rec = None
            else:
                snap_flds = _fields_tuple(rec)
                if open_rec["fields"] != snap_flds:
                    # Changed on d
                    history.append({**open_rec, "valid_to": d})
                    open_rec = {
                        "valid_from": d,
                        "fields": snap_flds,
                        "source": d.isoformat(),
                    }
                # else unchanged -- continue
    if open_rec is not None:
        history.append({**open_rec, "valid_to": None})
    return history


def _apply_fields(row, new_record):
    """Copy business fields from a snapshot-derived Attorney onto a row."""
    for f in (
        "name", "phone", "email", "firm", "address",
        "additional_information", "patents", "trademarks",
    ):
        setattr(row, f, getattr(new_record, f))


def reconstruct_history(from_date, to_date, scrapes_dir=None, apply=False, verbose=True):
    """Reconstruct attorney temporal history for ``[from_date, to_date]``.

    Snapshots must exist for every day in the range (inclusive) under
    ``scrapes_dir``. By default prints a plan and makes no DB changes; pass
    ``apply=True`` to commit.
    """
    scrapes_dir = Path(scrapes_dir or Path("scrapes"))
    snap_paths = _snap_dates_in_range(scrapes_dir, from_date, to_date)
    snapshots = [(d, _load_snapshot(p)) for d, p in snap_paths]
    if verbose:
        current_app.logger.info(
            "reconstruct_history: loaded %d snapshots (%s -> %s)",
            len(snapshots), from_date.isoformat(), to_date.isoformat(),
        )

    # The baseline (first snapshot day) defines the pre-window state.
    from_date = snap_paths[0][0]
    baseline = snapshots[0][1]
    window_snaps = snapshots[1:]  # subsequent days

    pre_window = _pre_window_rows(from_date)
    genuine_predecessors = _genuine_predecessors(from_date)
    db_rows = _window_rows(from_date, to_date)

    all_ids = set(baseline.keys())
    for _d, snap in window_snaps:
        all_ids |= set(snap.keys())
    all_ids |= set(db_rows.keys())

    # Build ideal history per attorney and diff against DB.
    plans = []  # list of (ext_id, name, action, detail)
    new_rows_to_link = []

    for ext_id in sorted(all_ids):
        ideal = _build_ideal_history(ext_id, window_snaps, baseline, pre_window, genuine_predecessors, from_date)
        cur = db_rows.get(ext_id, [])

        if _histories_match(ideal, cur, from_date):
            continue

        name = "?"
        if ext_id in baseline:
            name = f"{baseline[ext_id].name or ext_id[:8]}"
        else:
            for _d, snap in window_snaps:
                if ext_id in snap:
                    name = f"{snap[ext_id].name or ext_id[:8]}"
                    break
        plans.append((ext_id, name, ideal, cur))

    # Render the plan.
    if verbose:
        click_echo = current_app.logger.info
        print(f"\nReconstruction plan for {from_date.isoformat()} -> {to_date.isoformat()}")
        print(f"Attorneys needing changes: {len(plans)}\n")

    n_redate = 0
    n_insert = 0
    n_close = 0
    n_delete = 0

    for ext_id, name, ideal, cur in plans:
        if verbose:
            print(f"  {name}  ({ext_id[:8]}...)")
            print(f"    ideal: {[(str(h['valid_from']) if h['valid_from'] else 'pre', str(h['valid_to']) if h['valid_to'] else 'open', h['fields'][3] or '') for h in ideal]}")
            print(f"    db:    {[(str(r.valid_from), str(r.valid_to) if r.valid_to else 'open', _fields_tuple(r)[3] or '') for r in cur]}")

        if not apply:
            continue

        # Apply: rewrite this attorney's rows in the window to match the ideal.
        #
        # The ideal's first entry is either the genuine pre-window row
        # (``valid_from is None``; ``pre_row`` points at the matching DB row)
        # or a (re)appearance during the window (attorney was absent from the
        # baseline snapshot, so there's no pre-window row to preserve).
        #
        # Every DB row touching the window EXCEPT the genuine pre-window row
        # is deleted -- this removes spurious recovery rows and mis-dated
        # window rows -- and the ideal is re-inserted cleanly.
        first = ideal[0]
        pre_row = first.get("pre_row") if first["valid_from"] is None else None
        # Delete every DB row that overlaps the window, EXCEPT the genuine
        # pre-window row we're preserving. Rows that closed strictly before
        # the window (valid_to <= from_date) are left untouched -- they are
        # legitimate history from outside our scope.
        def _overlaps_window(r):
            # Open during the window, or opens within it.
            if r.valid_to is None or r.valid_to > from_date:
                return True
            return r.valid_from > from_date
        rows_to_delete = [
            r for r in cur
            if r is not pre_row and _overlaps_window(r)
        ]

        if pre_row is not None:
            # First ideal entry is the pre-window row; adjust its valid_to.
            pre_row.valid_to = first["valid_to"]
            remaining = ideal[1:]
        else:
            # No genuine pre-window row; first ideal entry is a (re)appearance.
            remaining = ideal[:]

        # Delete every other DB row touching the window (spurious intermediates,
        # mis-dated window rows, duplicates, etc.). They get rebuilt below.
        for r in rows_to_delete:
            db.session.delete(r)
            n_delete += 1

        # Insert new rows for `remaining`.
        # We need source Attorney records; pull from the snapshot on the
        # ideal entry's valid_from date.
        snap_by_date = {d: s for d, s in window_snaps}
        for entry in remaining:
            d = entry["valid_from"]
            snap_rec = snap_by_date[d].get(ext_id)
            if snap_rec is None:
                # Shouldn't happen: an ideal entry with valid_from=d means
                # the record appeared in snapshot d. Skip defensively.
                current_app.logger.warning(
                    "reconstruct_history: no snapshot record for %s on %s; "
                    "skipping an ideal row.", ext_id, d.isoformat()
                )
                continue
            new_row = Attorney(
                external_id=snap_rec.external_id,
                name=snap_rec.name,
                phone=snap_rec.phone,
                email=snap_rec.email,
                firm=snap_rec.firm,
                address=snap_rec.address,
                additional_information=snap_rec.additional_information,
                patents=snap_rec.patents,
                trademarks=snap_rec.trademarks,
                valid_from=d,
                valid_to=entry["valid_to"],
            )
            db.session.add(new_row)
            db.session.flush()
            new_rows_to_link.append(new_row.id)
            if entry["valid_to"] is None:
                n_insert += 1
            else:
                n_close += 1

        # If pre_window row had its valid_to moved into the window (i.e. the
        # attorney lapsed during the window) that's a "close".
        if pre_row is not None and ideal[0]["valid_to"] is not None:
            n_close += 1
        # If pre_row had its valid_to moved from a window date back to None
        # (reopened), count as redate.
        n_redate += 1

    if apply:
        db.session.commit()
        # Re-link consolidated firms for any rows we inserted whose firm moved.
        if new_rows_to_link:
            from app import data_migrator
            data_migrator.link_attorneys_to_consolidated_firms(new_rows_to_link)
            data_migrator.update_attorney_firm_links()

    if verbose:
        print(f"\nPlan summary: {len(plans)} attorneys to change")
        if apply:
            print(f"Applied: redated/adjusted {n_redate}, inserted {n_insert}, "
                  f"closed {n_close}, deleted {n_delete} window rows.")

    return {
        "n_changed": len(plans),
        "n_redate": n_redate,
        "n_insert": n_insert,
        "n_close": n_close,
        "n_delete": n_delete,
        "applied": apply,
        "plans": plans,
    }


def _histories_match(ideal, cur_rows, from_date):
    """True if the ideal history (list of dicts) matches the DB rows.

    Only rows that *overlap the window* (open at any point on or after
    ``from_date``) are compared. Rows that closed strictly before the window
    (``valid_to <= from_date``) are legitimate pre-window history and are
    ignored, so they don't trip the diff.
    """
    ideal_norm = [(h["valid_from"], h["valid_to"], h["fields"]) for h in ideal]
    cur_norm = []
    for r in cur_rows:
        if r.valid_to is not None and r.valid_to <= from_date and r.valid_from <= from_date:
            continue  # closed before the window -- out of scope
        vf = None if r.valid_from <= from_date else r.valid_from
        cur_norm.append((vf, r.valid_to, _fields_tuple(r)))
    return ideal_norm == cur_norm