"""department head ownership of tasks

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-16 20:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('task_head_ownership',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('task_id', sa.BigInteger(), nullable=False),
    sa.Column('employee_id', sa.BigInteger(), nullable=False),
    sa.Column('user_id', sa.BigInteger(), nullable=False),
    sa.Column('note', sa.Text(), nullable=True),
    sa.Column('created_at', mysql.DATETIME(fsp=6), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('task_id', 'employee_id', name='uq_task_head_owner')
    )
    op.create_index('ix_task_head_ownership_task_id', 'task_head_ownership', ['task_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_task_head_ownership_task_id', table_name='task_head_ownership')
    op.drop_table('task_head_ownership')
