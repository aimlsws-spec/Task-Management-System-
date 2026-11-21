"""admin-registered role emails (owner / ceo / ... by email)

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-17 11:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('role_invites',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('role_id', sa.BigInteger(), nullable=False),
    sa.Column('created_by', sa.BigInteger(), nullable=False),
    sa.Column('created_at', mysql.DATETIME(fsp=6), nullable=False),
    sa.Column('claimed_user_id', sa.BigInteger(), nullable=True),
    sa.Column('claimed_at', mysql.DATETIME(fsp=6), nullable=True),
    sa.ForeignKeyConstraint(['claimed_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['created_by'], ['users.id'], ),
    sa.ForeignKeyConstraint(['role_id'], ['roles.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('email')
    )


def downgrade() -> None:
    op.drop_table('role_invites')
