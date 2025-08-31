import datetime
import json
from pathlib import Path

import pytest
import sqlalchemy as sa

from app import create_app, db, temporal_db
from app.models import Attorney, Firm
from app.scraper import separate_data, convert_to_models, extract_html_data, merge_write


@pytest.fixture
def client(app):
    """Create test client."""
    return app.test_client()


@pytest.fixture
def sample_attorney_data():
    """Sample attorney data for testing."""
    return [
        {
            'Id': 'test-attorney-1',
            'Attorney': 'John Smith',
            'Phone': '+61 2 1234 5678',
            'Email': 'john.smith@example.com',
            'Firm': 'Example Law Firm',
            'Address': 'Level 10, 123 Example Street, Sydney NSW 2000 Australia',
            'Registered as': 'Patents, Trade marks'
        },
        {
            'Id': 'test-attorney-2',
            'Attorney': 'Jane Doe',
            'Phone': '+61 3 9876 5432',
            'Email': 'jane.doe@patentfirm.com.au',
            'Firm': 'Patent Attorneys Australia',
            'Address': 'Suite 5, 456 Patent Avenue, Melbourne VIC 3000 Australia',
            'Registered as': 'Patents'
        }
    ]


@pytest.fixture
def sample_firm_data():
    """Sample firm data for testing."""
    return [
        {
            'Id': 'test-firm-1',
            'Firm': 'ABC IP Law Firm',
            'Phone': '+61 2 8765 4321',
            'Email': 'contact@abciplaw.com.au',
            'Website': 'https://www.abciplaw.com.au',
            'Company Directors': 'Alice Cooper, Bob Johnson',
            'Address': 'Level 15, 200 Collins Street, Melbourne VIC 3000 Australia',
            'Registered as': 'Patents, Trade marks'
        },
        {
            'Id': 'test-firm-2',
            'Firm': 'XYZ Patent Services',
            'Phone': '+64 9 123 4567',
            'Email': 'info@xyzpatents.co.nz',
            'Company Directors': 'Michael Brown',
            'Address': 'Suite 10, 50 Queen Street, Auckland 1010 New Zealand',
            'Registered as': 'Patents'
        }
    ]


@pytest.fixture
def sample_json_data():
    """Load sample JSON data from test examples."""
    examples_folder = Path(__file__).parent / "examples"
    with open(examples_folder / "mixed_example.json", "r") as f:
        return json.loads(f.read())


