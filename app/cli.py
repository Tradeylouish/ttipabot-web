import datetime
import json
from pathlib import Path
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

import click
import sqlalchemy as sa
from flask import Blueprint
from flask import current_app

from app import data_migrator, db, queries, scraper, history_reconstructor
from app.models import Attorney, IncorporatedFirm, ConsolidatedFirm

bp = Blueprint("cli", __name__, cli_group=None)

# --- Helper functions ---


def print_table(headers, rows):
    if not rows:
        click.echo("No results found.")
        return

    table_data = [headers] + [[str(cell) for cell in row] for row in rows]
    col_widths = [max(len(cell) for cell in col) for col in zip(*table_data)]

    header_line = " | ".join(
        f"{cell:<{col_widths[i]}}" for i, cell in enumerate(headers)
    )
    click.echo(header_line)
    click.echo("-" * len(header_line))

    for row in rows:
        row_line = " | ".join(
            f"{str(cell):<{col_widths[i]}}" for i, cell in enumerate(row)
        )
        click.echo(row_line)


# --- Reusable Click Options ---


def get_default_date_range():
    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=7)
    return (week_ago.isoformat(), today.isoformat())


def get_default_today():
    return datetime.date.today().isoformat()


dates_option = click.option(
    "--dates",
    nargs=2,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=get_default_date_range,
    help="Start and end date (YYYY-MM-DD). Defaults to the last 7 days.",
)

date_option = click.option(
    "--date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=get_default_today,
    help="Date for query (YYYY-MM-DD). Defaults to today.",
)

pat_option = click.option(
    "--pat",
    is_flag=True,
    show_default=True,
    default=False,
    help="Filter by patent attorneys.",
)
tm_option = click.option(
    "--tm",
    is_flag=True,
    show_default=True,
    default=False,
    help="Filter by TM attorneys.",
)


# --- CLI Command Group ---


@bp.cli.group()
def ttipabot():
    """Command line tool for interacting with the TTIPA register."""
    pass


# --- Individual Commands ---


@ttipabot.command()
def test():
    click.echo("Hello world")


@ttipabot.command()
@click.option(
    "--to",
    "to_addr",
    default=None,
    help="Override recipient (default: ADMINS from config).",
)
def test_email(to_addr):
    """Send a test email via SMTP to verify error-email config."""

    cfg = current_app.config
    host = cfg.get("MAIL_SERVER")
    port = cfg.get("MAIL_PORT")
    user = cfg.get("MAIL_USERNAME")
    pw = cfg.get("MAIL_PASSWORD")
    fr = cfg.get("MAIL_FROM")
    admins = cfg.get("ADMINS")
    recipients = [to_addr] if to_addr else admins

    if not host or not user or not pw or not fr or not recipients:
        click.echo(
            "❌ Missing mail config — check MAIL_SERVER, MAIL_USERNAME, "
            "MAIL_PASSWORD, MAIL_FROM, ADMINS in .env",
            err=True,
        )
        return

    click.echo(f"Server:   {host}:{port}")
    click.echo(f"User:     {user}")
    click.echo(f"From:     {fr}")
    click.echo(f"To:       {', '.join(recipients)}")
    click.echo()

    msg = MIMEMultipart()
    msg["From"] = fr
    msg["To"] = ", ".join(recipients)
    msg["Subject"] = "Test email — ttipabot-web error handler"
    msg.attach(MIMEText("SMTP error emailing via Mailgun is working!", "plain"))

    try:
        with smtplib.SMTP(host, port, timeout=15) as s:
            s.ehlo()
            if cfg.get("MAIL_USE_TLS"):
                s.starttls()
                s.ehlo()
            s.login(user, pw)
            s.sendmail(fr, recipients, msg.as_string())
        click.echo("✅ Test email sent!")
    except smtplib.SMTPAuthenticationError as e:
        click.echo(f"❌ Authentication failed: {e}", err=True)
    except Exception as e:
        click.echo(f"❌ Failed: {e}", err=True)


