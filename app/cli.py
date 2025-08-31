import datetime
import json
from pathlib import Path

import click
from flask import Blueprint

from app import data_migrator, db, queries, scraper
from app.models import Attorney, Firm

bp = Blueprint('cli', __name__, cli_group=None)

# --- Helper functions ---

def print_table(headers, rows):
    if not rows:
        click.echo("No results found.")
        return

    table_data = [headers] + [[str(cell) for cell in row] for row in rows]
    col_widths = [max(len(cell) for cell in col) for col in zip(*table_data)]

    header_line = " | ".join(f"{cell:<{col_widths[i]}}" for i, cell in enumerate(headers))
    click.echo(header_line)
    click.echo("-" * len(header_line))

    for row in rows:
        row_line = " | ".join(f"{str(cell):<{col_widths[i]}}" for i, cell in enumerate(row))
        click.echo(row_line)

# --- Reusable Click Options ---

def get_default_date_range():
    today = datetime.date.today()
    week_ago = today - datetime.timedelta(days=7)
    return (week_ago.isoformat(), today.isoformat())

def get_default_today():
    return datetime.date.today().isoformat()

dates_option = click.option(
    '--dates',
    nargs=2,
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=get_default_date_range,
    help='Start and end date (YYYY-MM-DD). Defaults to the last 7 days.'
)

date_option = click.option(
    '--date',
    type=click.DateTime(formats=["%Y-%m-%d"]),
    default=get_default_today,
    help='Date for query (YYYY-MM-DD). Defaults to today.'
)

pat_option = click.option('--pat', is_flag=True, show_default=True, default=False, help='Filter by patent attorneys.')
tm_option = click.option('--tm', is_flag=True, show_default=True, default=False, help='Filter by TM attorneys.')


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
def scrape():
    """Scrape the TTIPA register."""
    scraper.scrape_register()
    click.echo("Finished today's register scrape and DB update.")

@ttipabot.command()
def migrate_csvs():
    """Migrate historical CSV files to the database. Should be done after a single scrape to match up external IDs."""
    csv_directory = Path("scrapes")
    click.echo("Migration CSV data from scrapes directory")

    try:
        data_migrator.migrate_csvs(csv_directory)
    except FileNotFoundError as e:
        click.echo(f"Error: {e}")
    except Exception as e:
        click.echo(f"An unexpected error occurred: {e}")

    # Delete the newest scrape and readd it to complete migration
    data_migrator.delete_new_scrapes()
    scraper.scrape_register()

@ttipabot.command()
@click.argument('replace_id', required=False)
@click.argument('new_id', required=False)
@click.option('--file', type=click.Path(exists=True), help='JSON file with patches.')
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
            click.echo(f"Successfully patched external_id '{replace_id}' to '{new_id}'.")
        except Exception as e:
            click.echo(f"An error occurred: {e}")
    else:
        click.echo("Please provide either a --file option or both a replace_id and new_id.")

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

    click.echo(f"\nFinding attorney movements between {first_date.isoformat()} and {last_date.isoformat()}\n")
    query = queries.get_movements_query(first_date, last_date, pat, tm)
    results = db.session.execute(query).all()

    headers = ["Name", "From Firm", "To Firm", "Movement Date"]
    rows = [[new.name, old.firm, new.firm, new.valid_from.isoformat()] for old, new in results]
    print_table(headers, rows)

@ttipabot.command()
@dates_option
@pat_option
@tm_option
def registrations(dates, pat, tm):
    """Lists new attorneys registered in a given period."""
    first_date, last_date = dates[0].date(), dates[1].date()

    click.echo(f"\nFinding new registrations between {first_date.isoformat()} and {last_date.isoformat()}\n")
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

    click.echo(f"\nFinding lapses between {first_date.isoformat()} and {last_date.isoformat()}\n")
    query = queries.get_lapses_query(first_date, last_date, pat, tm)
    results = db.session.execute(query).scalars().all()

    headers = ["Name", "Firm", "Lapse Date"]
    rows = [[a.name, a.firm, a.valid_to.isoformat()] for a in results]
    print_table(headers, rows)

@ttipabot.command()
@date_option
@pat_option
@tm_option
def names(date, pat, tm):
    """Ranks attorneys by name length on a given date."""
    query_date = date.date()
    click.echo(f"\nRanking names for {query_date.isoformat()}\n")
    query = queries.get_attorneys_query(query_date, pat, tm)
    results = db.session.execute(query).scalars().all()

    headers = ["Rank", "Name", "Length"]
    rows = [[i + 1, a.name, len(a.name)] for i, a in enumerate(results)]
    print_table(headers, rows)

@ttipabot.command()
@pat_option
@tm_option
def firms(pat, tm):
    """Placeholder for firms command."""
    click.echo("Firms command not implemented yet.")
    pass
