import datetime
import json
import os
from pathlib import Path

import requests
import sqlalchemy as sa
from bs4 import BeautifulSoup
from flask import current_app
from requests.adapters import HTTPAdapter, Retry

from app import db, temporal_db
from app.data_migrator import (
    link_attorneys_to_consolidated_firms,
    link_incorporated_firms_to_consolidated,
    update_attorney_firm_links,
)
from app.models import Attorney, IncorporatedFirm


def scrape_register() -> None:
    scrapes_dir = Path("scrapes")
    scrapes_dir.mkdir(exist_ok=True)
    today = datetime.date.today().isoformat()
    file_path = scrapes_dir / f"{today}.json"

    if not json_dump_register(file_path):
        current_app.logger.warning(
            "Already scraped the register today. Reattempting a DB update."
        )

    try:
        data = get_register_data(file_path)
        attorneys, firms = separate_data(data)
        attorneys, firms = convert_to_models(attorneys, firms)
        new_attorney_ids, changed_attorney_ids = temporal_db.temporal_write_with_ids(
            Attorney, attorneys, datetime.date.today()
        )
        new_firm_ids, changed_firm_ids = merge_write_with_ids(firms)

        if new_attorney_ids or changed_attorney_ids:
            all_attorney_ids = new_attorney_ids + changed_attorney_ids
            link_attorneys_to_consolidated_firms(all_attorney_ids)
            update_attorney_firm_links()

        if new_firm_ids or changed_firm_ids:
            all_firm_ids = new_firm_ids + changed_firm_ids
            link_incorporated_firms_to_consolidated(all_firm_ids)

        current_app.logger.info("Updated DB with changes from scraped data.")
    except Exception:
        # The scrape itself succeeded (file is written), but the DB update
        # failed. Log with a traceback so it shows up in the rotating file log
        # instead of only going to stderr / cron mail, which previously made
        # nightly write failures look like successful no-op scrapes.
        current_app.logger.exception(
            "Failed to update DB from scraped data. The scrape JSON at %s "
            "was written but no DB changes were committed.",
            file_path,
        )
        raise
    cleanup_older_jsons(file_path)


def separate_data(data: list[dict]) -> tuple:
    """Separate data into attorneys and firms.

    Records that contain neither an "Attorney" nor a "Firm" label (i.e. the
    name block could not be parsed) are logged with their external_id so a
    silent mass-drop is visible in the logs, rather than those records being
    lapsed by ``temporal_write_with_ids`` without any trace of why.
    """
    attorneys = []
    firms = []
    dropped = []
    for record in data:
        if "Attorney" in record:
            attorneys.append(record)
        elif "Firm" in record:
            firms.append(record)
        else:
            dropped.append(record.get("Id"))
    if dropped:
        current_app.logger.warning(
            "separate_data: dropped %d record(s) with neither Attorney nor Firm "
            "label (will be treated as lapsed by temporal_write): %s",
            len(dropped),
            dropped,
        )
    return attorneys, firms


# Register labels we know how to persist on each model. Anything outside
# this set (plus the metadata fields below) is ignored with a warning so a
# new register field can never break the nightly write.
_ATTORNEY_KNOWN_FIELDS = {
    "Id", "Attorney", "Phone", "Email", "Firm", "Address",
    "Additional Information",
}
_FIRM_KNOWN_FIELDS = {
    "Id", "Firm", "Phone", "Email", "Company Directors", "Website", "Address",
}
# Register-only / metadata keys that are never persisted on a model.
_META_FIELDS = {"Registered as", "Language", "Path", "Url", "Name"}


def _registered_booleans(registered_as: str | None) -> tuple[bool, bool]:
    """Derive (patents, trademarks) flags from the register's 'Registered as'
    free-text field, e.g. 'Patents, Trade marks'."""
    text = (registered_as or "").lower()
    return "patent" in text, "trademark" in text or "trade mark" in text


def _build_attorney(record: dict) -> Attorney:
    patents, trademarks = _registered_booleans(record.get("Registered as"))
    return Attorney(
        external_id=record.get("Id") or None,
        name=record.get("Attorney") or None,
        phone=record.get("Phone") or None,
        email=record.get("Email") or None,
        firm=record.get("Firm") or None,
        address=record.get("Address") or None,
        additional_information=record.get("Additional Information") or None,
        patents=patents,
        trademarks=trademarks,
        valid_from=datetime.date.today(),
        valid_to=None,
    )


def _build_firm(record: dict) -> IncorporatedFirm:
    patents, trademarks = _registered_booleans(record.get("Registered as"))
    return IncorporatedFirm(
        external_id=record.get("Id") or None,
        name=record.get("Firm") or None,
        phone=record.get("Phone") or None,
        email=record.get("Email") or None,
        directors=record.get("Company Directors") or None,
        website=record.get("Website") or None,
        address=record.get("Address") or None,
        patents=patents,
        trademarks=trademarks,
    )


