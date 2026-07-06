import datetime
import re

import sqlalchemy as sa
import Levenshtein

from app import db, temporal_db
from app.models import Attorney, IncorporatedFirm, ConsolidatedFirm


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

    # Group each original firm spelling by its normalised name, then for each
    # group pick the display name derived from the highest-frequency spelling
    # (tie-break: lexicographically smallest normalised form, then first-seen).
    # This replaces the previous pandas groupby(...).sort_values(...) logic.
    groups: dict[str, list[dict]] = {}
    for firm_name in unique_firms:
        normalized = normalize_firm_name(firm_name)
        if not normalized:
            continue
        groups.setdefault(normalized, []).append({
            "original": firm_name,
            "frequency": firm_frequency.get(firm_name, 1),
            "clean": normalized,
        })

    consolidated = {}
    for normalized, entries in groups.items():
        best = min(entries, key=lambda e: (-e["frequency"], e["clean"]))
        consolidated[normalized] = clean_display_name(best["original"])

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
