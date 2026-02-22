"""Seed script to create test auth data.

Usage:
    cd backend
    python -m metaforge.scripts.seed_auth
    python -m metaforge.scripts.seed_auth --reset
"""

import argparse
import sys
from pathlib import Path

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from metaforge.auth.password import PasswordService
from metaforge.metadata.loader import MetadataLoader
from metaforge.persistence import DatabaseConfig, create_adapter


def _parse_args():
    parser = argparse.ArgumentParser(description="Seed auth data for local development.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset default user passwords/roles even if demo data already exists.",
    )
    return parser.parse_args()


def _find_user_by_email(db, user_entity, email: str):
    result = db.query(
        user_entity,
        filter={"conditions": [{"field": "email", "operator": "eq", "value": email}]},
        limit=1,
    )
    data = result.get("data", [])
    return data[0] if data else None


def _ensure_membership(db, membership_entity, user_id: str, tenant_id: str, role: str, reset: bool):
    membership_result = db.query(
        membership_entity,
        filter={
            "conditions": [
                {"field": "userId", "operator": "eq", "value": user_id},
                {"field": "tenantId", "operator": "eq", "value": tenant_id},
            ]
        },
        limit=1,
    )
    data = membership_result.get("data", [])
    membership = data[0] if data else None
    if membership:
        if reset and membership.get("role") != role:
            db.update(membership_entity, membership["id"], {"role": role})
        return membership

    return db.create(
        membership_entity,
        {
            "userId": user_id,
            "tenantId": tenant_id,
            "role": role,
        },
    )


def _ensure_user(
    db,
    user_entity,
    membership_entity,
    password_service: PasswordService,
    tenant_id: str,
    email: str,
    password: str,
    name: str,
    role: str,
    reset: bool,
):
    existing = _find_user_by_email(db, user_entity, email)
    if existing:
        if reset:
            db.update(
                user_entity,
                existing["id"],
                {
                    "passwordHash": password_service.hash(password),
                    "name": name,
                    "active": 1,
                },
            )
            existing = db.get(user_entity, existing["id"]) or existing
        user_id = existing["id"]
    else:
        user = db.create(
            user_entity,
            {
                "email": email,
                "passwordHash": password_service.hash(password),
                "name": name,
                "active": 1,
            },
        )
        user_id = user["id"]

    _ensure_membership(db, membership_entity, user_id, tenant_id, role, reset)
    return user_id