def _records_to_models(
    records: list[dict],
    known_fields: set,
    name_source: str,
    build_fn,
    label: str,
) -> list:
    """Map a list of parsed register records to ORM model instances.

    Records with an empty/missing name are dropped (and logged by
    ``external_id``); any register field not in ``known_fields`` (and not a
    metadata field) is ignored with a single warning so the scrape is robust
    to the register introducing new labels.
    """
    if not records:
        return []

    known = known_fields | _META_FIELDS
    unknown = sorted({key for rec in records for key in rec} - known)
    if unknown:
        current_app.logger.warning(
            "Ignoring unknown register field(s) for %s: %s. "
            "These will not be persisted.",
            label,
            ", ".join(unknown),
        )

    models = []
    for record in records:
        name = record.get(name_source)
        if not name:
            current_app.logger.warning(
                "Dropping %s record with empty name: %s",
                label,
                record.get("Id"),
            )
            continue
        models.append(build_fn(record))
    return models


def convert_to_models(attorneys: list[dict], firms: list[dict]) -> tuple:
    """Convert parsed register records into ``Attorney`` / ``IncorporatedFirm``
    model instances.

    Robust to unknown register fields: only the attributes explicitly mapped
    in ``_build_attorney`` / ``_build_firm`` (plus the derived boolean and
    temporal columns) are passed to the constructor. Any other labels the
    register starts emitting (e.g. a secretary-entered freeform field) are
    dropped with a warning rather than crashing the scrape.
    """
    attorney_models = _records_to_models(
        attorneys, _ATTORNEY_KNOWN_FIELDS, "Attorney", _build_attorney, "attorney",
    )
    firm_models = _records_to_models(
        firms, _FIRM_KNOWN_FIELDS, "Firm", _build_firm, "firm",
    )
    return attorney_models, firm_models


def ttipab_request(count: int, timeout: int = 30, max_retries: int = 3):
    """Makes a GET request to the TTIPA register asking for <count> results."""
    endpoint = "https://www.ttipattorney.gov.au//sxa/search/results/"
    scope = "{21522AF6-8499-4C63-8CFA-02E2B97737BE}"
    itemid = "{8B94FE47-304A-4629-AD46-DD208EEF71AA}"
    sig = "als"
    offset = 0
    page_size = count
    variant = "%7B2FCA44D4-EE00-43EC-BBBF-858C31387413%7D"
    url = f"{endpoint}?s={scope}&itemid={itemid}&sig={sig}&e={offset}&p={page_size}&v={variant}"

    session = requests.Session()
    retry = Retry(
        total=max_retries,
        backoff_factor=0.5,  # Will sleep for [0.5, 1, 2] seconds between retries
        status_forcelist=[500, 502, 503, 504],  # Retry on these HTTP status codes
    )
    session.mount("https://", HTTPAdapter(max_retries=retry))

    return session.get(url, timeout=timeout)


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
        initial_response.raise_for_status()  # Raise HTTPError for bad status codes
        results_count = initial_response.json().get("Count")
        if results_count is None or results_count == 0:
            raise ValueError("API returned an invalid count")

        full_response = ttipab_request(results_count)
        full_response.raise_for_status()  # Raise HTTPError for bad status codes
        raw_JSON = full_response.text
        current_app.logger.info(
            f"Successfully scraped {results_count} results from the register."
        )
        # Save to file for future use
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(raw_JSON)
        return True

    except requests.HTTPError as http_err:
        current_app.logger.error(
            f"HTTP error occurred while scraping register: {http_err}",
            exc_info=http_err,
        )
        raise http_err

    except requests.RequestException as req_err:
        current_app.logger.error(
            "Network error while scraping register",
            extra={"url": req_err.request.url if req_err.request else None},
            exc_info=req_err,
        )
        raise req_err

    except Exception as ex:
        current_app.logger.error(
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
            current_app.logger.error("Failed to parse HTML for records", exc_info=ex)
            continue

    return data


def merge_write(firms: list[IncorporatedFirm]) -> None:
    """Merges non-temporal scraped data into the database."""

    # Need to adjust how firms data is handled if adding non-patent attorney firms
    for firm in firms:
        existing_firm = db.session.execute(
            sa.select(IncorporatedFirm).where(
                IncorporatedFirm.external_id == firm.external_id
            )
        ).scalar_one_or_none()

        # Only merge when business fields differ.
        if existing_firm and not temporal_db.records_unchanged(existing_firm, firm):
            # Update existing firm
            firm.id = existing_firm.id
            db.session.merge(firm)
        elif not existing_firm:
            # Insert new firm
            db.session.add(firm)
    db.session.commit()


def merge_write_with_ids(firms: list[IncorporatedFirm]) -> tuple:
    """
    Merges non-temporal scraped data into the database.
    Returns tuple of (new_ids, changed_ids).
    """
    new_ids = []
    changed_ids = []

    for firm in firms:
        existing_firm = db.session.execute(
            sa.select(IncorporatedFirm).where(
                IncorporatedFirm.external_id == firm.external_id
            )
        ).scalar_one_or_none()

        if existing_firm and not temporal_db.records_unchanged(existing_firm, firm):
            firm.id = existing_firm.id
            db.session.merge(firm)
            db.session.flush()
            changed_ids.append(existing_firm.id)
        elif not existing_firm:
            db.session.add(firm)
            db.session.flush()
            new_ids.append(firm.id)
    
    db.session.commit()
    return (new_ids, changed_ids)


def cleanup_older_jsons(keep_file: Path):
    """Delete *.json files in the scrapes directory except the one specified."""
    scrapes_dir = Path("scrapes")
    for fname in scrapes_dir.glob("*.json"):
        if fname != keep_file:
            try:
                os.remove(fname)
            except Exception as ex:
                current_app.logger.warning(f"Could not delete {fname}: {ex}")


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
