"""
Data migration script: SQLite → PostgreSQL

Migrates all data from ontology.db and entity_resolver.db to PostgreSQL.
"""

import sqlite3
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.db.postgres_connection import get_db
from src.db.postgres_models import (
    Alias,
    CanonicalEntity,
    EnrichmentQueue,
    EnrichmentStatus,
    EntityAlias,
    EntityType,
    Hierarchy,
    Skill,
)


def migrate_ontology_data():
    """Migrate skills, aliases, and hierarchy from ontology.db."""
    print("=" * 80)
    print("MIGRATING ONTOLOGY DATA (ontology.db → PostgreSQL)")
    print("=" * 80)

    sqlite_path = Path(__file__).parent.parent / "data" / "databases" / "ontology.db"
    if not sqlite_path.exists():
        print(f"ERROR: {sqlite_path} not found")
        return False

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    with get_db() as db:
        # 1. Migrate Skills
        print("\n[1/3] Migrating skills...")
        sqlite_cursor.execute("SELECT id, canonical_name, created_at FROM skills")
        skills_data = sqlite_cursor.fetchall()

        skill_id_map = {}  # Map old SQLite IDs to new Postgres IDs
        for row in skills_data:
            skill = Skill(
                id=row["id"],
                canonical_name=row["canonical_name"],
                created_at=row["created_at"],
            )
            db.add(skill)
            skill_id_map[row["id"]] = skill

        db.flush()
        print(f"✓ Migrated {len(skills_data)} skills")

        # 2. Migrate Aliases
        print("\n[2/3] Migrating aliases...")
        sqlite_cursor.execute("SELECT alias_name, skill_id FROM aliases")
        aliases_data = sqlite_cursor.fetchall()

        for row in aliases_data:
            alias = Alias(alias_name=row["alias_name"], skill_id=row["skill_id"])
            db.add(alias)

        print(f"✓ Migrated {len(aliases_data)} aliases")

        # 3. Migrate Hierarchy
        print("\n[3/3] Migrating hierarchy relationships...")
        sqlite_cursor.execute("SELECT child_id, parent_id FROM hierarchy")
        hierarchy_data = sqlite_cursor.fetchall()

        for row in hierarchy_data:
            relation = Hierarchy(child_id=row["child_id"], parent_id=row["parent_id"])
            db.add(relation)

        print(f"✓ Migrated {len(hierarchy_data)} hierarchy relationships")

        db.commit()

    sqlite_conn.close()
    print(f"\n{'=' * 80}")
    print("✓ ONTOLOGY MIGRATION COMPLETE")
    print(f"{'=' * 80}\n")
    return True


def migrate_entity_resolver_data():
    """Migrate entities, aliases, and enrichment queue from entity_resolver.db."""
    print("=" * 80)
    print("MIGRATING ENTITY RESOLVER DATA (entity_resolver.db → PostgreSQL)")
    print("=" * 80)

    sqlite_path = Path(__file__).parent.parent / "data" / "databases" / "entity_resolver.db"
    if not sqlite_path.exists():
        print(f"ERROR: {sqlite_path} not found")
        return False

    sqlite_conn = sqlite3.connect(sqlite_path)
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cursor = sqlite_conn.cursor()

    with get_db() as db:
        # 1. Migrate Canonical Entities
        print("\n[1/3] Migrating canonical entities...")
        sqlite_cursor.execute(
            "SELECT id, canonical_id, display_name, entity_type, metadata "
            "FROM canonical_entities"
        )
        entities_data = sqlite_cursor.fetchall()

        entity_id_map = {}
        for row in entities_data:
            entity = CanonicalEntity(
                id=row["id"],
                canonical_id=row["canonical_id"],
                display_name=row["display_name"],
                entity_type=EntityType(row["entity_type"]),
                entity_metadata=row["metadata"],  # JSON field
            )
            db.add(entity)
            entity_id_map[row["id"]] = entity

        db.flush()
        print(f"✓ Migrated {len(entities_data)} entities")

        # 2. Migrate Entity Aliases
        print("\n[2/3] Migrating entity aliases...")
        sqlite_cursor.execute("SELECT alias_name, canonical_id FROM entity_aliases")
        aliases_data = sqlite_cursor.fetchall()

        for row in aliases_data:
            alias = EntityAlias(alias_name=row["alias_name"], canonical_id=row["canonical_id"])
            db.add(alias)

        print(f"✓ Migrated {len(aliases_data)} entity aliases")

        # 3. Migrate Enrichment Queue
        print("\n[3/3] Migrating enrichment queue...")
        sqlite_cursor.execute(
            "SELECT canonical_id, entity_type, status, created_at, processed_at, error_message "
            "FROM enrichment_queue"
        )
        queue_data = sqlite_cursor.fetchall()

        for row in queue_data:
            queue_item = EnrichmentQueue(
                canonical_id=row["canonical_id"],
                entity_type=EntityType(row["entity_type"]),
                status=EnrichmentStatus(row["status"]),
                created_at=row["created_at"],
                processed_at=row["processed_at"],
                error_message=row["error_message"],
            )
            db.add(queue_item)

        print(f"✓ Migrated {len(queue_data)} enrichment queue items")

        db.commit()

    sqlite_conn.close()
    print(f"\n{'=' * 80}")
    print("✓ ENTITY RESOLVER MIGRATION COMPLETE")
    print(f"{'=' * 80}\n")
    return True


