import sqlalchemy as sa
import sqlalchemy.orm as so
from app import app, db
from app.models import Attorney, Firm
from app.csv_migrate import migrate_csvs
from app.scraper import delete_control_chars, parse_html
from app.queries import print_head, dump_attorneys_to_csv
from pathlib import Path

@app.shell_context_processor
def make_shell_context():
    return {'sa': sa, 'so': so, 'db': db, 'User': Attorney, 'Firm': Firm}

@app.cli.command("migrate_csvs")
def migrate_csvs_command():
    """Migrate CSV files to the database."""
    csv_directory = Path("scrapes")
    print("Ran command migrate_csvs")

    try:
        migrate_csvs(csv_directory)
    except FileNotFoundError as e:
        print(f"Error: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        
@app.cli.command("parse_html")
def parse_html_command():
    html = "\r\n\r\n\r\n\r\n    <div class=\"list-item firm\">\r\n      <div class=\"block\">\r\n        <span> Firm </span>\r\n        <h4>JLTF Holdings Pty Ltd trading as IP Flourish</h4>\r\n      </div>\r\n      <div class=\"contact block\">\r\n      \r\n        <div class=\"block-1\">\r\n          <span> Phone </span>\r\n          <span>\r\n            <a href=\"tel:+617 3177 3365\" class=\"btn btn-secondary btn-textOnly\">+617 3177 3365</a>\r\n          </span>\r\n        </div>\r\n      \r\n      \r\n      \r\n        <div class=\"block-2\">\r\n          <span> Email </span>\r\n          <span>\r\n            <a href=\"mailto:mail@ipflourish.com\" class=\"btn btn-secondary btn-textOnly\">mail@ipflourish.com</a>\r\n          </span>\r\n        </div>\r\n      \r\n\r\n      \r\n      \r\n        <div class=\"block-3\">\r\n          <span> Website </span>\r\n          <span>\r\n              <a class=\"btn btn-secondary btn-textOnly\" target=\"_blank\" rel=\"noopener noreferrer\" href=\"http://www.ipflourish.com\">JLTF Holdings Pty Ltd trading as IP Flourish</a>\r\n          </span>\r\n        </div>\r\n      \r\n      </div>\r\n\r\n      \r\n        <div class=\"block\">\r\n          <span> Company Directors </span>\r\n          <span>Timothy Liam Fitzgerald</span>\r\n        </div>\r\n      \r\n\r\n      \r\n      <div class=\"block\">\r\n        <span> Address </span><span>\r\n          8 82 Berwick Street Fortitude Valley QLD 4006 Australia\r\n        </span>\r\n      </div>\r\n      \r\n\r\n       \r\n        <div class=\"block\">\r\n          <span> Registered as</span>\r\n          <div class=\"tags\">       \r\n          \r\n              <span class=\"ipr-tag ipr-P\">Patents</span>\r\n          \r\n              <span class=\"ipr-tag ipr-TM\">Trade marks</span>\r\n            \r\n          </div>\r\n        </div>\r\n      \r\n    </div>\r\n  \r\n\r\n  "
    
    html = delete_control_chars(html)
    data = parse_html(html)
    
    print(data)
    
@app.cli.command("dump")
def dump_command():
    dump_attorneys_to_csv("attorneys_dump.csv")
    
    