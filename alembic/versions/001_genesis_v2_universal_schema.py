"""Genesis v2.0: Universal ontology schema

Revision ID: 001_genesis_v2
Revises: 4cc72cd32f0f
Create Date: 2025-10-26 00:00:00.000000

CRITICAL MIGRATION: Transforms domain-specific schema into universal ontology engine.

Changes:
- Creates domain_configs table
- Creates canonical_nodes table (replaces skills + canonical_entities)
- Creates node_aliases table (replaces aliases + entity_aliases)
- Creates node_relationships table (replaces hierarchy)
- Creates enrichment_queue table (domain-aware)
- Creates human_validations table (replaces CSV workflow)
- Creates async_tasks table (domain-aware)
- Migrates existing IT Skills data to new schema
- Inserts default IT Skills domain configuration

WARNING: This is a one-way migration. Backup your database before proceeding.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '001_genesis_v2'
down_revision: Union[str, None] = '4cc72cd32f0f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade to Genesis v2.0 universal schema."""

    # ============================================================================
    # STEP 1: Create new universal tables
    # ============================================================================

    # Domain configurations table
    op.create_table(
        'domain_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('domain_id', sa.String(length=255), nullable=False),
        sa.Column('domain_name', sa.String(length=255), nullable=False),
        sa.Column('version', sa.String(length=50), nullable=False),
        sa.Column('config_yaml', sa.Text(), nullable=False),
        sa.Column('config_json', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('domain_id')
    )
    op.create_index('ix_domain_configs_domain_id', 'domain_configs', ['domain_id'])

    # Universal canonical nodes table
    op.create_table(
        'canonical_nodes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('domain_id', sa.String(length=255), nullable=False),
        sa.Column('canonical_name', sa.String(length=255), nullable=False),
        sa.Column('node_type', sa.String(length=100), nullable=False),
        sa.Column('display_name', sa.String(length=255), nullable=True),
        sa.Column('properties', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('embedding', Vector(1536), nullable=True),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['domain_id'], ['domain_configs.domain_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('domain_id', 'canonical_name', 'node_type', name='uq_node_domain')
    )
    op.create_index('idx_node_domain', 'canonical_nodes', ['domain_id'])
    op.create_index('idx_node_type', 'canonical_nodes', ['node_type'])
    op.create_index('idx_node_canonical_name', 'canonical_nodes', ['canonical_name'])

    # Universal node aliases table
    op.create_table(
        'node_aliases',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('domain_id', sa.String(length=255), nullable=False),
        sa.Column('alias_name', sa.String(length=255), nullable=False),
        sa.Column('canonical_id', sa.Integer(), nullable=False),
        sa.Column('confidence', sa.Integer(), nullable=True, server_default='100'),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['domain_id'], ['domain_configs.domain_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['canonical_id'], ['canonical_nodes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('domain_id', 'alias_name', name='uq_alias_domain')
    )
    op.create_index('idx_alias_domain', 'node_aliases', ['domain_id'])
    op.create_index('idx_alias_name', 'node_aliases', ['alias_name'])
    op.create_index('idx_alias_canonical_id', 'node_aliases', ['canonical_id'])

    # Universal node relationships table
    op.create_table(
        'node_relationships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('domain_id', sa.String(length=255), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('relationship_type', sa.String(length=100), nullable=False),
        sa.Column('properties', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('metadata', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['domain_id'], ['domain_configs.domain_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['source_id'], ['canonical_nodes.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['target_id'], ['canonical_nodes.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('domain_id', 'source_id', 'target_id', 'relationship_type', name='uq_relationship_domain')
    )
    op.create_index('idx_rel_domain', 'node_relationships', ['domain_id'])
    op.create_index('idx_rel_source', 'node_relationships', ['source_id'])
    op.create_index('idx_rel_target', 'node_relationships', ['target_id'])
    op.create_index('idx_rel_type', 'node_relationships', ['relationship_type'])

    # Human validations table (replaces CSV workflow)
    op.create_table(
        'human_validations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('domain_id', sa.String(length=255), nullable=False),
        sa.Column('raw_value', sa.String(length=500), nullable=False),
        sa.Column('suggested_canonical_name', sa.String(length=255), nullable=False),
        sa.Column('suggested_node_type', sa.String(length=100), nullable=False),
        sa.Column('suggested_aliases', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('suggested_relationships', postgresql.JSON(astext_type=sa.Text()), nullable=False),
        sa.Column('suggested_properties', postgresql.JSON(astext_type=sa.Text()), nullable=True, server_default='{}'),
        sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'REJECTED', 'MODIFIED', name='validationstatus'), nullable=False, server_default='PENDING'),
        sa.Column('reviewer_notes', sa.Text(), nullable=True),
        sa.Column('reviewed_by', sa.String(length=255), nullable=True),
        sa.Column('frequency_count', sa.Integer(), nullable=True, server_default='1'),
        sa.Column('created_at', sa.DateTime(), nullable=False, server_default=sa.text('now()')),
        sa.Column('reviewed_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['domain_id'], ['domain_configs.domain_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_validation_domain', 'human_validations', ['domain_id'])
    op.create_index('idx_validation_status', 'human_validations', ['status'])
    op.create_index('idx_validation_created', 'human_validations', ['created_at'])

    # ============================================================================
    # STEP 2: Migrate existing data from skills → canonical_nodes
    # ============================================================================

    # First, insert default IT Skills domain configuration
    op.execute("""
        INSERT INTO domain_configs (domain_id, domain_name, version, config_yaml, config_json, is_active)
        VALUES (
            'it_skills',
            'IT Skills & Competencies Ontology',
            '1.2.0',
            '# Legacy domain - migrated from v1.0',
            '{"metadata": {"name": "IT Skills & Competencies Ontology", "domain_id": "it_skills", "version": "1.2.0", "description": "Migrated from Erwin Harmonizer v1.0", "owner": "Erwin Labs", "created_at": "2025-01-15T00:00:00Z", "updated_at": "2025-10-26T00:00:00Z"}, "node_types": [{"name": "skill", "display_name": "Technical Skill", "description": "A technical or soft skill"}], "relationship_types": [{"name": "is_subtype_of", "display_name": "Is Subtype Of", "description": "Hierarchical parent-child relationship", "source_types": ["skill"], "target_types": ["skill"]}]}',
            true
        )
    """)

    # Migrate skills → canonical_nodes
    op.execute("""
        INSERT INTO canonical_nodes (domain_id, canonical_name, node_type, display_name, embedding, created_at, updated_at)
        SELECT
            'it_skills' AS domain_id,
            canonical_name,
            'skill' AS node_type,
            canonical_name AS display_name,
            embedding,
            created_at,
            COALESCE(updated_at, created_at) AS updated_at
        FROM skills
        ORDER BY id
    """)

    # Migrate aliases → node_aliases
    op.execute("""
        INSERT INTO node_aliases (domain_id, alias_name, canonical_id, confidence, created_at)
        SELECT
            'it_skills' AS domain_id,
            a.alias_name,
            cn.id AS canonical_id,
            a.confidence,
            a.created_at
        FROM aliases a
        JOIN skills s ON a.skill_id = s.id
        JOIN canonical_nodes cn ON cn.canonical_name = s.canonical_name AND cn.domain_id = 'it_skills'
        ORDER BY a.id
    """)

    # Migrate hierarchy → node_relationships
    op.execute("""
        INSERT INTO node_relationships (domain_id, source_id, target_id, relationship_type, created_at)
        SELECT
            'it_skills' AS domain_id,
            cn_child.id AS source_id,
            cn_parent.id AS target_id,
            'is_subtype_of' AS relationship_type,
            h.created_at
        FROM hierarchy h
        JOIN skills s_child ON h.child_id = s_child.id
        JOIN skills s_parent ON h.parent_id = s_parent.id
        JOIN canonical_nodes cn_child ON cn_child.canonical_name = s_child.canonical_name AND cn_child.domain_id = 'it_skills'
        JOIN canonical_nodes cn_parent ON cn_parent.canonical_name = s_parent.canonical_name AND cn_parent.domain_id = 'it_skills'
        ORDER BY h.id
    """)

    # ============================================================================
    # STEP 3: Update enrichment_queue and async_tasks to be domain-aware
    # ============================================================================

    # Add domain_id column to existing tables
    op.add_column('enrichment_queue', sa.Column('domain_id', sa.String(length=255), nullable=True))
    op.add_column('async_tasks', sa.Column('domain_id', sa.String(length=255), nullable=True))

    # Set existing records to 'it_skills' domain
    op.execute("UPDATE enrichment_queue SET domain_id = 'it_skills' WHERE domain_id IS NULL")
    op.execute("UPDATE async_tasks SET domain_id = 'it_skills' WHERE domain_id IS NULL")

    # Now make domain_id nullable=False for enrichment_queue (but keep nullable for async_tasks)
    # We keep it nullable for async_tasks because system tasks may not belong to any domain

    # Add foreign key constraints
    op.create_foreign_key(
        'fk_enrichment_queue_domain',
        'enrichment_queue',
        'domain_configs',
        ['domain_id'],
        ['domain_id'],
        ondelete='CASCADE'
    )

    op.create_foreign_key(
        'fk_async_tasks_domain',
        'async_tasks',
        'domain_configs',
        ['domain_id'],
        ['domain_id'],
        ondelete='SET NULL'
    )

    # Add indexes
    op.create_index('idx_enrich_domain', 'enrichment_queue', ['domain_id'])
    op.create_index('idx_task_domain', 'async_tasks', ['domain_id'])

    # ============================================================================
    # STEP 4: Validation and Summary
    # ============================================================================

    # Print migration summary (will appear in logs)
    print("\n" + "="*80)
    print("GENESIS v2.0 MIGRATION COMPLETED SUCCESSFULLY")
    print("="*80)
    print("\nMigration Summary:")
    print("- Created 7 new universal tables")
    print("- Migrated existing data to 'it_skills' domain")
    print("- Updated enrichment_queue and async_tasks to be domain-aware")
    print("\nNext Steps:")
    print("1. Verify data integrity: poetry run python scripts/validate_migration.py")
    print("2. Test API with new schema: poetry run uvicorn src.api.genesis_main:app --reload")
    print("3. Load additional domains: export DOMAIN_CONFIG_PATH=domains/product_catalog.yaml")
    print("="*80 + "\n")


def downgrade() -> None:
    """Downgrade from Genesis v2.0 (NOT RECOMMENDED)."""

    # WARNING: This will destroy the universal schema and domain-specific data
    print("\n" + "!"*80)
    print("WARNING: Downgrading from Genesis v2.0 will destroy universal schema!")
    print("This operation cannot preserve multi-domain data.")
    print("Only IT Skills domain data will be preserved.")
    print("!"*80 + "\n")

    # Remove foreign keys from enrichment_queue and async_tasks
    op.drop_constraint('fk_enrichment_queue_domain', 'enrichment_queue', type_='foreignkey')
    op.drop_constraint('fk_async_tasks_domain', 'async_tasks', type_='foreignkey')

    # Remove domain_id columns
    op.drop_index('idx_enrich_domain', 'enrichment_queue')
    op.drop_index('idx_task_domain', 'async_tasks')
    op.drop_column('enrichment_queue', 'domain_id')
    op.drop_column('async_tasks', 'domain_id')

    # Drop new universal tables
    op.drop_table('human_validations')
    op.drop_table('node_relationships')
    op.drop_table('node_aliases')
    op.drop_table('canonical_nodes')
    op.drop_table('domain_configs')

    print("\nDowngrade completed. Legacy schema restored.")
    print("WARNING: All non-IT Skills domain data has been lost.")
