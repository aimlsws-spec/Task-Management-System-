"""Project points, blocker escalation, project assignee, QA bug sheet url

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-19 14:45:00
"""
from alembic import op
import sqlalchemy as sa

revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. QA bug sheet URL in task reverts
    op.add_column('task_reverts', sa.Column('bug_sheet_url', sa.String(500), nullable=True))

    # 2. Project assignee and progress
    op.add_column('projects', sa.Column('assignee_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_project_assignee', 'projects', 'employees', ['assignee_id'], ['id'])
    op.add_column('projects', sa.Column('progress_pct', sa.SmallInteger(), nullable=False, server_default='0'))

    # 3. Project point completion status
    op.add_column('project_points', sa.Column('is_done', sa.Boolean(), nullable=False, server_default=sa.text('0')))

    # 4. Blocker escalation to leadership flag
    op.add_column('task_blockers', sa.Column('escalated_to_leadership', sa.Boolean(), nullable=False, server_default=sa.text('0')))


def downgrade() -> None:
    op.drop_column('task_blockers', 'escalated_to_leadership')
    op.drop_column('project_points', 'is_done')
    op.drop_column('projects', 'progress_pct')
    op.drop_constraint('fk_project_assignee', 'projects', type_='foreignkey')
    op.drop_column('projects', 'assignee_id')
    op.drop_column('task_reverts', 'bug_sheet_url')
