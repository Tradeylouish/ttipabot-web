import datetime
import re
from pathlib import Path

import numpy as np
import pandas as pd
import sqlalchemy as sa
import Levenshtein

from app import db, temporal_db
from app.models import Attorney, IncorporatedFirm, ConsolidatedFirm


def parse_date_from_filename(filename: str) -> datetime.date:
    """Extracts date from filename, expects format YYYY-MM-DD.csv"""
    stem = Path(filename).stem
    return datetime.datetime.strptime(stem, "%Y-%m-%d").date()


def normalize_external_id(row):
    ext_id = row.get("external_id")
    if not ext_id:
        current_query = temporal_db.temporal_query(
            model=Attorney,
            as_of_date=datetime.date.today(),
            criterion=[Attorney.name == row.get("name")],
        )
        current_attorney = db.session.execute(current_query).scalar()
        if current_attorney:
            return current_attorney.external_id

    return str(row.get("name")).strip().lower()[:36]


def migrate_csvs(csv_dir: Path) -> None:
    """Imports CSV files into the DB using pandas for efficient processing."""
    if not csv_dir.exists():
        raise FileNotFoundError("CSV directory does not exist.")

    csv_files = sorted(
        csv_dir.glob("*.csv"), key=lambda f: parse_date_from_filename(f.name)
    )

    for csv_file in csv_files:
        print(f"Migrating {csv_file.name}")
        attorneys = csv_to_attorneys(csv_file)
        temporal_db.temporal_write(
            Attorney, attorneys, parse_date_from_filename(csv_file.name)
        )


def csv_to_attorneys(csv_file: Path) -> list[Attorney]:
    csv_date = parse_date_from_filename(csv_file.name)
    df = pd.read_csv(csv_file)

    # Map DataFrame columns to Attorney fields
    column_map = {
        "Name": "name",
        "Phone": "phone",
        "Email": "email",
        "Firm": "firm",
        "Address": "address",
    }
    df = df.rename(columns=column_map)

    # Normalize external_id
    df["external_id"] = None
    df["external_id"] = df.apply(normalize_external_id, axis=1)

    # Prepare boolean fields
    df["patents"] = df.get("Registered as", "").apply(lambda x: "Patents" in str(x))
    df["trademarks"] = df.get("Registered as", "").apply(
        lambda x: "Trade marks" in str(x)
    )
    df.drop(columns=["Registered as"], inplace=True)

    # Replace NaN with None
    df.replace({np.nan: None}, inplace=True)

    # Add valid_from
    df["valid_from"] = csv_date

    return [Attorney(**row) for row in df.to_dict(orient="records")]


def delete_new_scrapes():
    """Deletes all attorneys with a valid_from date of today or later.
    Intended for use only during migration, when a new scrape needs rewriting to
    properly connect it to the historical data."""
    delete_query = sa.delete(Attorney).where(
        Attorney.valid_from >= datetime.date.today()
    )
    db.session.execute(delete_query)
    db.session.commit()


def patch_external_ids(replace_id: str, new_id: str):
    """Updates the external_id for all attorney records matching replace_id."""
    update_statement = (
        sa.update(Attorney)
        .where(Attorney.external_id == replace_id)
        .values(external_id=new_id)
    )
    db.session.execute(update_statement)
    db.session.commit()


def clean_display_name(firm_name: str) -> str:
    """Strips company suffixes from firm name for cleaner display, preserving original case."""
    if not firm_name:
        return ""

    # First normalize (apply aliases, uppercase) then convert to title case
    normalized = normalize_firm_name(firm_name)
    
    # Identify short words that are all-caps (likely initials like FB, AJ, IP)
    # Also preserve some common abbreviations that should stay uppercase
    common_words = {'AND', 'THE', 'FOR', 'OF', 'IN', 'TO', 'A', 'AN', 'AT', 'BY'}
    preserved_words = {'IP', 'IT', 'TV', 'OS', 'AI', 'ML', 'UK', 'US', 'EU', 'NZ', 'AU'}
    normalized_words = normalized.split()
    uppercase_words = {
        w for w in normalized_words 
        if w.isupper() and len(w) <= 3 and w not in common_words
    } | preserved_words
    
    # Convert to title case
    title_cased = normalized.title()
    
    # Restore uppercase for short words that were all-caps in normalized form
    words = title_cased.split()
    result_words = []
    for word in words:
        if word.upper() in uppercase_words:
            result_words.append(word.upper())
        else:
            result_words.append(word)
    
    return ' '.join(result_words)


