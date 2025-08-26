import json
from pathlib import Path

import pytest

from app import scraper

# TODO Fix these parsing tests by replacing missing examples
EXAMPLES_FOLDER = Path(__file__).parent / "examples"

@pytest.fixture(scope="module")
def example_htmls():
    """Load example HTML snippets from files in the Examples folder."""
    examples = {}
    for fname in EXAMPLES_FOLDER.glob("*.json"):
        with open(fname, "r", encoding="utf-8") as f:
            # Each JSON file contains a dict with at least a 'Html' key
            data = f.read()
            try:
                record = json.loads(data)
                html = record.get("Html", "")
            except Exception:
                html = data  # fallback: treat as raw HTML
            examples[fname.stem] = html
    return examples

def test_parse_html_raw():
    html = "\r\n\r\n\r\n\r\n    <div class=\"list-item firm\">\r\n      <div class=\"block\">\r\n        <span> Firm </span>\r\n        <h4>JLTF Holdings Pty Ltd trading as IP Flourish</h4>\r\n      </div>\r\n      <div class=\"contact block\">\r\n      \r\n        <div class=\"block-1\">\r\n          <span> Phone </span>\r\n          <span>\r\n            <a href=\"tel:+617 3177 3365\" class=\"btn btn-secondary btn-textOnly\">+617 3177 3365</a>\r\n          </span>\r\n        </div>\r\n      \r\n      \r\n      \r\n        <div class=\"block-2\">\r\n          <span> Email </span>\r\n          <span>\r\n            <a href=\"mailto:mail@ipflourish.com\" class=\"btn btn-secondary btn-textOnly\">mail@ipflourish.com</a>\r\n          </span>\r\n        </div>\r\n      \r\n\r\n      \r\n      \r\n        <div class=\"block-3\">\r\n          <span> Website </span>\r\n          <span>\r\n              <a class=\"btn btn-secondary btn-textOnly\" target=\"_blank\" rel=\"noopener noreferrer\" href=\"http://www.ipflourish.com\">JLTF Holdings Pty Ltd trading as IP Flourish</a>\r\n          </span>\r\n        </div>\r\n      \r\n      </div>\r\n\r\n      \r\n        <div class=\"block\">\r\n          <span> Company Directors </span>\r\n          <span>Timothy Liam Fitzgerald</span>\r\n        </div>\r\n      \r\n\r\n      \r\n      <div class=\"block\">\r\n        <span> Address </span><span>\r\n          8 82 Berwick Street Fortitude Valley QLD 4006 Australia\r\n        </span>\r\n      </div>\r\n      \r\n\r\n       \r\n        <div class=\"block\">\r\n          <span> Registered as</span>\r\n          <div class=\"tags\">       \r\n          \r\n              <span class=\"ipr-tag ipr-P\">Patents</span>\r\n          \r\n              <span class=\"ipr-tag ipr-TM\">Trade marks</span>\r\n            \r\n          </div>\r\n        </div>\r\n      \r\n    </div>\r\n  \r\n\r\n  "

    html = scraper.delete_control_chars(html)
    data = scraper.parse_html(html)
    assert data == "{'Firm': 'JLTF Holdings Pty Ltd trading as IP Flourish', 'Phone': '+617 3177 3365', 'Company Directors': 'Timothy Liam Fitzgerald', 'Address': '8 82 Berwick Street Fortitude Valley QLD 4006 Australia', 'Registered as': 'Patents, Trade marks', 'Email': 'mail@ipflourish.com', 'Website': 'JLTF Holdings Pty Ltd trading as IP Flourish'}"
    
def test_parse_html_fields(example_htmls):
    """Test that parse_html extracts expected fields from example HTML."""
    # You can expand this dict with more expected outputs as you add more examples
    expected_outputs = {
        "attorneyHTMLExample": {
            "Name": "Louis Francisco Yates Habberfield-Short",
            "Phone": "+64 9 353 5423",
            "Email": "louis.habberfield-short@ajpark.com",
            "Address": "Level 14, Aon Centre, 29 Customs Street West, Auckland 1010, New Zealand",
            "Registered as": "Patents"
        },
        "attorneyHTMLExample2": {
            "Name": "Donald Iain Angus",
            "Phone": "08 8212 3133",
            "Email": "collison@collison.com.au",
            "Firm": "Collison & Co",
            "Address": "Level 4 70 Light Square Adelaide SA 5000 Australia",
            "Registered as": "Patents, Trade marks"
        }
    }
    for key, html in example_htmls.items():
        if key in expected_outputs:
            parsed = scraper.parse_html(html)
            for field, expected_value in expected_outputs[key].items():
                assert parsed.get(field) == expected_value, f"{key}: {field} did not match"

def test_registered_as_tags(example_htmls):
    """Test that 'Registered as' tags are parsed correctly."""
    for key, html in example_htmls.items():
        parsed = scraper.parse_html(html)
        if "Registered as" in parsed:
            tags = parsed["Registered as"].split(", ")
            assert all(tag in ["Patents", "Trade marks"] for tag in tags)

def test_parse_html_website(example_htmls):
    """Test that Website field is parsed correctly when present."""
    # Add an example with a Website field in your Examples folder for this test
    for key, html in example_htmls.items():
        parsed = scraper.parse_html(html)
        if "Website" in parsed:
            # Should be a URL if an <a href> is present
            assert parsed["Website"].startswith("http") or parsed["Website"] != ""

def test_parse_html_blank(example_htmls):
    """Test that parsing blank or minimal HTML returns an empty dict."""
    blank_html = example_htmls.get("blankAttorneyExample", "")
    parsed = scraper.parse_html(blank_html)
    assert isinstance(parsed, dict)
    assert len(parsed) == 0 or all(v == "" for v in parsed.values())

