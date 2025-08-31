from app import scraper

def test_delete_control_chars():
    """Test that control characters are properly removed from HTML."""
    html_with_controls = "\\r\\n\\t<div>\\r\\nContent\\n</div>\\r\\n"
    cleaned = scraper.delete_control_chars(html_with_controls)
    assert "\\r" not in cleaned
    assert "\\n" not in cleaned
    assert "\\" not in cleaned
    assert "<div>Content</div>" in cleaned

def test_parse_html_raw():
    """Test parsing of raw HTML string with known structure."""
    html = "\r\n\r\n\r\n\r\n    <div class=\"list-item firm\">\r\n      <div class=\"block\">\r\n        <span> Firm </span>\r\n        <h4>JLTF Holdings Pty Ltd trading as IP Flourish</h4>\r\n      </div>\r\n      <div class=\"contact block\">\r\n      \r\n        <div class=\"block-1\">\r\n          <span> Phone </span>\r\n          <span>\r\n            <a href=\"tel:+617 3177 3365\" class=\"btn btn-secondary btn-textOnly\">+617 3177 3365</a>\r\n          </span>\r\n        </div>\r\n      \r\n      \r\n      \r\n        <div class=\"block-2\">\r\n          <span> Email </span>\r\n          <span>\r\n            <a href=\"mailto:mail@ipflourish.com\" class=\"btn btn-secondary btn-textOnly\">mail@ipflourish.com</a>\r\n          </span>\r\n        </div>\r\n      \r\n\r\n      \r\n      \r\n        <div class=\"block-3\">\r\n          <span> Website </span>\r\n          <span>\r\n              <a class=\"btn btn-secondary btn-textOnly\" target=\"_blank\" rel=\"noopener noreferrer\" href=\"http://www.ipflourish.com\">JLTF Holdings Pty Ltd trading as IP Flourish</a>\r\n          </span>\r\n        </div>\r\n      \r\n      </div>\r\n\r\n      \r\n        <div class=\"block\">\r\n          <span> Company Directors </span>\r\n          <span>Timothy Liam Fitzgerald</span>\r\n        </div>\r\n      \r\n\r\n      \r\n      <div class=\"block\">\r\n        <span> Address </span><span>\r\n          8 82 Berwick Street Fortitude Valley QLD 4006 Australia\r\n        </span>\r\n      </div>\r\n      \r\n\r\n       \r\n        <div class=\"block\">\r\n          <span> Registered as</span>\r\n          <div class=\"tags\">       \r\n          \r\n              <span class=\"ipr-tag ipr-P\">Patents</span>\r\n          \r\n              <span class=\"ipr-tag ipr-TM\">Trade marks</span>\r\n            \r\n          </div>\r\n        </div>\r\n      \r\n    </div>\r\n  \r\n\r\n  "

    html = scraper.delete_control_chars(html)
    data = scraper.parse_html(html)

    expected = {
        'Firm': 'JLTF Holdings Pty Ltd trading as IP Flourish',
        'Phone': '+617 3177 3365',
        'Email': 'mail@ipflourish.com',
        'Website': 'http://www.ipflourish.com',
        'Company Directors': 'Timothy Liam Fitzgerald',
        'Address': '8 82 Berwick Street Fortitude Valley QLD 4006 Australia',
        'Registered as': 'Patents, Trade marks'
    }

    assert data == expected

def test_parse_html_attorney_fields(example_htmls):
    """Test parsing of attorney-specific HTML structures."""
    # Test specific attorney examples
    attorney_cases = {
        "attorney_example_result_0": {
            "Attorney": "John Smith",
            "Phone": "+61 2 1234 5678",
            "Email": "john.smith@example.com",
            "Firm": "Example Law Firm",
            "Address": "Level 10, 123 Example Street, Sydney NSW 2000 Australia",
            "Registered as": "Patents, Trade marks"
        },
        "attorney_example_result_1": {
            "Attorney": "Jane Doe",
            "Phone": "+61 3 9876 5432",
            "Email": "jane.doe@patentfirm.com.au",
            "Firm": "Patent Attorneys Australia",
            "Address": "Suite 5, 456 Patent Avenue, Melbourne VIC 3000 Australia",
            "Registered as": "Patents"
        },
        "attorney_example_result_2": {
            "Attorney": "Bob Wilson",
            "Email": "b.wilson@trademarkfirm.co.nz",
            "Firm": "Trademark Specialists NZ",
            "Address": "Level 2, 789 Queen Street, Auckland 1010 New Zealand",
            "Registered as": "Trade marks"
        }
    }

    for key, expected in attorney_cases.items():
        if key in example_htmls:
            html = scraper.delete_control_chars(example_htmls[key])
            parsed = scraper.parse_html(html)
            for field, expected_value in expected.items():
                assert parsed.get(field) == expected_value, f"{key}: {field} expected '{expected_value}', got '{parsed.get(field)}'"

