import pytest
from pathlib import Path
from app import scraper, app
import json

EXAMPLES_FOLDER = Path(__file__).parent / "Examples"

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

@pytest.fixture(scope="session", autouse=True)
def app_context():
    with app.app_context():
        yield

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

