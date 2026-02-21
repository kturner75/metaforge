"""Seed script to create demo Category hierarchy for tree-view testing.

Usage:
    cd backend
    python -m metaforge.scripts.seed_categories
    python -m metaforge.scripts.seed_categories --reset
"""

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from metaforge.metadata.loader import MetadataLoader
from metaforge.persistence import DatabaseConfig, create_adapter


def _parse_args():
    parser = argparse.ArgumentParser(description="Seed Category hierarchy for local development.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing categories and recreate the demo hierarchy.",
    )
    return parser.parse_args()


def _find_tenant(db, tenant_entity):
    """Find the demo tenant (created by seed_auth)."""
    result = db.query(
        tenant_entity,
        filter={"conditions": [{"field": "slug", "operator": "eq", "value": "demo"}]},
        limit=1,
    )
    return result.get("data", [None])[0]


def _create_category(db, entity, tenant_id, name, parent_id=None, description=None, sort_order=0):
    return db.create(entity, {
        "tenantId": tenant_id,
        "name": name,
        "parentId": parent_id,
        "description": description,
        "status": "active",
        "sortOrder": sort_order,
    })


def main():
    args = _parse_args()
    backend_dir = Path(__file__).parent.parent.parent.parent
    base_path = backend_dir.parent
    metadata_path = base_path / "metadata"
    db_path = base_path / "data" / "metaforge.db"

    import os
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

    category_entity = loader.get_entity("Category")
    if not category_entity:
        print("ERROR: Category entity not found in metadata.")
        db.close()
        return

    db.initialize_entity(category_entity)
    print("Initialized table: Category")

    tenant_entity = loader.get_entity("Tenant")
    tenant = _find_tenant(db, tenant_entity)
    if not tenant:
        print("ERROR: Demo tenant not found. Run seed_auth first.")
        db.close()
        return

    tenant_id = tenant["id"]

    # Check for existing categories
    existing = db.query(category_entity, limit=1)
    if existing["data"] and not args.reset:
        print(f"\nCategories already exist ({existing['pagination']['total']} total). Use --reset to recreate.")
        db.close()
        return

    if args.reset:
        # Delete all existing categories
        all_cats = db.query(category_entity, limit=1000)
        for cat in all_cats["data"]:
            db.delete(category_entity, cat["id"])
        print(f"Deleted {len(all_cats['data'])} existing categories.")

    print("\nCreating category hierarchy...")

    # --- Technology tree ---
    tech = _create_category(db, category_entity, tenant_id,
        "Technology", description="Technical disciplines", sort_order=1)
    print(f"  Technology: {tech['id']}")

    frontend = _create_category(db, category_entity, tenant_id,
        "Frontend", parent_id=tech["id"], description="Client-side technologies", sort_order=1)
    backend_cat = _create_category(db, category_entity, tenant_id,
        "Backend", parent_id=tech["id"], description="Server-side technologies", sort_order=2)
    devops = _create_category(db, category_entity, tenant_id,
        "DevOps", parent_id=tech["id"], description="Infrastructure and deployment", sort_order=3)

    _create_category(db, category_entity, tenant_id,
        "React", parent_id=frontend["id"], sort_order=1)
    _create_category(db, category_entity, tenant_id,
        "Vue", parent_id=frontend["id"], sort_order=2)
    _create_category(db, category_entity, tenant_id,
        "Angular", parent_id=frontend["id"], sort_order=3)

    _create_category(db, category_entity, tenant_id,
        "Python", parent_id=backend_cat["id"], sort_order=1)
    _create_category(db, category_entity, tenant_id,
        "Node.js", parent_id=backend_cat["id"], sort_order=2)
    _create_category(db, category_entity, tenant_id,
        "Go", parent_id=backend_cat["id"], sort_order=3)

    _create_category(db, category_entity, tenant_id,
        "Docker", parent_id=devops["id"], sort_order=1)
    _create_category(db, category_entity, tenant_id,
        "Kubernetes", parent_id=devops["id"], sort_order=2)

    # --- Business tree ---
    biz = _create_category(db, category_entity, tenant_id,
        "Business", description="Business functions", sort_order=2)
    print(f"  Business: {biz['id']}")

    marketing = _create_category(db, category_entity, tenant_id,
        "Marketing", parent_id=biz["id"], description="Marketing strategies", sort_order=1)
    sales = _create_category(db, category_entity, tenant_id,
        "Sales", parent_id=biz["id"], description="Sales operations", sort_order=2)
    _create_category(db, category_entity, tenant_id,
        "Finance", parent_id=biz["id"], description="Financial management", sort_order=3)

    _create_category(db, category_entity, tenant_id,
        "Content Marketing", parent_id=marketing["id"], sort_order=1)
    _create_category(db, category_entity, tenant_id,
        "SEO", parent_id=marketing["id"], sort_order=2)

    _create_category(db, category_entity, tenant_id,
        "Enterprise Sales", parent_id=sales["id"], sort_order=1)
    _create_category(db, category_entity, tenant_id,
        "Inside Sales", parent_id=sales["id"], sort_order=2)

    db.close()

    print("\nSeed complete! Created 20 categories in a 3-level hierarchy.")
    print("View at: http://localhost:5173/categories")


if __name__ == "__main__":
    main()