def normalize_firm_name(firm_name: str) -> str:
    """Normalizes firm name for matching by converting to uppercase and removing suffixes."""
    if not firm_name:
        return ""

    normalized = firm_name.upper().strip()

    # Replace & with AND
    normalized = normalized.replace('&', 'AND')

    # Replace commas with space, then clean up extra spaces
    normalized = normalized.replace(',', ' ')
    normalized = ' '.join(normalized.split())

    # Remove parentheses and their contents
    normalized = re.sub(r'\s*\([^)]*\)\s*', ' ', normalized)

    # Remove common prefixes at the START only (not in middle of string)
    if normalized.startswith('THE '):
        normalized = normalized[4:]

    # Hard-coded aliases for specific firm name variations (applied after basic normalization)
    aliases = {
        'IPONZ': 'INTELLECTUAL PROPERTY OFFICE OF NEW ZEALAND',
        'IPO NZ': 'INTELLECTUAL PROPERTY OFFICE OF NEW ZEALAND',
        'INTELLECTUAL PROPERTY OFFICE OF NZ': 'INTELLECTUAL PROPERTY OFFICE OF NEW ZEALAND',
        'DENTONS AUSTRALIA': 'DENTONS',
        'DENTONS AUSTRALIA LIMITED': 'DENTONS',
        'DENTONS KENSINGTON SWAN': 'DENTONS',
        'DENTONS PATENT ATTORNEYS AUSTRALASIA': 'DENTONS',
        'DENTONS PATENT ATTORNEYS AUSTRALASIA LIMITED': 'DENTONS',
        'DENTONS PATENT ATTORNEYS AUSTRALASIA LTD': 'DENTONS',
        'WELLINGTON UNIVENTURES': 'WELLINGTON UNIVENTURES',
        'VICTORIA LINK LIMITED T/A WELLINGTON UNIVERNTURES': 'WELLINGTON UNIVENTURES',
        'SPRUSON AND FERGUSON ASIA': 'SPRUSON AND FERGUSON',
        'SPRUSON AND FERGUSON ASIA LIMITED': 'SPRUSON AND FERGUSON',
        'SPRUSON AND FERGUSON ASIA PTE': 'SPRUSON AND FERGUSON',
        'SPRUSON AND FERGUSON ASIA PTE LTD': 'SPRUSON AND FERGUSON',
    }
    if normalized in aliases:
        return aliases[normalized]

    # Remove regional office suffixes - both with hyphen and standalone at end
    # Note: Don't strip HONG KONG as it appears in legitimate names like "University of Hong Kong"
    regional_office_patterns = [
        r'\s+-\s+(SYDNEY|MELBOURNE|BRISBANE|PERTH|ADELAIDE|CANBERRA|HOBART|DARWIN|NZ)\s*$',
        r'\s+-\s+(SYDNEY|MELBOURNE|BRISBANE|PERTH|ADELAIDE|CANBERRA|HOBART|DARWIN|NZ)\s+\d+\s*$',
        r'\s+(SYDNEY|MELBOURNE|BRISBANE|PERTH|ADELAIDE|CANBERRA|HOBART|DARWIN|ASIA)$',
        r'\s*-\s*$',  # trailing hyphen only
    ]
    for pattern in regional_office_patterns:
        normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)

    # Run multiple passes to handle chained suffixes like " - BRISBANE - 1844"
    for _ in range(3):
        regional_patterns = [
            r'\s*-\s*(SYDNEY|MELBOURNE|BRISBANE|PERTH|ADELAIDE|CANBERRA|HOBART|DARWIN|NEW SOUTH WALES|VICTORIA|QUEENSLAND|WESTERN AUSTRALIA|SOUTH AUSTRALIA|TASMANIA|NORTHERN TERRITORY|ACT|NSW|VIC|QLD|WA|SA|TAS|NT)\s*\d*$',
            r'\s*-\s+(HONG\s*KONG|ASIA|NZ|AUSTRALIA|LAW)$',
            r'\s+-\s+\d+$',
            r'\s*-\s*$',
        ]
        for pattern in regional_patterns:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)

    # Remove trailing company suffixes and attorney designations
    # Order matters: longer/more specific first
    suffixes = [
        " ADDRESS",
        " T/AS",
        " T/A",
        " PTY LTD",
        " PTY LIMITED",
        " PTY. LTD.",
        " PTY.",
        " PTE LTD",
        " PTE LIMITED",
        " LIMITED",
        " LTD.",
        " LTD",
        " LLC",
        " LLP",
        " LAWYERS",
        " GROUP",
        " IP",
        " LAW",
        " CORPORATION",
        " CORP",
        " SERVICES",
        " PATENT AND TRADE MARK ATTORNEYS",
        " PATENT AND TRADE MARKS ATTORNEYS",
        " PATENT AND TRADEMARK ATTORNEYS",
        " PATENT AND TRADEMARK ATTORNEY",
        " PATENT & TRADE MARK ATTORNEYS",
        " PATENT & TRADE MARKS ATTORNEYS",
        " PATENT & TRADEMARK ATTORNEYS",
        " PATENT & TRADEMARK ATTORNEY",
        " TRADE MARK ATTORNEYS",
        " TRADE MARKS ATTORNEYS",
        " TRADEMARK ATTORNEYS",
        " ATTORNEYS",
        " ATTORNEY",
        ",",
    ]

    # Use regex to remove suffixes (handles cases like "PTY LTD T/AS")
    suffix_patterns = [
        r'\s+PTY\s+LTD\.?\s*T/?AS.*$',
        r'\s+PTY\s+LTD\.?$',
        r'\s+PTE\s+LTD\.?$',
        r'\s+LIMITED\.?$',
        r'\s+LTD\.?$',
        r'\s+LLC\.?$',
        r'\s+LLP\.?$',
        r'\s+T/?AS\.?$',
        r'\s+T/?A\.?$',
        r'\s+LAWYERS?\.?$',
        r'\s+ATTORNEYS?\.?$',
        r'\s+GROUP\.?$',
        r'\s+LAW\.?$',
        r'\s+CORPORATION\.?$',
        r'\s+CORP\.?$',
        r'\s+SERVICES\.?$',
        r'\s+PATENT\s+AND\s+TRADE\s+MARK\s+ATTORNEYS?\.?$',
        r'\s+PATENT\s+AND\s+TRADE\s+MARKS?\s+ATTORNEYS?\.?$',
        r'\s+PATENT\s+AND\s+TRADEMARK\s+ATTORNEYS?\.?$',
        r'\s+PATENT\s+&\s+TRADE\s+MARK\s+ATTORNEYS?\.?$',
        r'\s+PATENT\s+&\s+TRADE\s+MARKS?\s+ATTORNEYS?\.?$',
        r'\s+PATENT\s+&\s+TRADEMARK\s+ATTORNEYS?\.?$',
        r'\s+TRADE\s+MARK\s+ATTORNEYS?\.?$',
        r'\s+TRADE\s+MARKS?\s+ATTORNEYS?\.?$',
        r'\s+TRADEMARK\s+ATTORNEYS?\.?$',
        r',$',
    ]
    for pattern in suffix_patterns:
        normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
    
    normalized = re.sub(r'\s+ADDRESS\s*$', '', normalized, flags=re.IGNORECASE)
    normalized = re.sub(r'\.?\s*$', '', normalized)

    # Remove duplicate words (e.g., "VICTORIA SERVICES VICTORIA" -> "VICTORIA SERVICES")
    words = normalized.split()
    seen = set()
    result = []
    for word in words:
        if word not in seen:
            result.append(word)
            seen.add(word)
    normalized = ' '.join(result)

    return normalized