class TestModels:
    """Test database models directly."""

    def test_attorney_creation(self, app):
        """Test creating an attorney record."""
        attorney = Attorney(
            external_id='test-1',
            name='John Smith',
            phone='+61 2 1234 5678',
            email='john.smith@example.com',
            firm='Example Firm',
            address='123 Test Street',
            patents=True,
            trademarks=False,
            valid_from=datetime.date.today()
        )

        db.session.add(attorney)
        db.session.commit()

        # Verify the record was created
        retrieved = db.session.get(Attorney, attorney.id)
        assert retrieved is not None
        assert retrieved.name == 'John Smith'
        assert retrieved.patents is True
        assert retrieved.trademarks is False

    def test_firm_creation(self, app):
        """Test creating a firm record."""
        firm = Firm(
            external_id='test-firm-1',
            name='Test Firm',
            phone='+61 2 8765 4321',
            email='contact@testfirm.com',
            website='https://testfirm.com',
            directors='John Doe, Jane Smith',
            address='456 Firm Street',
            patents=True,
            trademarks=True
        )

        db.session.add(firm)
        db.session.commit()

        # Verify the record was created
        retrieved = db.session.get(Firm, firm.id)
        assert retrieved is not None
        assert retrieved.name == 'Test Firm'
        assert retrieved.patents is True
        assert retrieved.trademarks is True

    def test_attorney_firm_relationship(self, app):
        """Test the relationship between attorney and firm."""
        # Create a firm
        firm = Firm(
            external_id='test-firm-rel',
            name='Relationship Test Firm',
            patents=True,
            trademarks=False
        )
        db.session.add(firm)
        db.session.commit()

        # Create an attorney linked to the firm
        attorney = Attorney(
            external_id='test-attorney-rel',
            name='Related Attorney',
            firm='Relationship Test Firm',
            firm_id=firm.id,
            patents=True,
            trademarks=False,
            valid_from=datetime.date.today()
        )
        db.session.add(attorney)
        db.session.commit()

        # Test the relationship
        assert attorney.firm_record == firm
        assert attorney in firm.attorneys
        assert firm.attorney_count() == 1

    def test_attorney_equality(self, app):
        """Test Attorney model equality comparison."""
        attorney1 = Attorney(
            external_id='test-eq-1',
            name='John Smith',
            phone='+61 2 1234 5678',
            email='john.smith@example.com',
            firm='Example Firm',
            address='123 Test Street',
            patents=True,
            trademarks=False,
            valid_from=datetime.date.today()
        )

        attorney2 = Attorney(
            external_id='test-eq-1',
            name='John Smith',
            phone='+61 2 1234 5678',
            email='john.smith@example.com',
            firm='Example Firm',
            address='123 Test Street',
            patents=True,
            trademarks=False,
            valid_from=datetime.date.today()
        )

        attorney3 = Attorney(
            external_id='test-eq-1',
            name='John Smith',
            phone='+61 2 1234 5678',
            email='different@example.com',  # Different email
            firm='Example Firm',
            address='123 Test Street',
            patents=True,
            trademarks=False,
            valid_from=datetime.date.today()
        )

        assert attorney1 == attorney2
        assert attorney1 != attorney3

    def test_firm_equality(self, app):
        """Test Firm model equality comparison."""
        firm1 = Firm(
            external_id='test-firm-eq-1',
            name='Test Firm',
            phone='+61 2 8765 4321',
            email='contact@testfirm.com',
            website='https://testfirm.com',
            directors='John Doe',
            address='456 Firm Street',
            patents=True,
            trademarks=True
        )

        firm2 = Firm(
            external_id='test-firm-eq-1',
            name='Test Firm',
            phone='+61 2 8765 4321',
            email='contact@testfirm.com',
            website='https://testfirm.com',
            directors='John Doe',
            address='456 Firm Street',
            patents=True,
            trademarks=True
        )

        firm3 = Firm(
            external_id='test-firm-eq-1',
            name='Different Firm',  # Different name
            phone='+61 2 8765 4321',
            email='contact@testfirm.com',
            website='https://testfirm.com',
            directors='John Doe',
            address='456 Firm Street',
            patents=True,
            trademarks=True
        )

        assert firm1 == firm2
        assert firm1 != firm3

    def test_attorney_to_dict(self, app):
        """Test Attorney.to_dict() method."""
        attorney = Attorney(
            external_id='test-dict-1',
            name='Dictionary Test',
            phone='+61 2 1234 5678',
            email='dict@test.com',
            firm='Test Firm',
            address='Test Address',
            patents=True,
            trademarks=False,
            valid_from=datetime.date.today()
        )
        db.session.add(attorney)
        db.session.commit()

        result = attorney.to_dict()

        expected_keys = {'id', 'name', 'name_length', 'phone', 'email', 'firm', 'previous_firm', 'address', 'patents', 'trademarks'}
        assert set(result.keys()) == expected_keys
        assert result['id'] == 'test-dict-1'
        assert result['name'] == 'Dictionary Test'
        assert result['name_length'] == len('Dictionary Test')
        assert result['patents'] is True
        assert result['trademarks'] is False

    def test_firm_to_dict(self, app):
        """Test Firm.to_dict() method."""
        firm = Firm(
            external_id='test-firm-dict-1',
            name='Firm Dictionary Test',
            phone='+61 2 8765 4321',
            email='firm@test.com',
            website='https://test.com',
            directors='Test Director',
            address='Firm Address',
            patents=True,
            trademarks=True
        )

        result = firm.to_dict()

        expected_keys = {'id', 'name', 'phone', 'email', 'website', 'address', 'patents', 'trademarks'}
        assert set(result.keys()) == expected_keys
        assert result['id'] == 'test-firm-dict-1'
        assert result['name'] == 'Firm Dictionary Test'
        assert result['patents'] is True
        assert result['trademarks'] is True


