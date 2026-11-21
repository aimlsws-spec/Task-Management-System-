"""Owner highest authority (rank 120) and full system access

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-21 17:35:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    conn = op.get_bind()
    # 1. Update owner role rank to 120 (rank is a MySQL 8 reserved keyword)
    conn.execute(sa.text("""
        UPDATE roles 
        SET `rank` = 120, 
            description = 'Highest business and system authority, full system access and all admin capabilities' 
        WHERE code = 'owner'
    """))

    # 2. Grant all permissions at 'organization' scope to owner role
    conn.execute(sa.text("""
        INSERT INTO role_permissions (role_id, permission_id, scope)
        SELECT r.id, p.id, 'organization'
        FROM roles r
        CROSS JOIN permissions p
        WHERE r.code = 'owner'
          AND NOT EXISTS (
              SELECT 1 FROM role_permissions rp 
              WHERE rp.role_id = r.id AND rp.permission_id = p.id
          )
    """))

    # 3. Bump rbac_seed_version in system_settings
    conn.execute(sa.text("""
        INSERT INTO system_settings (`key`, `value`, `updated_at`)
        VALUES ('rbac_seed_version', '5', UTC_TIMESTAMP())
        ON DUPLICATE KEY UPDATE `value` = '5', `updated_at` = UTC_TIMESTAMP()
    """))


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(sa.text("UPDATE roles SET `rank` = 100 WHERE code = 'owner'"))
    conn.execute(sa.text("""
        INSERT INTO system_settings (`key`, `value`, `updated_at`)
        VALUES ('rbac_seed_version', '4', UTC_TIMESTAMP())
        ON DUPLICATE KEY UPDATE `value` = '4', `updated_at` = UTC_TIMESTAMP()
    """))