def find_firm_by_name(normalized_name: str, firms: list) -> int:
    """Finds a firm ID by normalized name matching with fuzzy Levenshtein distance."""
    if not normalized_name:
        return None

    for firm_id, firm_name in firms:
        if normalize_firm_name(firm_name) == normalized_name:
            return firm_id

    best_match = None
    best_distance = None
    best_firm_id = None

    for firm_id, firm_name in firms:
        normalized_firm = normalize_firm_name(firm_name)

        distance = Levenshtein.distance(normalized_name, normalized_firm)

        max_len = max(len(normalized_name), len(normalized_firm))
        similarity = 1 - (distance / max_len) if max_len > 0 else 0

        if similarity >= 0.85:
            if best_distance is None or distance < best_distance:
                best_match = firm_name
                best_distance = distance
                best_firm_id = firm_id

    if best_firm_id is not None:
        print(
            f"Fuzzy match: '{normalized_name}' -> '{best_match}' (distance: {best_distance})"
        )
        return best_firm_id

    return None


def populate_firm_records():
    """Populates consolidated_firms table and matches attorneys and incorporated firms to it."""
    print("Step 1: Clearing consolidated_firms table...")
    db.session.execute(sa.delete(ConsolidatedFirm))
    db.session.commit()

    print("\nStep 2: Getting unique firm names from attorneys...")
    unique_firms_query = sa.select(Attorney.firm).where(
        Attorney.firm.isnot(None)
    ).distinct()
    unique_firms = db.session.execute(unique_firms_query).scalars().all()
    print(f"Found {len(unique_firms)} unique firm names in attorney records")

    # Also get firm name frequencies from attorneys table
    firm_freq_query = sa.select(Attorney.firm, sa.func.count(Attorney.id).label('count')).where(
        Attorney.firm.isnot(None)
    ).group_by(Attorney.firm)
    firm_freqs = db.session.execute(firm_freq_query).all()
    firm_frequency = {f.firm: f.count for f in firm_freqs}

    print("\nStep 3: Deduplicating and creating consolidated_firm records...")

    # Build a DataFrame of firm names with frequencies
    firm_data = []
    for firm_name in unique_firms:
        normalized = normalize_firm_name(firm_name)
        if not normalized:
            continue
        freq = firm_frequency.get(firm_name, 1)
        # Create a clean display name by stripping suffixes from original
        display_name = clean_display_name(firm_name)
        firm_data.append({
            'original': firm_name,
            'normalized': normalized,
            'display': display_name,
            'frequency': freq,
            'clean': normalized,  # Use normalized (uppercase, aliases applied) as clean name
        })

    df = pd.DataFrame(firm_data)

    # Group by normalized name and find the best display name:
    # Prefer the shortest clean name among high-frequency options
    def select_best_display(group):
        # Sort by frequency desc, then by length asc (shorter = cleaner)
        sorted_group = group.sort_values(['frequency', 'clean'], ascending=[False, True])
        # Get the original name that had the shortest clean form
        original_name = sorted_group.iloc[0]['original']
        # Use clean_display_name to convert to proper title case with initials preserved
        return clean_display_name(original_name)

    consolidated = df.groupby('normalized').apply(select_best_display, include_groups=False).to_dict()

    # Create consolidated firm records
    consolidated_firms = {}
    normalized_to_id = {}
    for normalized, display_name in consolidated.items():
        cf = ConsolidatedFirm(name=display_name)
        db.session.add(cf)
        db.session.flush()
        normalized_to_id[normalized] = cf.id
        consolidated_firms[cf.id] = display_name

    db.session.commit()
    print(f"Created {len(consolidated_firms)} consolidated_firm records")

    print("\nStep 4: Matching attorneys to consolidated_firms...")
    attorneys_query = sa.select(Attorney.id, Attorney.firm).where(
        Attorney.firm.isnot(None)
    )
    attorneys = db.session.execute(attorneys_query).all()

    matched_attorneys = 0
    for attorney_id, firm_name in attorneys:
        normalized = normalize_firm_name(firm_name)
        cf_id = normalized_to_id.get(normalized)
        if cf_id:
            update_statement = (
                sa.update(Attorney)
                .where(Attorney.id == attorney_id)
                .values(consolidated_firm_id=cf_id)
            )
            db.session.execute(update_statement)
            matched_attorneys += 1

    db.session.commit()
    print(f"Matched {matched_attorneys} attorneys to consolidated_firms")

    print("\nStep 5: Matching consolidated_firms to incorporated_firms...")
    incorporated_firms_query = sa.select(IncorporatedFirm.id, IncorporatedFirm.name)
    incorporated_firms = db.session.execute(incorporated_firms_query).all()

    cf_to_if = {}
    for cf_id, cf_name in consolidated_firms.items():
        normalized_cf = normalize_firm_name(cf_name)
        if_id = find_firm_by_name(normalized_cf, incorporated_firms)
        if if_id:
            cf_to_if[cf_id] = if_id

    matched_incorporated = 0
    for cf_id, if_id in cf_to_if.items():
        update_statement = (
            sa.update(IncorporatedFirm)
            .where(IncorporatedFirm.id == if_id)
            .values(consolidated_firm_id=cf_id)
        )
        db.session.execute(update_statement)
        matched_incorporated += 1

    db.session.commit()
    print(f"Matched {matched_incorporated} incorporated_firms to consolidated_firms")

    print("\n" + "=" * 50)
    print("Firm record population completed:")
    print(f"  - Consolidated firms created: {len(consolidated_firms)}")
    print(f"  - Attorneys matched: {matched_attorneys}")
    print(f"  - Incorporated firms matched: {matched_incorporated}")


