"""QA and head per task, QA per project (ADR 006)

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-18 10:00:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('qa_employee_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_project_qa', 'projects', 'employees', ['qa_employee_id'], ['id'])
    op.add_column('tasks', sa.Column('head_employee_id', sa.BigInteger(), nullable=True))
    op.add_column('tasks', sa.Column('qa_employee_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_task_head', 'tasks', 'employees', ['head_employee_id'], ['id'])
    op.create_foreign_key('fk_task_qa', 'tasks', 'employees', ['qa_employee_id'], ['id'])


def downgrade() -> None:
    op.drop_constraint('fk_task_qa', 'tasks', type_='foreignkey')
    op.drop_constraint('fk_task_head', 'tasks', type_='foreignkey')
    op.drop_column('tasks', 'qa_employee_id')
    op.drop_column('tasks', 'head_employee_id')
    op.drop_constraint('fk_project_qa', 'projects', type_='foreignkey')
    op.drop_column('projects', 'qa_employee_id')