@ttipabot.command()
def scrape():
    """Scrape the TTIPA register."""
    scraper.scrape_register()
    click.echo("Finished today's register scrape and DB update.")


@ttipabot.command()
@click.argument("replace_id", required=False)
@click.argument("new_id", required=False)
@click.option("--file", type=click.Path(exists=True), help="JSON file with patches.")
def patch_ext_ids(replace_id, new_id, file):
    """Updates external_ids in the database from a file or arguments."""
    if file:
        try:
            with open(file) as f:
                patches = json.load(f)
            for old, new in patches.items():
                data_migrator.patch_external_ids(old, new)
                click.echo(f"Successfully patched external_id '{old}' to '{new}'.")
            click.echo("All patches from file processed successfully.")
        except Exception as e:
            click.echo(f"An error occurred while processing the file: {e}")
    elif replace_id and new_id:
        try:
            data_migrator.patch_external_ids(replace_id, new_id)
            click.echo(
                f"Successfully patched external_id '{replace_id}' to '{new_id}'."
            )
        except Exception as e:
            click.echo(f"An error occurred: {e}")
    else:
        click.echo(
            "Please provide either a --file option or both a replace_id and new_id."
        )


@ttipabot.command()
def dump():
    queries.dump_attorneys_to_csv("attorneys_dump.csv")
    queries.dump_firms_to_csv("firms_dump.csv")
    click.echo("Dumped attorneys and firms to CSV files.")


@ttipabot.command()
@dates_option
@pat_option
@tm_option
def movements(dates, pat, tm):
    """Lists attorney movements in a given period."""
    first_date, last_date = dates[0].date(), dates[1].date()

    click.echo(
        f"\nFinding attorney movements between {first_date.isoformat()} and {last_date.isoformat()}\n"
    )
    query = queries.get_movements_query(first_date, last_date, pat, tm)
    results = db.session.execute(query).all()

    headers = ["Name", "From Firm", "To Firm", "Movement Date"]
    rows = [
        [row.new_name, row.old_firm, row.new_firm, row.movement_date.isoformat()]
        for row in results
    ]
    print_table(headers, rows)


@ttipabot.command()
@dates_option
@pat_option
@tm_option
def registrations(dates, pat, tm):
    """Lists new attorneys registered in a given period."""
    first_date, last_date = dates[0].date(), dates[1].date()

    click.echo(
        f"\nFinding new registrations between {first_date.isoformat()} and {last_date.isoformat()}\n"
    )
    query = queries.get_registrations_query(first_date, last_date, pat, tm)
    results = db.session.execute(query).scalars().all()

    def get_reg_type(attorney):
        if attorney.patents and attorney.trademarks:
            return "Patents & Trademarks"
        elif attorney.patents:
            return "Patents"
        elif attorney.trademarks:
            return "Trademarks"
        return "N/A"

    headers = ["Name", "Firm", "Registration Type"]
    rows = [[a.name, a.firm, get_reg_type(a)] for a in results]
    print_table(headers, rows)


@ttipabot.command()
@dates_option
@pat_option
@tm_option
def lapses(dates, pat, tm):
    """Lists attorneys whose registration lapsed in a given period."""
    first_date, last_date = dates[0].date(), dates[1].date()

    click.echo(
        f"\nFinding lapses between {first_date.isoformat()} and {last_date.isoformat()}\n"
    )
    query = queries.get_lapses_query(first_date, last_date, pat, tm)
    results = db.session.execute(query).scalars().all()

    headers = ["Name", "Firm", "Lapse Date"]
    rows = [[a.name, a.firm, a.valid_to.isoformat()] for a in results]
    print_table(headers, rows)