def link_attorneys_to_consolidated_firms(attorney_ids: list[int] | None = None) -> int:
    """
    Link attorneys to consolidated firms, creating new ones if needed.
    
    If attorney_ids is provided, processes only those attorneys.
    Otherwise, processes all attorneys with null consolidated_firm_id.
    
    Returns the number of attorneys linked.
    """
    if attorney_ids:
        query = sa.select(Attorney.id, Attorney.firm).where(Attorney.id.in_(attorney_ids))
    else:
        query = sa.select(Attorney.id, Attorney.firm).where(
            sa.and_(
                Attorney.firm.isnot(None),
                Attorney.consolidated_firm_id.is_(None)
            )
        )
    
    attorneys = db.session.execute(query).all()
    if not attorneys:
        return 0
    
    existing_consolidated = db.session.execute(
        sa.select(ConsolidatedFirm.id, ConsolidatedFirm.name)
    ).all()
    
    normalized_to_id = {}
    normalized_names = {}
    
    for cf_id, cf_name in existing_consolidated:
        normalized = normalize_firm_name(cf_name)
        normalized_to_id[normalized] = cf_id
        normalized_names[normalized] = cf_name
    
    created_count = 0
    matched_count = 0
    
    for attorney_id, firm_name in attorneys:
        if not firm_name:
            continue
            
        normalized = normalize_firm_name(firm_name)
        if not normalized:
            continue
        
        cf_id = normalized_to_id.get(normalized)
        
        if not cf_id:
            display_name = clean_display_name(firm_name)
            cf = ConsolidatedFirm(name=display_name)
            db.session.add(cf)
            db.session.flush()
            cf_id = cf.id
            normalized_to_id[normalized] = cf_id
            normalized_names[normalized] = display_name
            created_count += 1
            
            print(f"Created new consolidated_firm: '{display_name}' for attorney {attorney_id}")
        
        update_statement = (
            sa.update(Attorney)
            .where(Attorney.id == attorney_id)
            .values(consolidated_firm_id=cf_id)
        )
        db.session.execute(update_statement)
        matched_count += 1
    
    db.session.commit()
    print(f"Linked {matched_count} attorneys ({created_count} new consolidated_firms created)")
    return matched_count