class TestTemporalDatabase:
    """Test temporal database functionality."""

    def test_temporal_query_current_date(self, app):
        """Test temporal query for current date."""
        today = datetime.date.today()

        # Create an attorney valid from today
        attorney = Attorney(
            external_id='temp-test-1',
            name='Current Attorney',
            patents=True,
            trademarks=False,
            valid_from=today,
            valid_to=None
        )
        db.session.add(attorney)
        db.session.commit()

        # Query for current date
        query = temporal_db.temporal_query(Attorney, today)
        results = db.session.execute(query).scalars().all()

        assert len(results) == 1
        assert results[0].name == 'Current Attorney'

    def test_temporal_query_past_date(self, app):
        """Test temporal query for past date."""
        today = datetime.date.today()
        past_date = today - datetime.timedelta(days=30)

        # Create an attorney valid in the past
        attorney = Attorney(
            external_id='temp-test-2',
            name='Past Attorney',
            patents=True,
            trademarks=False,
            valid_from=past_date,
            valid_to=today
        )
        db.session.add(attorney)
        db.session.commit()

        # Query for past date - should find the attorney
        query = temporal_db.temporal_query(Attorney, past_date)
        results = db.session.execute(query).scalars().all()
        assert len(results) == 1

        # Query for today - should not find the attorney (expired)
        query = temporal_db.temporal_query(Attorney, today)
        results = db.session.execute(query).scalars().all()
        assert len(results) == 0

    def test_temporal_write_new_records(self, app, sample_attorney_data):
        """Test temporal write with new records."""
        today = datetime.date.today()

        # Convert sample data to attorney models
        attorneys, _ = convert_to_models(sample_attorney_data, [])

        # Write to temporal database
        temporal_db.temporal_write(Attorney, attorneys, today)

        # Verify records were created
        query = temporal_db.temporal_query(Attorney, today)
        results = db.session.execute(query).scalars().all()

        assert len(results) == 2
        names = {result.name for result in results}
        assert names == {'John Smith', 'Jane Doe'}

        # All records should be valid from today
        for result in results:
            assert result.valid_from == today
            assert result.valid_to is None

    def test_temporal_write_update_existing(self, app):
        """Test temporal write with updated records."""
        today = datetime.date.today()

        # Create initial record
        original = Attorney(
            external_id='temp-update-1',
            name='Original Name',
            email='original@test.com',
            patents=True,
            trademarks=False,
            valid_from=today,
            valid_to=None
        )
        db.session.add(original)
        db.session.commit()

        # Create updated version
        updated = Attorney(
            external_id='temp-update-1',
            name='Original Name',
            email='updated@test.com',  # Changed email
            patents=True,
            trademarks=False,
            valid_from=today,
            valid_to=None
        )

        # Write updated record
        temporal_db.temporal_write(Attorney, [updated], today)

        # Query all records with this external_id
        query = sa.select(Attorney).where(Attorney.external_id == 'temp-update-1').order_by(Attorney.valid_from)
        results = db.session.execute(query).scalars().all()

        assert len(results) == 2
        # First record should be expired
        assert results[0].email == 'original@test.com'
        assert results[0].valid_to == today
        # Second record should be current
        assert results[1].email == 'updated@test.com'
        assert results[1].valid_to is None

    def test_temporal_write_lapse_missing_records(self, app):
        """Test temporal write lapses records not in incoming data."""
        today = datetime.date.today()

        # Create initial records
        attorney1 = Attorney(
            external_id='lapse-test-1',
            name='Attorney 1',
            patents=True,
            trademarks=False,
            valid_from=today,
            valid_to=None
        )
        attorney2 = Attorney(
            external_id='lapse-test-2',
            name='Attorney 2',
            patents=True,
            trademarks=False,
            valid_from=today,
            valid_to=None
        )
        db.session.add_all([attorney1, attorney2])
        db.session.commit()

        # Write only one attorney (attorney1 should be lapsed)
        updated_attorney2 = Attorney(
            external_id='lapse-test-2',
            name='Attorney 2',
            patents=True,
            trademarks=False,
            valid_from=today,
            valid_to=None
        )

        temporal_db.temporal_write(Attorney, [updated_attorney2], today)

        # Check that attorney1 is lapsed
        attorney1_refreshed = db.session.get(Attorney, attorney1.id)
        assert attorney1_refreshed.valid_to == today

        # Check that attorney2 is still valid
        query = temporal_db.temporal_query(Attorney, today)
        results = db.session.execute(query).scalars().all()
        assert len(results) == 1
        assert results[0].name == 'Attorney 2'


