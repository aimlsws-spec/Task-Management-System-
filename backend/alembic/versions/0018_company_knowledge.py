"""Company knowledge and entity memory for AI recommendations

Revision ID: 0018
Revises: 0017
Create Date: 2026-11-23 15:15:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0018'
down_revision = '0017'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()

    conn.execute(sa.text("""
        CREATE TABLE IF NOT EXISTS company_knowledge (
            id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
            company_id BIGINT NOT NULL,
            entity_key VARCHAR(100) NOT NULL,
            entity_name VARCHAR(150) NOT NULL,
            entity_type VARCHAR(50) NOT NULL DEFAULT 'product',
            description TEXT NOT NULL,
            tech_stack VARCHAR(255) NULL,
            default_notes TEXT NULL,
            created_by_user_id BIGINT NULL,
            created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
            UNIQUE KEY uq_company_entity (company_id, entity_key),
            KEY ix_comp_knowledge_comp (company_id),
            CONSTRAINT fk_comp_knowledge_comp FOREIGN KEY (company_id) REFERENCES companies(id) ON DELETE CASCADE,
            CONSTRAINT fk_comp_knowledge_user FOREIGN KEY (created_by_user_id) REFERENCES users(id) ON DELETE SET NULL
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("DROP TABLE IF EXISTS company_knowledge;"))