def link_incorporated_firms_to_consolidated(firm_ids: list[int] | None = None) -> int:
    """
    Link incorporated firms to consolidated firms using fuzzy matching.
    
    If firm_ids is provided, processes only those firms.
    Otherwise, processes all incorporated firms with null consolidated_firm_id.
    
    Returns the number of firms linked.
    """
    if firm_ids:
        query = sa.select(IncorporatedFirm.id, IncorporatedFirm.name).where(
            IncorporatedFirm.id.in_(firm_ids)
        )
    else:
        query = sa.select(IncorporatedFirm.id, IncorporatedFirm.name).where(
            IncorporatedFirm.consolidated_firm_id.is_(None)
        )
    
    incorporated_firms = db.session.execute(query).all()
    if not incorporated_firms:
        return 0
    
    consolidated_firms = db.session.execute(
        sa.select(ConsolidatedFirm.id, ConsolidatedFirm.name)
    ).all()
    
    matched_count = 0
    for if_id, if_name in incorporated_firms:
        cf_id = find_firm_by_name(normalize_firm_name(if_name), consolidated_firms)
        
        if cf_id:
            update_statement = (
                sa.update(IncorporatedFirm)
                .where(IncorporatedFirm.id == if_id)
                .values(consolidated_firm_id=cf_id)
            )
            db.session.execute(update_statement)
            matched_count += 1
    
    db.session.commit()
    print(f"Linked {matched_count} incorporated_firms to consolidated_firms")
    return matched_count