def verify_migration():
    """Verify data counts match between SQLite and PostgreSQL."""
    print("=" * 80)
    print("VERIFYING MIGRATION")
    print("=" * 80)

    sqlite_ontology = Path(__file__).parent.parent / "data" / "databases" / "ontology.db"
    sqlite_entity = Path(__file__).parent.parent / "data" / "databases" / "entity_resolver.db"

    # Count SQLite records
    ontology_conn = sqlite3.connect(sqlite_ontology)
    entity_conn = sqlite3.connect(sqlite_entity)

    sqlite_counts = {
        "skills": ontology_conn.execute("SELECT COUNT(*) FROM skills").fetchone()[0],
        "aliases": ontology_conn.execute("SELECT COUNT(*) FROM aliases").fetchone()[0],
        "hierarchy": ontology_conn.execute("SELECT COUNT(*) FROM hierarchy").fetchone()[0],
        "entities": entity_conn.execute("SELECT COUNT(*) FROM canonical_entities").fetchone()[0],
        "entity_aliases": entity_conn.execute("SELECT COUNT(*) FROM entity_aliases").fetchone()[0],
        "enrichment_queue": entity_conn.execute("SELECT COUNT(*) FROM enrichment_queue").fetchone()[
            0
        ],
    }

    ontology_conn.close()
    entity_conn.close()

    # Count PostgreSQL records
    with get_db() as db:
        postgres_counts = {
            "skills": db.query(Skill).count(),
            "aliases": db.query(Alias).count(),
            "hierarchy": db.query(Hierarchy).count(),
            "entities": db.query(CanonicalEntity).count(),
            "entity_aliases": db.query(EntityAlias).count(),
            "enrichment_queue": db.query(EnrichmentQueue).count(),
        }

    # Compare counts
    print("\nRecord counts comparison:")
    print(f"{'Table':<20} {'SQLite':<12} {'PostgreSQL':<12} {'Status':<10}")
    print("-" * 60)

    all_match = True
    for table, sqlite_count in sqlite_counts.items():
        postgres_count = postgres_counts[table]
        match = "✓ OK" if sqlite_count == postgres_count else "✗ MISMATCH"
        if sqlite_count != postgres_count:
            all_match = False
        print(f"{table:<20} {sqlite_count:<12} {postgres_count:<12} {match:<10}")

    print("=" * 80)
    if all_match:
        print("✓ ALL DATA SUCCESSFULLY MIGRATED")
    else:
        print("✗ MIGRATION ERRORS DETECTED - REVIEW ABOVE")
    print("=" * 80)

    return all_match


def main():
    """Run full migration."""
    print("\n" + "=" * 80)
    print(" " * 20 + "SQLITE → POSTGRESQL MIGRATION")
    print("=" * 80 + "\n")

    try:
        # Step 1: Migrate ontology data
        if not migrate_ontology_data():
            print("✗ Ontology migration failed")
            return False

        # Step 2: Migrate entity resolver data
        if not migrate_entity_resolver_data():
            print("✗ Entity resolver migration failed")
            return False

        # Step 3: Verify
        if not verify_migration():
            print("✗ Verification failed")
            return False

        print("\n" + "=" * 80)
        print(" " * 25 + "MIGRATION SUCCESSFUL")
        print(" " * 15 + "PostgreSQL is now the source of truth")
        print("=" * 80 + "\n")
        return True

    except Exception as e:
        print(f"\n✗ MIGRATION FAILED: {e}")
        import traceback

        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