def test_parse_html_firm_fields(example_htmls):
    """Test parsing of firm-specific HTML structures."""
    firm_cases = {
        "firm_example_result_0": {
            "Firm": "ABC IP Law Firm",
            "Phone": "+61 2 8765 4321",
            "Email": "contact@abciplaw.com.au",
            "Website": "https://www.abciplaw.com.au",
            "Company Directors": "Alice Cooper, Bob Johnson",
            "Address": "Level 15, 200 Collins Street, Melbourne VIC 3000 Australia",
            "Registered as": "Patents, Trade marks"
        },
        "firm_example_result_1": {
            "Firm": "XYZ Patent Services",
            "Phone": "+64 9 123 4567",
            "Email": "info@xyzpatents.co.nz",
            "Company Directors": "Michael Brown",
            "Address": "Suite 10, 50 Queen Street, Auckland 1010 New Zealand",
            "Registered as": "Patents"
        }
    }

    for key, expected in firm_cases.items():
        if key in example_htmls:
            html = scraper.delete_control_chars(example_htmls[key])
            parsed = scraper.parse_html(html)
            for field, expected_value in expected.items():
                assert parsed.get(field) == expected_value, f"{key}: {field} expected '{expected_value}', got '{parsed.get(field)}'"

def test_parse_html_mixed_data(example_htmls):
    """Test parsing mixed attorney and firm data."""
    mixed_cases = {
        "mixed_example_result_0": {  # Sarah Mitchell - Attorney
            "Attorney": "Sarah Mitchell",
            "Phone": "+61 7 3333 1111",
            "Email": "s.mitchell@mixedlaw.com",
            "Firm": "Mixed IP Solutions",
            "Address": "Level 8, 100 George Street, Brisbane QLD 4000 Australia",
            "Registered as": "Trade marks"
        },
        "mixed_example_result_1": {  # Global IP Partners - Firm
            "Firm": "Global IP Partners",
            "Phone": "+61 8 9999 8888",
            "Email": "hello@globalip.com.au",
            "Website": "http://www.globalip.com.au",
            "Company Directors": "David Williams, Emma Thompson, James Rodriguez",
            "Address": "Level 25, 88 Phillip Street, Sydney NSW 2000 Australia",
            "Registered as": "Patents, Trade marks"
        },
        "mixed_example_result_2": {  # Michael Chen - Attorney (no phone, no firm)
            "Attorney": "Michael Chen",
            "Email": "m.chen@independentip.com",
            "Address": "Unit 5, 150 Adelaide Street, Brisbane QLD 4000 Australia",
            "Registered as": "Patents, Trade marks"
        },
        "mixed_example_result_3": {  # Boutique IP Law - Firm (no website, no directors)
            "Firm": "Boutique IP Law",
            "Phone": "+64 4 5555 6666",
            "Email": "contact@boutiqueip.co.nz",
            "Address": "Level 5, 30 The Terrace, Wellington 6011 New Zealand",
            "Registered as": "Trade marks"
        }
    }

    for key, expected in mixed_cases.items():
        if key in example_htmls:
            html = scraper.delete_control_chars(example_htmls[key])
            parsed = scraper.parse_html(html)
            for field, expected_value in expected.items():
                assert parsed.get(field) == expected_value, f"{key}: {field} expected '{expected_value}', got '{parsed.get(field)}'"

def test_registered_as_tags_parsing(example_htmls):
    """Test that 'Registered as' tags are parsed correctly."""
    for key, html in example_htmls.items():
        cleaned_html = scraper.delete_control_chars(html)
        parsed = scraper.parse_html(cleaned_html)

        if "Registered as" in parsed:
            registered_as = parsed["Registered as"]

            # Should be a comma-separated string
            assert isinstance(registered_as, str)

            # Split and check individual tags
            tags = [tag.strip() for tag in registered_as.split(",")]
            valid_tags = {"Patents", "Trade marks"}

            for tag in tags:
                assert tag in valid_tags, f"Invalid tag '{tag}' found in {key}"

            # Should not be empty
            assert len(tags) > 0, f"No tags found in {key}"
            assert all(tag != "" for tag in tags), f"Empty tag found in {key}"

def test_website_field_parsing(example_htmls):
    """Test that Website field extracts href attributes correctly."""
    for key, html in example_htmls.items():
        cleaned_html = scraper.delete_control_chars(html)
        parsed = scraper.parse_html(cleaned_html)

        if "Website" in parsed:
            website = parsed["Website"]

            # Should be a URL starting with http
            assert website.startswith(("http://", "https://")), f"Website '{website}' in {key} should start with http:// or https://"

            # Should not contain HTML tags
            assert "<" not in website and ">" not in website, f"Website '{website}' in {key} contains HTML tags"