def update_attorney_firm_links() -> int:
    """
    Update consolidated_firm_id for attorneys whose firm has changed.
    
    This handles the case where an attorney's firm field was modified
    in a scrape, and they need to be linked to a different consolidated firm.
    
    Returns the number of attorneys updated.
    """
    query = sa.select(
        Attorney.id, 
        Attorney.firm, 
        Attorney.consolidated_firm_id,
        Attorney.valid_from
    ).where(
        sa.and_(
            Attorney.firm.isnot(None),
            Attorney.valid_from == datetime.date.today()
        )
    )
    
    attorneys = db.session.execute(query).all()
    if not attorneys:
        return 0
    
    existing_consolidated = {}
    for cf in db.session.execute(sa.select(ConsolidatedFirm)).scalars().all():
        existing_consolidated[normalize_firm_name(cf.name)] = cf.id
    
    updated_count = 0
    
    for attorney_id, firm_name, current_cf_id, valid_from in attorneys:
        if not firm_name:
            continue
        
        normalized = normalize_firm_name(firm_name)
        target_cf_id = existing_consolidated.get(normalized)
        
        if not target_cf_id:
            display_name = clean_display_name(firm_name)
            cf = ConsolidatedFirm(name=display_name)
            db.session.add(cf)
            db.session.flush()
            target_cf_id = cf.id
            existing_consolidated[normalized] = target_cf_id
            print(f"Created new consolidated_firm: '{display_name}' for updated attorney {attorney_id}")
        
        if target_cf_id != current_cf_id:
            update_statement = (
                sa.update(Attorney)
                .where(Attorney.id == attorney_id)
                .values(consolidated_firm_id=target_cf_id)
            )
            db.session.execute(update_statement)
            updated_count += 1
    
    db.session.commit()
    print(f"Updated {updated_count} attorneys with new consolidated_firm links")
    return updated_count
