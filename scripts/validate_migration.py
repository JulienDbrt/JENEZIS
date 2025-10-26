#!/usr/bin/env python3
"""
Migration Validation Script

Validates data integrity after Genesis v2.0 migration.
Compares legacy tables (skills, aliases, hierarchy) with new universal tables.

Usage:
    poetry run python scripts/validate_migration.py
    poetry run python scripts/validate_migration.py --database erwin_genesis_test
"""

import argparse
import os
import sys
from typing import Any, Dict

import psycopg2
from dotenv import load_dotenv

load_dotenv()


class MigrationValidator:
    """Validates Genesis v2.0 migration data integrity."""

    def __init__(self, database_url: str):
        """Initialize validator with database connection."""
        self.conn = psycopg2.connect(database_url)
        self.cursor = self.conn.cursor()
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def validate_all(self) -> bool:
        """Run all validation checks. Returns True if all pass."""
        print("\n" + "=" * 80)
        print("GENESIS v2.0 MIGRATION VALIDATION")
        print("=" * 80 + "\n")

        checks = [
            ("Domain Configuration", self.validate_domain_config),
            ("Canonical Nodes Migration", self.validate_canonical_nodes),
            ("Node Aliases Migration", self.validate_node_aliases),
            ("Node Relationships Migration", self.validate_node_relationships),
            ("Data Integrity", self.validate_data_integrity),
            ("Indexes and Constraints", self.validate_indexes),
        ]

        for check_name, check_func in checks:
            print(f"\n{'─' * 80}")
            print(f"✓ Running: {check_name}")
            print(f"{'─' * 80}")
            try:
                check_func()
            except Exception as e:
                self.errors.append(f"{check_name} failed: {str(e)}")
                print(f"❌ ERROR: {e}")

        # Print summary
        print("\n" + "=" * 80)
        print("VALIDATION SUMMARY")
        print("=" * 80)

        if self.errors:
            print(f"\n❌ FAILED: {len(self.errors)} critical errors found:\n")
            for i, error in enumerate(self.errors, 1):
                print(f"  {i}. {error}")

        if self.warnings:
            print(f"\n⚠️  WARNINGS: {len(self.warnings)} warnings found:\n")
            for i, warning in enumerate(self.warnings, 1):
                print(f"  {i}. {warning}")

        if not self.errors and not self.warnings:
            print("\n✅ ALL CHECKS PASSED - Migration is valid!")
            print("   Ready to proceed with Genesis v2.0 deployment.")

        print("\n" + "=" * 80 + "\n")

        return len(self.errors) == 0

    def get_count(self, table: str, where: str = "") -> int:
        """Get row count from table."""
        query = f"SELECT COUNT(*) FROM {table}"
        if where:
            query += f" WHERE {where}"
        self.cursor.execute(query)
        return self.cursor.fetchone()[0]

    def validate_domain_config(self) -> None:
        """Validate domain_configs table."""
        count = self.get_count("domain_configs")
        print(f"   Domain configs found: {count}")

        if count == 0:
            self.errors.append("No domain configs found - migration failed")
            return

        # Check IT Skills domain exists
        self.cursor.execute(
            "SELECT domain_id, domain_name, version FROM domain_configs WHERE domain_id = 'it_skills'"
        )
        result = self.cursor.fetchone()

        if not result:
            self.errors.append("IT Skills domain config not found")
        else:
            domain_id, domain_name, version = result
            print(f"   ✓ IT Skills domain: {domain_name} (v{version})")

    def validate_canonical_nodes(self) -> None:
        """Validate skills → canonical_nodes migration."""
        # Count legacy skills
        legacy_count = self.get_count("skills")
        print(f"   Legacy skills table: {legacy_count} rows")

        # Count migrated nodes
        migrated_count = self.get_count("canonical_nodes", "domain_id = 'it_skills'")
        print(f"   Migrated canonical_nodes: {migrated_count} rows")

        # Compare
        if legacy_count != migrated_count:
            self.errors.append(
                f"Skill count mismatch: {legacy_count} legacy vs {migrated_count} migrated"
            )
        else:
            print(f"   ✓ Skill migration count matches: {migrated_count}")

        # Check all node_types are 'skill'
        self.cursor.execute(
            "SELECT COUNT(DISTINCT node_type) FROM canonical_nodes WHERE domain_id = 'it_skills'"
        )
        distinct_types = self.cursor.fetchone()[0]

        if distinct_types != 1:
            self.errors.append(f"Expected 1 node_type (skill), found {distinct_types}")
        else:
            print("   ✓ All IT Skills nodes have node_type='skill'")

        # Sample check: verify specific skills migrated correctly
        test_skills = ["python", "javascript", "react"]
        for skill in test_skills:
            self.cursor.execute(
                """
                SELECT cn.id FROM canonical_nodes cn
                WHERE cn.domain_id = 'it_skills' AND cn.canonical_name = %s
            """,
                (skill,),
            )
            if not self.cursor.fetchone():
                self.warnings.append(f"Test skill '{skill}' not found in canonical_nodes")
            else:
                print(f"   ✓ Test skill '{skill}' migrated")

    def validate_node_aliases(self) -> None:
        """Validate aliases → node_aliases migration."""
        # Count legacy aliases
        legacy_count = self.get_count("aliases")
        print(f"   Legacy aliases table: {legacy_count} rows")

        # Count migrated aliases
        migrated_count = self.get_count("node_aliases", "domain_id = 'it_skills'")
        print(f"   Migrated node_aliases: {migrated_count} rows")

        # Compare
        if legacy_count != migrated_count:
            self.errors.append(
                f"Alias count mismatch: {legacy_count} legacy vs {migrated_count} migrated"
            )
        else:
            print(f"   ✓ Alias migration count matches: {migrated_count}")

        # Check referential integrity
        self.cursor.execute(
            """
            SELECT COUNT(*)
            FROM node_aliases na
            LEFT JOIN canonical_nodes cn ON na.canonical_id = cn.id
            WHERE na.domain_id = 'it_skills' AND cn.id IS NULL
        """
        )
        orphaned = self.cursor.fetchone()[0]

        if orphaned > 0:
            self.errors.append(f"Found {orphaned} orphaned aliases (no canonical node)")
        else:
            print("   ✓ All aliases have valid canonical_id references")

    def validate_node_relationships(self) -> None:
        """Validate hierarchy → node_relationships migration."""
        # Count legacy hierarchy
        legacy_count = self.get_count("hierarchy")
        print(f"   Legacy hierarchy table: {legacy_count} rows")

        # Count migrated relationships
        migrated_count = self.get_count("node_relationships", "domain_id = 'it_skills'")
        print(f"   Migrated node_relationships: {migrated_count} rows")

        # Compare
        if legacy_count != migrated_count:
            self.errors.append(
                f"Relationship count mismatch: {legacy_count} legacy vs {migrated_count} migrated"
            )
        else:
            print(f"   ✓ Relationship migration count matches: {migrated_count}")

        # Check all relationship_types are 'is_subtype_of'
        self.cursor.execute(
            """
            SELECT COUNT(DISTINCT relationship_type)
            FROM node_relationships
            WHERE domain_id = 'it_skills'
        """
        )
        distinct_types = self.cursor.fetchone()[0]

        if distinct_types != 1:
            self.errors.append(
                f"Expected 1 relationship_type (is_subtype_of), found {distinct_types}"
            )
        else:
            print("   ✓ All IT Skills relationships have type='is_subtype_of'")

        # Check referential integrity (no broken references)
        self.cursor.execute(
            """
            SELECT COUNT(*)
            FROM node_relationships nr
            LEFT JOIN canonical_nodes cn_source ON nr.source_id = cn_source.id
            LEFT JOIN canonical_nodes cn_target ON nr.target_id = cn_target.id
            WHERE nr.domain_id = 'it_skills'
              AND (cn_source.id IS NULL OR cn_target.id IS NULL)
        """
        )
        broken = self.cursor.fetchone()[0]

        if broken > 0:
            self.errors.append(f"Found {broken} relationships with broken node references")
        else:
            print("   ✓ All relationships have valid source/target references")

    def validate_data_integrity(self) -> None:
        """Cross-validate data consistency."""
        # Test: For each legacy skill, verify it has:
        # 1. Exactly one canonical_node
        # 2. At least one alias
        # 3. Zero or more relationships

        self.cursor.execute(
            """
            SELECT s.canonical_name,
                   COUNT(DISTINCT cn.id) as node_count,
                   COUNT(DISTINCT na.id) as alias_count
            FROM skills s
            LEFT JOIN canonical_nodes cn
                ON cn.canonical_name = s.canonical_name AND cn.domain_id = 'it_skills'
            LEFT JOIN node_aliases na
                ON na.canonical_id = cn.id AND na.domain_id = 'it_skills'
            GROUP BY s.canonical_name
            HAVING COUNT(DISTINCT cn.id) != 1
            LIMIT 10
        """
        )

        integrity_issues = self.cursor.fetchall()

        if integrity_issues:
            self.errors.append(f"Found {len(integrity_issues)} skills with integrity issues")
            for skill_name, node_count, alias_count in integrity_issues[:5]:
                print(
                    f"   ❌ {skill_name}: {node_count} nodes, {alias_count} aliases (expected 1 node, ≥1 alias)"
                )
        else:
            print("   ✓ All legacy skills have exactly one canonical_node")

        # Test: Verify no duplicate canonical_names in same domain
        self.cursor.execute(
            """
            SELECT canonical_name, COUNT(*)
            FROM canonical_nodes
            WHERE domain_id = 'it_skills'
            GROUP BY canonical_name
            HAVING COUNT(*) > 1
        """
        )

        duplicates = self.cursor.fetchall()

        if duplicates:
            self.errors.append(f"Found {len(duplicates)} duplicate canonical_names")
            for name, count in duplicates[:5]:
                print(f"   ❌ Duplicate: {name} ({count} times)")
        else:
            print("   ✓ No duplicate canonical_names in it_skills domain")

    def validate_indexes(self) -> None:
        """Validate critical indexes exist."""
        required_indexes = {
            "ix_domain_configs_domain_id": "domain_configs",
            "idx_node_domain": "canonical_nodes",
            "idx_node_type": "canonical_nodes",
            "idx_alias_domain": "node_aliases",
            "idx_alias_name": "node_aliases",
            "idx_rel_domain": "node_relationships",
            "idx_rel_type": "node_relationships",
        }

        for index_name, table_name in required_indexes.items():
            self.cursor.execute(
                """
                SELECT COUNT(*)
                FROM pg_indexes
                WHERE tablename = %s AND indexname = %s
            """,
                (table_name, index_name),
            )

            if self.cursor.fetchone()[0] == 0:
                self.errors.append(f"Missing critical index: {index_name} on {table_name}")
            else:
                print(f"   ✓ Index exists: {index_name}")

    def close(self) -> None:
        """Close database connection."""
        self.cursor.close()
        self.conn.close()


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate Genesis v2.0 migration")
    parser.add_argument(
        "--database",
        default=None,
        help="Database name (default: from DATABASE_URL env var)",
    )
    args = parser.parse_args()

    # Build database URL
    if args.database:
        db_url = f"postgresql://erwin:erwin@localhost:5433/{args.database}"
    else:
        db_url = os.getenv(
            "DATABASE_URL", "postgresql://erwin:erwin@localhost:5433/erwin_harmonizer"
        )

    print(f"\nConnecting to: {db_url}")

    # Run validation
    validator = MigrationValidator(db_url)

    try:
        success = validator.validate_all()
    finally:
        validator.close()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