class TestDataProcessing:
    """Test data processing functions."""

    def test_separate_data(self, sample_json_data):
        """Test separation of attorneys and firms from mixed data."""
        # Extract HTML data first
        extracted_data = extract_html_data(sample_json_data["Results"])
        attorneys, firms = separate_data(extracted_data)

        # Check that data is properly separated
        assert len(attorneys) == 2  # Should have 2 attorneys
        assert len(firms) == 2      # Should have 2 firms

        # Verify attorney data
        attorney_names = {attorney['Attorney'] for attorney in attorneys}
        assert 'Sarah Mitchell' in attorney_names
        assert 'Michael Chen' in attorney_names

        # Verify firm data
        firm_names = {firm['Firm'] for firm in firms}
        assert 'Global IP Partners' in firm_names
        assert 'Boutique IP Law' in firm_names

    def test_convert_to_models_attorneys(self, app, sample_attorney_data):
        """Test conversion of attorney data to models."""
        attorney_models, _ = convert_to_models(sample_attorney_data, [])

        assert len(attorney_models) == 2
        assert all(isinstance(model, Attorney) for model in attorney_models)

        # Check first attorney
        john = next(model for model in attorney_models if model.name == 'John Smith')
        assert john.external_id == 'test-attorney-1'
        assert john.phone == '+61 2 1234 5678'
        assert john.email == 'john.smith@example.com'
        assert john.firm == 'Example Law Firm'
        assert john.patents is True
        assert john.trademarks is True
        assert john.valid_from == datetime.date.today()
        assert john.valid_to is None

    def test_convert_to_models_firms(self, app, sample_firm_data):
        """Test conversion of firm data to models."""
        _, firm_models = convert_to_models([], sample_firm_data)

        assert len(firm_models) == 2
        assert all(isinstance(model, Firm) for model in firm_models)

        # Check first firm
        abc = next(model for model in firm_models if model.name == 'ABC IP Law Firm')
        assert abc.external_id == 'test-firm-1'
        assert abc.phone == '+61 2 8765 4321'
        assert abc.email == 'contact@abciplaw.com.au'
        assert abc.website == 'https://www.abciplaw.com.au'
        assert abc.directors == 'Alice Cooper, Bob Johnson'
        assert abc.patents is True
        assert abc.trademarks is True

    def test_convert_to_models_boolean_fields(self, app):
        """Test conversion of 'Registered as' field to boolean fields."""
        test_cases = [
            {'Id': '1', 'Attorney': 'Test 1', 'Registered as': 'Patents'},
            {'Id': '2', 'Attorney': 'Test 2', 'Registered as': 'Trade marks'},
            {'Id': '3', 'Attorney': 'Test 3', 'Registered as': 'Patents, Trade marks'},
            {'Id': '4', 'Attorney': 'Test 4', 'Registered as': ''},
        ]

        attorney_models, _ = convert_to_models(test_cases, [])

        assert attorney_models[0].patents is True
        assert attorney_models[0].trademarks is False

        assert attorney_models[1].patents is False
        assert attorney_models[1].trademarks is True

        assert attorney_models[2].patents is True
        assert attorney_models[2].trademarks is True

        assert attorney_models[3].patents is False
        assert attorney_models[3].trademarks is False

    def test_merge_write_new_firms(self, app, sample_firm_data):
        """Test merge write with new firms."""
        _, firm_models = convert_to_models([], sample_firm_data)

        # Write to database
        merge_write(firm_models)

        # Verify firms were created
        firms_in_db = db.session.execute(sa.select(Firm)).scalars().all()
        assert len(firms_in_db) == 2

        names = {firm.name for firm in firms_in_db}
        assert names == {'ABC IP Law Firm', 'XYZ Patent Services'}

    def test_merge_write_update_existing_firms(self, app):
        """Test merge write with updated existing firms."""
        # Create initial firm
        original_firm = Firm(
            external_id='merge-test-1',
            name='Original Firm Name',
            email='original@test.com',
            patents=True,
            trademarks=False
        )
        db.session.add(original_firm)
        db.session.commit()
        original_id = original_firm.id

        # Create updated version
        updated_firm = Firm(
            external_id='merge-test-1',
            name='Original Firm Name',
            email='updated@test.com',  # Changed email
            patents=True,
            trademarks=True  # Changed trademark status
        )

        # Merge write
        merge_write([updated_firm])

        # Verify update
        firm_in_db = db.session.get(Firm, original_id)
        assert firm_in_db.email == 'updated@test.com'
        assert firm_in_db.trademarks is True

        # Should still be only one firm
        all_firms = db.session.execute(sa.select(Firm)).scalars().all()
        assert len(all_firms) == 1

    def test_merge_write_no_change(self, app):
        """Test merge write when no changes are needed."""
        # Create initial firm
        original_firm = Firm(
            external_id='no-change-test',
            name='Unchanged Firm',
            email='same@test.com',
            patents=True,
            trademarks=False
        )
        db.session.add(original_firm)
        db.session.commit()
        original_id = original_firm.id

        # Create identical firm
        identical_firm = Firm(
            external_id='no-change-test',
            name='Unchanged Firm',
            email='same@test.com',
            patents=True,
            trademarks=False
        )

        # Merge write
        merge_write([identical_firm])

        # Verify no changes
        firm_in_db = db.session.get(Firm, original_id)
        assert firm_in_db.name == 'Unchanged Firm'
        assert firm_in_db.email == 'same@test.com'

        # Should still be only one firm
        all_firms = db.session.execute(sa.select(Firm)).scalars().all()
        assert len(all_firms) == 1