@ttipabot.command()
@date_option
@click.option(
    "--limit", type=int, default=10, help="Number of attorneys to rank (default: 10)."
)
@pat_option
@tm_option
def names(date, limit, pat, tm):
    """Ranks attorneys by name length on a given date."""
    query_date = date.date()
    click.echo(f"\nRanking top {limit} names by length for {query_date.isoformat()}\n")
    query = queries.get_attorneys_query(query_date, "-name_length", pat, tm)
    results = db.session.execute(query).scalars().all()

    headers = ["Rank", "Name", "Length"]
    rows = [[i + 1, a.name, len(a.name)] for i, a in enumerate(results[:limit])]
    print_table(headers, rows)


@ttipabot.command()
@click.option(
    "--limit", type=int, default=10, help="Number of firms to rank (default: 10)."
)
@pat_option
@tm_option
def firms(limit, pat, tm):
    """Ranks firms by number of related attorneys."""
    today = datetime.date.today()

    # Get current attorneys (valid as of today) with their consolidated firm
    filters = [
        Attorney.valid_from <= today,
        sa.or_(Attorney.valid_to.is_(None), Attorney.valid_to >= today),
    ]
    if pat:
        filters.append(Attorney.patents == True)
    if tm:
        filters.append(Attorney.trademarks == True)

    attorneys_query = (
        sa.select(
            Attorney.consolidated_firm_id, sa.func.count(Attorney.id).label("count")
        )
        .where(sa.and_(*filters))
        .group_by(Attorney.consolidated_firm_id)
    )

    firm_counts = db.session.execute(attorneys_query).all()

    # Get firm details
    firms_query = sa.select(ConsolidatedFirm)
    all_firms = db.session.execute(firms_query).scalars().all()
    firm_names = {f.id: f.name for f in all_firms}

    # Build results
    results = []
    for firm_id, count in firm_counts:
        if firm_id and firm_id in firm_names:
            results.append((firm_names[firm_id], count))

    # Sort by count descending
    results.sort(key=lambda x: -x[1])

    headers = ["Rank", "Firm", "Attorney Count"]
    rows = [[i + 1, name, count] for i, (name, count) in enumerate(results[:limit])]
    print_table(headers, rows)


@ttipabot.command()
def populate_firm_records():
    """Populates consolidated_firms table and matches attorneys and incorporated firms to it."""
    click.echo("Populating consolidated firm records...")
    click.echo("This process:")
    click.echo("1. Clears and repopulates the consolidated_firms table")
    click.echo("2. Deduplicates firm names from attorneys using normalized matching")
    click.echo("3. Matches attorneys to consolidated_firms (sets consolidated_firm_id)")
    click.echo(
        "4. Matches consolidated_firms to incorporated_firms (sets incorporated_firm.consolidated_firm_id)"
    )
    click.echo("")

    try:
        data_migrator.populate_firm_records()
        click.echo("\nFirm record population completed successfully!")
    except Exception as e:
        click.echo(f"\nAn error occurred during firm record population: {e}")
        raise


