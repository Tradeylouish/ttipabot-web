import datetime
import logging
from app.models import Attorney, Firm
from app import db

import requests
from bs4 import BeautifulSoup
import json

logger = logging.getLogger(__name__)

def scrape_register() -> None:
    data = get_register_data()
    data = extract_html_data(data)
    attorneys, firms = parse_data(data)
    write_to_db(attorneys, firms)
    logger.info(f"Scraped and saved {len(attorneys)} attorneys and {len(firms)} firms to the database.")

def ttipab_request(count: int):
    """Makes a GET request to the TTIPA register asking for <count> results."""
    # Public API endpoint as determined by Inspect Element > Network > Requests on Google Chrome
    endpoint = "https://www.ttipattorney.gov.au//sxa/search/results/"
    scope= "{21522AF6-8499-4C63-8CFA-02E2B97737BE}"
    itemid = "{8B94FE47-304A-4629-AD46-DD208EEF71AA}"
    sig = "als"
    offset = 0
    page_size = count
    variant = "%7B2FCA44D4-EE00-43EC-BBBF-858C31387413%7D"
    url =  f"{endpoint}?s={scope}&itemid={itemid}&sig={sig}&e={offset}&p={page_size}&v={variant}"
    return requests.get(url, stream=True)
    
def delete_control_chars(html: str) -> str:
    # Get rid of control characters
    html = html.replace("\\r", "")
    html = html.replace("\\n", "")
    html = html.replace("\\", "")
    return html

def get_register_data() -> dict:
    """Scrapes the register and returns a dict loaded from the JSON response."""
    
    try:
        #Do an intial ping of the register to determine the total number of results to be requested
        initialResponse = ttipab_request(1)
        #Convert JSON response to dict and extract count
        resultsCount = initialResponse.json().get("Count")
        #Request the full contents of the register
        rawJSON = ttipab_request(resultsCount).text
        logger.debug(f"Successfully scraped {resultsCount} results from the register.")
    except Exception as ex:
        logger.error("Failed to scrape register, could be a server-side problem.", exc_info= ex)
        raise ex

    return json.loads(rawJSON)

def extract_html_data(data: dict) -> dict:
    """Extracts additional data fields from the html and adds it into the record data."""
    for record in data:
        html = record['Html']
        html = delete_control_chars(html)
        # Parse the html and extract the fields
        record.update(parse_html(html))
        del data['Html']
        
    return data

def parse_data(data: dict) -> tuple[list[Attorney], list[Firm]]:
    attorneys = []
    firms = []
    for record in data:
        external_id = record["Id"]
        valid_from=datetime.date.today()
        
        if "Attorney" in record:
            re_keyed_data = data
            attorney = Attorney(**re_keyed_data)
            attorneys.append(attorney)
        elif "Firm" in record:
            re_keyed_data = data
            firm = Firm(**re_keyed_data)
            firms.append(firm)
            
    return attorneys, firms

def write_to_db(attorneys: list[Attorney], firms: list[Firm]) -> None:
    #TODO Need to implement the temporal aspects of checking validity etc. - maybe its own module
    """Writes the scraped data to the database."""
    db.session.add_all(attorneys)
    db.session.add_all(firms)
    db.session.commit()

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

        # Special case: Website
        if label == "Website":
            value_tag = label_tag.find_next_sibling("span")
            if value_tag:
                a_tag = value_tag.find("a", href=True)
                if a_tag and a_tag["href"]:
                    data["Website"] = a_tag["href"]
                else:
                    data["Website"] = value_tag.get_text(strip=True)
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
            value_tag = label_tag.find_next_sibling("span")
            if value_tag:
                value = value_tag.get_text(strip=True)
                data[label] = value

    return data

def write_raw_json(rawJSON: str) -> None:
    """Testing function to dump the JSON to a txt file instead of parsing and writing to csv."""
    with open("registerDump.txt", 'w', encoding="utf-8") as f:
        f.write(rawJSON)
    
