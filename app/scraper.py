import pandas as pd
import sqlalchemy as sa
import numpy as np
import datetime
import json
import logging
import os
from pathlib import Path
import requests
from bs4 import BeautifulSoup

from app import db, temporal_db
from app.models import Attorney, Firm

logger = logging.getLogger(__name__)
logging.basicConfig(filename='ttipabot.log', encoding='utf-8', format='%(asctime)s %(message)s', level=logging.DEBUG)

def scrape_register() -> None:
    scrapes_dir = Path("scrapes")
    scrapes_dir.mkdir(exist_ok=True)
    today = datetime.date.today().isoformat()
    file_path = scrapes_dir / f"{today}.json"

    if not json_dump_register(file_path):
        logger.warning("Already scraped the register today. Reattempting a DB update.")

    data = get_register_data(file_path)
    attorneys, firms = separate_data(data)
    attorneys, firms = convert_to_models(attorneys, firms)
    temporal_db.temporal_write(Attorney, attorneys, datetime.date.today())
    merge_write(firms)

    logger.info("Updated DB with changes from scraped data.")
    cleanup_older_jsons(file_path)


def separate_data(data: list[dict]) -> tuple:
    """Separate data into attorneys and firms."""
    attorneys = []
    firms = []
    for record in data:
        if "Attorney" in record:
            attorneys.append(record)
        elif "Firm" in record:
            firms.append(record)
    return attorneys, firms


def convert_to_models(attorneys: list[dict], firms: list[dict]) -> tuple:
    """Converts the data to models using pandas for efficient processing."""

    def process_dataframe(
        data: list[dict], column_map: dict, add_temporal: bool = False
    ) -> pd.DataFrame:
        if not data:
            return pd.DataFrame()

        df = pd.DataFrame(data)

        # Rename columns
        df = df.rename(columns=column_map)

        # Replace empty strings with NaN in 'name' column so they can be dropped
        df["name"] = df["name"].replace("", np.nan)

        # Delete rows where name is not present
        df.dropna(subset=["name"], inplace=True)

        # Handle boolean fields from 'Registered as'
        registered_col = df.get("Registered as", pd.Series("", index=df.index))
        df["patents"] = (
            registered_col.astype(str).str.lower().str.contains("patent", na=False)
        )
        df["trademarks"] = (
            registered_col.astype(str)
            .str.lower()
            .str.contains("trademark|trade mark", na=False)
        )

        # Add temporal fields for attorneys
        if add_temporal:
            df["valid_from"] = datetime.date.today()
            df["valid_to"] = None

        # Clean up
        df.replace({np.nan: None}, inplace=True)
        columns_to_drop = ["Registered as", "Language", "Path", "Url", "Name"]
        for column in columns_to_drop:
            if column in df.columns:
                df.drop(columns=[column], inplace=True)
        return df

    # Column mappings
    attorney_column_map = {
        "Id": "external_id",
        "Attorney": "name",
        "Phone": "phone",
        "Email": "email",
        "Firm": "firm",
        "Address": "address",
    }

    firm_column_map = {
        "Id": "external_id",
        "Firm": "name",
        "Phone": "phone",
        "Email": "email",
        "Company Directors": "directors",
        "Website": "website",
        "Address": "address",
    }

    # Process data
    df_attorneys = process_dataframe(attorneys, attorney_column_map, add_temporal=True)
    df_firms = process_dataframe(firms, firm_column_map, add_temporal=False)

    # Convert to model objects
    attorney_models = (
        [Attorney(**row) for row in df_attorneys.to_dict(orient="records")]
        if not df_attorneys.empty
        else []
    )
    firm_models = (
        [Firm(**row) for row in df_firms.to_dict(orient="records")]
        if not df_firms.empty
        else []
    )

    return attorney_models, firm_models


def ttipab_request(count: int):
    """Makes a GET request to the TTIPA register asking for <count> results."""
    # Public API endpoint as determined by Inspect Element > Network > Requests on Google Chrome
    endpoint = "https://www.ttipattorney.gov.au//sxa/search/results/"
    scope = "{21522AF6-8499-4C63-8CFA-02E2B97737BE}"
    itemid = "{8B94FE47-304A-4629-AD46-DD208EEF71AA}"
    sig = "als"
    offset = 0
    page_size = count
    variant = "%7B2FCA44D4-EE00-43EC-BBBF-858C31387413%7D"
    url = f"{endpoint}?s={scope}&itemid={itemid}&sig={sig}&e={offset}&p={page_size}&v={variant}"
    return requests.get(url, stream=True)