def test_parse_html_empty_input():
    """Test parsing of empty or minimal HTML."""
    test_cases = [
        "",  # Empty string
        "<div></div>",  # Empty div
        "<div class='list-item'></div>",  # Empty list item
        "   \r\n\t   ",  # Whitespace only
    ]

    for html in test_cases:
        cleaned_html = scraper.delete_control_chars(html)
        parsed = scraper.parse_html(cleaned_html)
        assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)} for input: {repr(html)}"
        # Empty or minimal HTML should return empty dict or dict with empty values
        assert len(parsed) == 0 or all(v == "" for v in parsed.values()), f"Expected empty dict or empty values for input: {repr(html)}"

def test_parse_html_malformed_input():
    """Test parsing of malformed HTML."""
    malformed_cases = [
        "<div class='block'><span>Label</span>",  # Unclosed div
        "<div class='block'><span>Label</span><span>Value</div>",  # Unclosed span
        "<div class='block'><span Label </span><span>Value</span></div>",  # Malformed span
    ]

    for html in malformed_cases:
        cleaned_html = scraper.delete_control_chars(html)
        # Should not raise an exception
        parsed = scraper.parse_html(cleaned_html)
        assert isinstance(parsed, dict), f"Expected dict, got {type(parsed)} for malformed HTML: {repr(html)}"

def test_contact_block_parsing():
    """Test specific parsing of contact blocks."""
    contact_html = """
    <div class="contact block">
        <div class="block-1">
            <span>Phone</span>
            <span><a href="tel:+61234567890">+61234567890</a></span>
        </div>
        <div class="block-2">
            <span>Email</span>
            <span><a href="mailto:test@example.com">test@example.com</a></span>
        </div>
        <div class="block-3">
            <span>Website</span>
            <span><a href="https://example.com" target="_blank">Example Site</a></span>
        </div>
    </div>
    """

    parsed = scraper.parse_html(contact_html)

    assert parsed.get("Phone") == "+61234567890"
    assert parsed.get("Email") == "test@example.com"
    assert parsed.get("Website") == "https://example.com"

def test_block_parsing():
    """Test parsing of general block elements."""
    block_html = """
    <div class="block">
        <span>Attorney</span>
        <h4>Test Attorney Name</h4>
    </div>
    <div class="block">
        <span>Address</span>
        <span>123 Test Street, Test City</span>
    </div>
    """

    parsed = scraper.parse_html(block_html)

    assert parsed.get("Attorney") == "Test Attorney Name"
    assert parsed.get("Address") == "123 Test Street, Test City"

def test_registered_as_tags_structure():
    """Test parsing of the tags structure within Registered as blocks."""
    tags_html = """
    <div class="block">
        <span>Registered as</span>
        <div class="tags">
            <span class="ipr-tag ipr-P">Patents</span>
            <span class="ipr-tag ipr-TM">Trade marks</span>
        </div>
    </div>
    """

    parsed = scraper.parse_html(tags_html)

    assert parsed.get("Registered as") == "Patents, Trade marks"

def test_registered_as_single_tag():
    """Test parsing when only one registration type is present."""
    single_tag_html = """
    <div class="block">
        <span>Registered as</span>
        <div class="tags">
            <span class="ipr-tag ipr-P">Patents</span>
        </div>
    </div>
    """

    parsed = scraper.parse_html(single_tag_html)

    assert parsed.get("Registered as") == "Patents"

def test_parsing_preserves_whitespace_in_values():
    """Test that meaningful whitespace in field values is preserved."""
    whitespace_html = """
    <div class="block">
        <span>Company Directors</span>
        <span>John Smith, Jane Doe, Bob Wilson</span>
    </div>
    <div class="block">
        <span>Address</span>
        <span>Level 10, 123 Example Street, Sydney NSW 2000 Australia</span>
    </div>
    """

    parsed = scraper.parse_html(whitespace_html)

    # Commas and spaces should be preserved in meaningful content
    assert parsed.get("Company Directors") == "John Smith, Jane Doe, Bob Wilson"
    assert parsed.get("Address") == "Level 10, 123 Example Street, Sydney NSW 2000 Australia"

def test_case_sensitivity_in_labels():
    """Test that parsing handles various case patterns in field labels."""
    case_html = """
    <div class="block">
        <span> Attorney </span>
        <h4>Test Name</h4>
    </div>
    <div class="block">
        <span>FIRM</span>
        <span>Test Firm</span>
    </div>
    <div class="block">
        <span>company directors</span>
        <span>Test Director</span>
    </div>
    """

    parsed = scraper.parse_html(case_html)

    # Labels should be parsed as-is (with proper spacing handled)
    assert parsed.get("Attorney") == "Test Name"
    assert parsed.get("FIRM") == "Test Firm"
    assert parsed.get("company directors") == "Test Director"
