"""Seed script to create demo Companies and Contacts for CRM testing.

Creates a realistic set of companies across industries and contacts
with varied statuses, useful for testing grids, charts, kanban, and filters.

Usage:
    cd backend
    python -m metaforge.scripts.seed_contacts
    python -m metaforge.scripts.seed_contacts --reset
"""

import argparse
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from metaforge.metadata.loader import MetadataLoader
from metaforge.persistence import DatabaseConfig, create_adapter


def _parse_args():
    parser = argparse.ArgumentParser(description="Seed demo Companies and Contacts.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete all existing contacts and companies before seeding.",
    )
    return parser.parse_args()


def _find_tenant(db, tenant_entity):
    result = db.query(
        tenant_entity,
        filter={"conditions": [{"field": "slug", "operator": "eq", "value": "demo"}]},
        limit=1,
    )
    return result.get("data", [None])[0]


def _delete_all(db, entity):
    result = db.query(entity, limit=2000)
    for row in result.get("data", []):
        try:
            db.delete(entity, row["id"])
        except Exception:
            pass
    return len(result.get("data", []))


def main():
    args = _parse_args()

    backend_dir = Path(__file__).parent.parent.parent.parent
    base_path = backend_dir.parent
    metadata_path = base_path / "metadata"
    db_path = base_path / "data" / "metaforge.db"

    db_url = os.environ.get("DATABASE_URL") or f"sqlite:///{db_path}"
    print(f"Database: {db_url}")
    print(f"Metadata: {metadata_path}")

    if db_url.startswith("sqlite"):
        db_path.parent.mkdir(parents=True, exist_ok=True)

    loader = MetadataLoader(metadata_path)
    loader.load_all()

    db_config = DatabaseConfig(url=db_url)
    db = create_adapter(db_config)
    db.connect()

    # Initialize tables
    for entity_name in ["Tenant", "Company", "Contact"]:
        entity = loader.get_entity(entity_name)
        if entity:
            db.initialize_entity(entity)

    tenant_entity = loader.get_entity("Tenant")
    company_entity = loader.get_entity("Company")
    contact_entity = loader.get_entity("Contact")

    tenant = _find_tenant(db, tenant_entity)
    if not tenant:
        print("ERROR: Demo tenant not found. Run seed_auth first.")
        db.close()
        return

    tenant_id = tenant["id"]
    print(f"Using tenant: {tenant['name']} ({tenant_id})")

    # Check for existing data
    existing_contacts = db.query(contact_entity, limit=1)
    if existing_contacts["data"] and not args.reset:
        total = existing_contacts["pagination"]["total"]
        print(f"\nContacts already exist ({total} total). Use --reset to recreate.")
        db.close()
        return

    if args.reset:
        print("\nResetting contacts and companies...")
        n = _delete_all(db, contact_entity)
        print(f"  Deleted {n} contacts")
        n = _delete_all(db, company_entity)
        print(f"  Deleted {n} companies")

    print("\nCreating companies...")

    # --- Companies ---
    companies_data = [
        {"name": "Acme Corp",         "industry": "technology",    "website": "https://acme.example.com",       "phone": "415-555-0100", "city": "San Francisco", "state": "CA"},
        {"name": "Globex Industries",  "industry": "manufacturing", "website": "https://globex.example.com",     "phone": "312-555-0200", "city": "Chicago",       "state": "IL"},
        {"name": "Initech Solutions",  "industry": "technology",    "website": "https://initech.example.com",    "phone": "512-555-0300", "city": "Austin",        "state": "TX"},
        {"name": "Umbrella Financial", "industry": "finance",       "website": "https://umbrella.example.com",   "phone": "212-555-0400", "city": "New York",      "state": "NY"},
        {"name": "Soylent Media",      "industry": "media",         "website": "https://soylent.example.com",    "phone": "310-555-0500", "city": "Los Angeles",   "state": "CA"},
        {"name": "Vandelay Import",    "industry": "retail",        "website": "https://vandelay.example.com",   "phone": "646-555-0600", "city": "New York",      "state": "NY"},
        {"name": "Prestige Worldwide", "industry": "consulting",    "website": "https://prestige.example.com",   "phone": "617-555-0700", "city": "Boston",        "state": "MA"},
        {"name": "Bluth Company",      "industry": "real_estate",   "website": "https://bluth.example.com",      "phone": "949-555-0800", "city": "Newport Beach", "state": "CA"},
        {"name": "Pied Piper Inc",     "industry": "technology",    "website": "https://piedpiper.example.com",  "phone": "650-555-0900", "city": "Palo Alto",     "state": "CA"},
        {"name": "Dunder Mifflin",     "industry": "manufacturing", "website": "https://dundermifflin.example.com","phone": "570-555-1000","city": "Scranton",     "state": "PA"},
    ]

    companies = {}
    for c in companies_data:
        record = {
            "tenantId": tenant_id,
            "name": c["name"],
            "industry": c.get("industry"),
            "website": c.get("website"),
            "phone": c.get("phone"),
        }
        created = db.create(company_entity, record)
        companies[c["name"]] = created["id"]
        print(f"  {c['name']}: {created['id']}")

    print(f"\nCreating contacts...")

    # --- Contacts: (firstName, lastName, email, phone, status, notes, companyName) ---
    contacts_data = [
        # Acme Corp
        ("James",    "Wilson",    "james.wilson@acme.example.com",    "415-555-0101", "active",   "Key decision maker. Met at SaaStr.",                "Acme Corp"),
        ("Sarah",    "Chen",      "sarah.chen@acme.example.com",      "415-555-0102", "active",   "Engineering lead. Prefers async comms.",             "Acme Corp"),
        ("Marcus",   "Reed",      "marcus.reed@acme.example.com",     "415-555-0103", "inactive", "Former champion, left company.",                    "Acme Corp"),

        # Globex Industries
        ("Linda",    "Park",      "linda.park@globex.example.com",    "312-555-0201", "active",   "VP Operations. Very responsive.",                   "Globex Industries"),
        ("Tom",      "Kowalski",  "tom.k@globex.example.com",         "312-555-0202", "lead",     "Inbound from trade show. Evaluating Q3.",           "Globex Industries"),

        # Initech Solutions
        ("Bill",     "Lumbergh",  "bill.l@initech.example.com",       "512-555-0301", "active",   "Needs TPS reports. Very process-oriented.",         "Initech Solutions"),
        ("Peter",    "Gibbons",   "peter.g@initech.example.com",      "512-555-0302", "inactive", "Low engagement. Do not prioritize.",                "Initech Solutions"),
        ("Michael",  "Bolton",    "michael.b@initech.example.com",    "512-555-0303", "lead",     "Referred by Bill. Follow up next week.",            "Initech Solutions"),

        # Umbrella Financial
        ("Diana",    "Prince",    "diana.p@umbrella.example.com",     "212-555-0401", "active",   "CFO. Budget approved for Q2.",                      "Umbrella Financial"),
        ("Clark",    "Kent",      "clark.k@umbrella.example.com",     "212-555-0402", "active",   "Director of Compliance. Needs security docs.",      "Umbrella Financial"),
        ("Bruce",    "Wayne",     "bruce.w@umbrella.example.com",     "212-555-0403", "lead",     "New contact. Self-described as very busy.",         "Umbrella Financial"),

        # Soylent Media
        ("Charlton", "Heston",    "c.heston@soylent.example.com",     "310-555-0501", "active",   "Long-time customer. Renewal coming up in Sept.",    "Soylent Media"),
        ("Talia",    "Winters",   "talia.w@soylent.example.com",      "310-555-0502", "lead",     "Content strategy lead. Demoed last month.",         "Soylent Media"),

        # Vandelay Import
        ("Art",      "Vandelay",  "art@vandelay.example.com",         "646-555-0601", "active",   "Owner. Makes all decisions himself.",               "Vandelay Import"),
        ("George",   "Costanza",  "george.c@vandelay.example.com",    "646-555-0602", "inactive", "Claims to be an architect. Unresponsive.",          "Vandelay Import"),

        # Prestige Worldwide
        ("Brennan",  "Huff",      "brennan.h@prestige.example.com",   "617-555-0701", "active",   "Co-founder. Very enthusiastic.",                   "Prestige Worldwide"),
        ("Dale",     "Doback",    "dale.d@prestige.example.com",       "617-555-0702", "lead",     "Partner. Wants a full demo with live data.",        "Prestige Worldwide"),

        # Bluth Company
        ("George",   "Bluth",     "george.b@bluth.example.com",       "949-555-0801", "inactive", "On leave. Coordinate with Michael.",               "Bluth Company"),
        ("Michael",  "Bluth",     "michael.bluth@bluth.example.com",  "949-555-0802", "active",   "Primary contact. Very detail-oriented.",           "Bluth Company"),
        ("Tobias",   "Funke",     "tobias.f@bluth.example.com",       "949-555-0803", "lead",     "New role: Head of Talent. Exploring options.",     "Bluth Company"),

        # Pied Piper
        ("Richard",  "Hendricks", "richard.h@piedpiper.example.com",  "650-555-0901", "active",   "CEO. Obsessed with middle-out compression.",       "Pied Piper Inc"),
        ("Bertram",  "Gilfoyle",  "gilfoyle@piedpiper.example.com",   "650-555-0902", "active",   "Infrastructure lead. Skeptical of everything.",    "Pied Piper Inc"),
        ("Dinesh",   "Chugtai",   "dinesh.c@piedpiper.example.com",   "650-555-0903", "lead",     "Mobile dev. Wants API access.",                    "Pied Piper Inc"),

        # Dunder Mifflin
        ("Michael",  "Scott",     "michael.s@dundermifflin.example.com","570-555-1001","active",  "Regional Manager. Loves relationship-building.",   "Dunder Mifflin"),
        ("Dwight",   "Schrute",   "dwight.s@dundermifflin.example.com","570-555-1002","active",   "Assistant (to the) Regional Manager. Very thorough.","Dunder Mifflin"),
        ("Jim",      "Halpert",   "jim.h@dundermifflin.example.com",  "570-555-1003", "lead",     "Sales. Low-key interested. Keep warm.",            "Dunder Mifflin"),

        # No company — standalone contacts
        ("Cosmo",    "Kramer",    "kramer@example.com",               "212-555-9001", "lead",     "Entrepreneur. Multiple active ventures.",           None),
        ("Newman",   "Postman",   "newman@example.com",               "212-555-9002", "inactive", "Referred by George. Low priority.",                None),
        ("Elaine",   "Benes",     "elaine.b@example.com",             "212-555-9003", "active",   "Independent consultant. High potential.",          None),
    ]

    for first, last, email, phone, status, notes, company_name in contacts_data:
        record = {
            "tenantId": tenant_id,
            "firstName": first,
            "lastName": last,
            "email": email,
            "phone": phone,
            "status": status,
            "notes": notes,
        }
        if company_name and company_name in companies:
            record["companyId"] = companies[company_name]

        db.create(contact_entity, record)

    db.close()

    print(f"\n{'=' * 50}")
    print("Seed complete!")
    print(f"{'=' * 50}")
    print(f"  {len(companies_data)} companies")
    print(f"  {len(contacts_data)} contacts")
    print(f"    active:   {sum(1 for c in contacts_data if c[4] == 'active')}")
    print(f"    lead:     {sum(1 for c in contacts_data if c[4] == 'lead')}")
    print(f"    inactive: {sum(1 for c in contacts_data if c[4] == 'inactive')}")
    print(f"\nView at: http://localhost:5173/contacts")


if __name__ == "__main__":
    main()