@ttipabot.command()
@click.option(
    "--date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    required=True,
    help="The valid_to date of the false lapses to recover (YYYY-MM-DD).",
)
def recover_false_lapses(date):
    """Recovers attorneys incorrectly lapsed on a given date.

    For every attorney row whose valid_to equals --date, looks up the
    attorney's current record on the live register:
      - if the live record is unchanged from the lapsed row, the false lapse
        is reopened (valid_to set back to NULL) for a clean continuous history;
      - if the live record differs, a new row is inserted with
        valid_from = --date and valid_to = NULL, on the assumption that the
        change occurred on that date (the old row keeps valid_to = --date).
      - if the attorney is no longer on the live register at all, the lapse
        is left as-is (treated as a genuine lapse).
    """
    from app import temporal_db
    from app.models import Attorney

    target_date = date.date()

    # Ensure we have a fresh scrape to compare against, then build models.
    scrapes_dir = Path("scrapes")
    scrapes_dir.mkdir(exist_ok=True)
    today = datetime.date.today().isoformat()
    file_path = scrapes_dir / f"{today}.json"
    if not file_path.exists():
        scraper.json_dump_register(file_path)
    data = scraper.get_register_data(file_path)
    attorneys_raw, _ = scraper.separate_data(data)
    live_models, _ = scraper.convert_to_models(attorneys_raw, [])
    live_by_id = {a.external_id: a for a in live_models}

    lapsed_rows = (
        db.session.execute(sa.select(Attorney).where(Attorney.valid_to == target_date))
        .scalars()
        .all()
    )
    click.echo(
        f"Found {len(lapsed_rows)} attorney row(s) lapsed on {target_date.isoformat()}."
    )

    reopened = 0
    inserted = 0
    kept = 0
    new_ids = []
    for row in lapsed_rows:
        live = live_by_id.get(row.external_id)
        if live is None:
            click.echo(f"  KEEP (not on live register): {row.name} [{row.external_id}]")
            kept += 1
            continue
        # Reopen only if the lapsed row matches the live record on business fields.
        if temporal_db.records_unchanged(row, live):
            row.valid_to = None
            reopened += 1
            click.echo(f"  REOPEN (unchanged):          {row.name}")
        else:
            # Insert a new row dated target_date with the live data.
            new = Attorney(
                external_id=live.external_id,
                name=live.name,
                phone=live.phone,
                email=live.email,
                firm=live.firm,
                address=live.address,
                additional_information=live.additional_information,
                patents=live.patents,
                trademarks=live.trademarks,
                valid_from=target_date,
                valid_to=None,
            )
            db.session.add(new)
            db.session.flush()
            new_ids.append(new.id)
            inserted += 1
            click.echo(f"  INSERT changed row ({target_date.isoformat()}): {row.name}")

    db.session.commit()

    # Link any newly inserted attorneys to consolidated firms.
    if new_ids:
        data_migrator.link_attorneys_to_consolidated_firms(new_ids)
        data_migrator.update_attorney_firm_links()

    click.echo("")
    click.echo(
        f"Done. Reopened {reopened}, inserted {inserted}, kept {kept} (genuine lapse)."
    )


@ttipabot.command()
@click.option(
    "--from",
    "from_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    required=True,
    help="First date of the reconstruction window (YYYY-MM-DD). A "
    "snapshot JSON for this date must exist in scrapes/.",
)
@click.option(
    "--to",
    "to_date",
    type=click.DateTime(formats=["%Y-%m-%d"]),
    required=True,
    help="Last date of the reconstruction window (inclusive).",
)
@click.option(
    "--apply",
    is_flag=True,
    default=False,
    help="Apply the changes to the DB. Without this flag, only a plan "
    "is printed and no changes are made.",
)
@click.option(
    "--scrapes-dir",
    type=click.Path(exists=True, file_okay=False),
    default="scrapes",
    help="Directory containing the snapshot JSON files (default: scrapes).",
)
def reconstruct_history(from_date, to_date, apply, scrapes_dir):
    """Reconstruct attorney history from preserved scrape JSON snapshots.

    Replays every daily snapshot in the window [FROM, TO] (inclusive) and
    rewrites the temporal attorneys rows for that window so changes are dated
    to the day they actually appeared, instead of being lumped onto the next
    successful scrape. Requires a snapshot JSON for every day in the window.

    By default prints a plan and makes no changes; pass --apply to commit.
    """

    fd = from_date.date()
    td = to_date.date()
    if fd >= td:
        click.echo("--from must be earlier than --to.")
        return

    click.echo(
        f"Reconstructing attorney history for {fd.isoformat()} -> "
        f"{td.isoformat()} (apply={apply})"
    )
    result = history_reconstructor.reconstruct_history(
        from_date=fd,
        to_date=td,
        scrapes_dir=Path(scrapes_dir),
        apply=apply,
        verbose=True,
    )
    if not apply:
        click.echo(
            f"\nDry run: {result['n_changed']} attorneys would be changed. "
            f"Re-run with --apply to commit."
        )