def main():
    args = _parse_args()
    # Find paths
    backend_dir = Path(__file__).parent.parent.parent.parent
    base_path = backend_dir.parent
    metadata_path = base_path / "metadata"
    db_path = base_path / "data" / "metaforge.db"

    # Resolve database URL: DATABASE_URL env var takes precedence over default SQLite path
    import os
    db_url = os.environ.get("DATABASE_URL") or f"sqlite:///{db_path}"
    print(f"Database: {db_url}")
    print(f"Metadata: {metadata_path}")

    # Ensure data directory exists (only relevant for SQLite)
    if db_url.startswith("sqlite"):
        db_path.parent.mkdir(parents=True, exist_ok=True)

    # Load metadata
    loader = MetadataLoader(metadata_path)
    loader.load_all()

    # Connect to database
    db_config = DatabaseConfig(url=db_url)
    db = create_adapter(db_config)
    db.connect()

    # Initialize tables
    for entity_name in ["Tenant", "User", "TenantMembership"]:
        entity = loader.get_entity(entity_name)
        if entity:
            db.initialize_entity(entity)
            print(f"Initialized table: {entity_name}")

    # Create password service
    password_service = PasswordService()

    # Check if demo tenant already exists
    tenant_entity = loader.get_entity("Tenant")
    existing = db.query(
        tenant_entity,
        filter={"conditions": [{"field": "slug", "operator": "eq", "value": "demo"}]},
        limit=1,
    )

    if existing["data"]:
        tenant = existing["data"][0]
        print("\nDemo tenant already exists.")
        print(f"Tenant ID: {tenant['id']}")

        user_entity = loader.get_entity("User")
        membership_entity = loader.get_entity("TenantMembership")

        if args.reset:
            print("Resetting default users and memberships...")
            _ensure_user(
                db,
                user_entity,
                membership_entity,
                password_service,
                tenant["id"],
                "admin@example.com",
                "admin123",
                "Admin User",
                "admin",
                reset=True,
            )
            _ensure_user(
                db,
                user_entity,
                membership_entity,
                password_service,
                tenant["id"],
                "manager@example.com",
                "manager123",
                "Manager User",
                "manager",
                reset=True,
            )
            _ensure_user(
                db,
                user_entity,
                membership_entity,
                password_service,
                tenant["id"],
                "user@example.com",
                "user123",
                "Regular User",
                "user",
                reset=True,
            )
            _ensure_user(
                db,
                user_entity,
                membership_entity,
                password_service,
                tenant["id"],
                "readonly@example.com",
                "readonly123",
                "Read Only User",
                "readonly",
                reset=True,
            )

        print("\nDefault UI login:")
        print("  Admin:    admin@example.com / admin123")
        print("  Manager:  manager@example.com / manager123")
        print("  User:     user@example.com / user123")
        print("  Readonly: readonly@example.com / readonly123")
        print("  Tenant ID (optional):", tenant["id"])

        db.close()
        return

    # Create demo tenant
    tenant_data = {
        "name": "Demo Company",
        "slug": "demo",
        "active": 1,
    }
    tenant = db.create(tenant_entity, tenant_data)
    print(f"\nCreated Tenant: {tenant['id']} ({tenant['name']})")

    # Create admin + regular users and memberships
    user_entity = loader.get_entity("User")
    membership_entity = loader.get_entity("TenantMembership")

    admin_id = _ensure_user(
        db,
        user_entity,
        membership_entity,
        password_service,
        tenant["id"],
        "admin@example.com",
        "admin123",
        "Admin User",
        "admin",
        reset=True,
    )
    print(f"Created User: {admin_id} (admin@example.com)")

    manager_id = _ensure_user(
        db,
        user_entity,
        membership_entity,
        password_service,
        tenant["id"],
        "manager@example.com",
        "manager123",
        "Manager User",
        "manager",
        reset=True,
    )
    print(f"Created User: {manager_id} (manager@example.com)")

    user_id = _ensure_user(
        db,
        user_entity,
        membership_entity,
        password_service,
        tenant["id"],
        "user@example.com",
        "user123",
        "Regular User",
        "user",
        reset=True,
    )
    print(f"Created User: {user_id} (user@example.com)")

    readonly_id = _ensure_user(
        db,
        user_entity,
        membership_entity,
        password_service,
        tenant["id"],
        "readonly@example.com",
        "readonly123",
        "Read Only User",
        "readonly",
        reset=True,
    )
    print(f"Created User: {readonly_id} (readonly@example.com)")

    db.close()

    print("\n" + "=" * 50)
    print("Seed complete! Test credentials:")
    print("=" * 50)
    print("\nAdmin:    admin@example.com / admin123")
    print("Manager:  manager@example.com / manager123")
    print("User:     user@example.com / user123")
    print("Readonly: readonly@example.com / readonly123")
    print(f"\nTenant ID (optional): {tenant['id']}")
    print("\nUI login:")
    print("  admin@example.com / admin123")
    print("  manager@example.com / manager123")
    print("  user@example.com / user123")
    print("  readonly@example.com / readonly123")
    print("\nTest login:")
    print('  curl -X POST http://localhost:8000/api/auth/login \\')
    print('    -H "Content-Type: application/json" \\')
    print('    -d \'{"email": "admin@example.com", "password": "admin123"}\'')


if __name__ == "__main__":
    main()
