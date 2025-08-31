import pytest
import json
from pathlib import Path
from app import create_app, db
from config import Config

EXAMPLES_FOLDER = Path(__file__).parent / "examples"

class TestConfig(Config):
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite://"


@pytest.fixture
def app():
    app = create_app(TestConfig)
    with app.app_context():
        db.create_all()
        yield app
        db.drop_all()

@pytest.fixture(scope="module")
def example_data():
    """Load example data from JSON files in the examples folder."""
    examples = {}
    for fname in EXAMPLES_FOLDER.glob("*.json"):
        with open(fname, "r", encoding="utf-8") as f:
            data = json.loads(f.read())
            examples[fname.stem] = data
    return examples

@pytest.fixture(scope="module")
def example_htmls(example_data):
    """Extract HTML snippets from example data for direct parsing tests."""
    htmls = {}
    for file_key, data in example_data.items():
        results = data.get("Results", [])
        for i, record in enumerate(results):
            html = record.get("Html", "")
            key = f"{file_key}_result_{i}"
            htmls[key] = html
    return htmls