class TestFullIntegration:
    """Test full integration scenarios."""

    def test_full_data_processing_flow(self, app, sample_json_data):
        """Test complete data processing flow from JSON to database."""
        today = datetime.date.today()

        # Process the data through the full pipeline
        extracted_data = extract_html_data(sample_json_data["Results"])
        attorneys, firms = separate_data(extracted_data)
        attorney_models, firm_models = convert_to_models(attorneys, firms)

        # Write to database
        temporal_db.temporal_write(Attorney, attorney_models, today)
        merge_write(firm_models)

        # Verify attorneys in temporal database
        attorney_query = temporal_db.temporal_query(Attorney, today)
        attorneys_in_db = db.session.execute(attorney_query).scalars().all()
        assert len(attorneys_in_db) == 2

        attorney_names = {attorney.name for attorney in attorneys_in_db}
        expected_attorney_names = {'Sarah Mitchell', 'Michael Chen'}
        assert attorney_names == expected_attorney_names

        # Verify firms in database
        firms_in_db = db.session.execute(sa.select(Firm)).scalars().all()
        assert len(firms_in_db) == 2

        firm_names = {firm.name for firm in firms_in_db}
        expected_firm_names = {'Global IP Partners', 'Boutique IP Law'}
        assert firm_names == expected_firm_names

    def test_data_consistency_across_operations(self, app):
        """Test data consistency across multiple operations."""
        today = datetime.date.today()

        # First batch of data
        batch1_attorneys = [
            {
                'Id': 'consistency-1',
                'Attorney': 'Consistent Attorney',
                'Email': 'consistent@test.com',
                'Registered as': 'Patents'
            }
        ]
        batch1_firms = [
            {
                'Id': 'consistency-firm-1',
                'Firm': 'Consistent Firm',
                'Email': 'firm@test.com',
                'Registered as': 'Trade marks'
            }
        ]

        # Process first batch
        attorney_models1, firm_models1 = convert_to_models(batch1_attorneys, batch1_firms)
        temporal_db.temporal_write(Attorney, attorney_models1, today)
        merge_write(firm_models1)

        # Verify first batch
        attorney_count = db.session.execute(sa.select(sa.func.count(Attorney.id))).scalar()
        firm_count = db.session.execute(sa.select(sa.func.count(Firm.id))).scalar()
        assert attorney_count == 1
        assert firm_count == 1

        # Second batch with updates
        batch2_attorneys = [
            {
                'Id': 'consistency-1',
                'Attorney': 'Consistent Attorney',
                'Email': 'updated@test.com',  # Changed email
                'Registered as': 'Patents'
            },
            {
                'Id': 'consistency-2',
                'Attorney': 'New Attorney',
                'Email': 'new@test.com',
                'Registered as': 'Trade marks'
            }
        ]
        batch2_firms = [
            {
                'Id': 'consistency-firm-1',
                'Firm': 'Consistent Firm',
                'Email': 'firm@test.com',  # No change
                'Registered as': 'Trade marks'
            }
        ]

        # Process second batch
        attorney_models2, firm_models2 = convert_to_models(batch2_attorneys, batch2_firms)
        temporal_db.temporal_write(Attorney, attorney_models2, today)
        merge_write(firm_models2)

        # Verify final state
        current_query = temporal_db.temporal_query(Attorney, today)
        current_attorneys = db.session.execute(current_query).scalars().all()
        assert len(current_attorneys) == 2

        # Check that the first attorney was updated
        consistent_attorney = next(a for a in current_attorneys if a.name == 'Consistent Attorney')
        assert consistent_attorney.email == 'updated@test.com'

        # Check that new attorney was added
        new_attorney = next(a for a in current_attorneys if a.name == 'New Attorney')
        assert new_attorney.email == 'new@test.com'

        # Firm should remain unchanged (only one)
        all_firms = db.session.execute(sa.select(Firm)).scalars().all()
        assert len(all_firms) == 1
        assert all_firms[0].email == 'firm@test.com'