def delete_control_chars(html: str) -> str:
    # Get rid of control characters
    html = html.replace("\\r", "")
    html = html.replace("\\n", "")
    html = html.replace("\\", "")
    return html


def json_dump_register(file_path: Path) -> bool:
    """Scrapes the register and dumps the data to JSON, returns True on success"""

    # Check if today's file exists
    if file_path.exists():
        return False

    try:
        # Initial ping to get count
        initial_response = ttipab_request(1)
        results_count = initial_response.json().get("Count")
        if results_count is None or results_count == 0:
            raise ValueError("API returned an invalid count")
        raw_JSON = ttipab_request(results_count).text
        logger.debug(f"Successfully scraped {results_count} results from the register.")
        # Save to file for future use
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(raw_JSON)
        return True
    except Exception as ex:
        logger.error(
            "Failed to scrape register, could be a server-side problem.", exc_info=ex
        )
        raise ex


def get_register_data(file_path: Path) -> list[dict]:
    """Extract register data from the JSON dump"""
    raw_JSON = file_path.read_text(encoding="utf-8")
    data = json.loads(raw_JSON)
    return extract_html_data(data["Results"])


def extract_html_data(data: list[dict]) -> list[dict]:
    """Extracts additional data fields from the html field of each record"""
    for record in data:
        try:
            html = record["Html"]
            html = delete_control_chars(html)
            # Parse the html and extract the fields
            record.update(parse_html(html))
            del record["Html"]
        except Exception as ex:
            logger.error("Failed to parse HTML for records", exc_info=ex)
            continue

    return data


def merge_write(firms: list[Firm]) -> None:
    """Merges non-temporal scraped data into the database."""

    # Need to adjust how firms data is handled if adding non-patent attorney firms
    for firm in firms:
        existing_firm = db.session.execute(
            sa.select(Firm).where(Firm.external_id == firm.external_id)
        ).scalar_one_or_none()

        # Comparison relies on appropriate __eq__ method being defined in model
        if existing_firm and existing_firm != firm:
            # Update existing firm
            firm.id = existing_firm.id
            db.session.merge(firm)
        elif not existing_firm:
            # Insert new firm
            db.session.add(firm)
    db.session.commit()


def cleanup_older_jsons(keep_file: Path):
    """Delete *.json files in the scrapes directory except the one specified."""
    scrapes_dir = Path("scrapes")
    for fname in scrapes_dir.glob("*.json"):
        if fname != keep_file:
            try:
                os.remove(fname)
            except Exception as ex:
                logger.warning(f"Could not delete {fname}: {ex}")


def parse_html(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    data = {}

    # Handle all <div class="block"> elements
    for block in soup.find_all("div", class_="block"):
        label_tag = block.find("span")
        if not label_tag:
            continue
        label = label_tag.get_text(strip=True)

        # Special case: Registered as
        if label == "Registered as":
            tags_div = block.find("div", class_="tags")
            if tags_div:
                tags = [span.get_text(strip=True) for span in tags_div.find_all("span")]
                data["Registered as"] = ", ".join(tags)
            continue

        # For other fields, get the next tag/text after the label
        value_tag = label_tag.find_next_sibling()
        if value_tag:
            value = value_tag.get_text(strip=True)
            data[label] = value

    # Handle contact blocks (phone/email)
    contact_block = soup.find("div", class_="contact block")
    if contact_block:
        for sub_block in contact_block.find_all("div"):
            label_tag = sub_block.find("span")
            if not label_tag:
                continue
            label = label_tag.get_text(strip=True)

            # Special case: Website
            if label == "Website":
                value_tag = label_tag.find_next_sibling("span")
                if value_tag:
                    a_tag = value_tag.find("a", href=True)
                    # print(a_tag)
                    if a_tag and a_tag["href"]:
                        data["Website"] = a_tag["href"]
                    else:
                        data["Website"] = value_tag.get_text(strip=True)
                continue

            # Handle other contact fields
            value_tag = label_tag.find_next_sibling("span")
            if value_tag:
                value = value_tag.get_text(strip=True)
                data[label] = value

    return data
