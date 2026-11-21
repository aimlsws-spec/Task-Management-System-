"""projects: expected result, head, team, points; tasks: review stage

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-17 14:00:00
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql

revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('projects', sa.Column('expected_result', sa.Text(), nullable=True))
    op.add_column('projects', sa.Column('head_employee_id', sa.BigInteger(), nullable=True))
    op.add_column('projects', sa.Column('completed_at', mysql.DATETIME(fsp=6), nullable=True))
    op.add_column('projects', sa.Column('reviewed_by_user_id', sa.BigInteger(), nullable=True))
    op.add_column('projects', sa.Column('review_note', sa.Text(), nullable=True))
    op.create_foreign_key('fk_project_head', 'projects', 'employees', ['head_employee_id'], ['id'])
    op.create_foreign_key('fk_project_reviewer', 'projects', 'users', ['reviewed_by_user_id'], ['id'])
    op.add_column('tasks', sa.Column('review_stage', sa.String(length=12), nullable=True))
    op.create_table('project_members',
    sa.Column('project_id', sa.BigInteger(), nullable=False),
    sa.Column('employee_id', sa.BigInteger(), nullable=False),
    sa.ForeignKeyConstraint(['employee_id'], ['employees.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.PrimaryKeyConstraint('project_id', 'employee_id')
    )
    op.create_table('project_points',
    sa.Column('id', sa.BigInteger(), nullable=False),
    sa.Column('project_id', sa.BigInteger(), nullable=False),
    sa.Column('title', sa.String(length=200), nullable=False),
    sa.Column('details', sa.Text(), nullable=True),
    sa.Column('expected_result', sa.Text(), nullable=True),
    sa.Column('position', sa.Integer(), nullable=False),
    sa.Column('task_id', sa.BigInteger(), nullable=True),
    sa.Column('created_by_user_id', sa.BigInteger(), nullable=True),
    sa.Column('created_at', mysql.DATETIME(fsp=6), nullable=False),
    sa.ForeignKeyConstraint(['created_by_user_id'], ['users.id'], ),
    sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ),
    sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('task_id')
    )
    op.create_index('ix_point_project', 'project_points', ['project_id', 'position'], unique=False)


def downgrade() -> None:
    op.drop_table('project_points')
    op.drop_table('project_members')
    op.drop_column('tasks', 'review_stage')
    op.drop_constraint('fk_project_reviewer', 'projects', type_='foreignkey')
    op.drop_constraint('fk_project_head', 'projects', type_='foreignkey')
    op.drop_column('projects', 'review_note')
    op.drop_column('projects', 'reviewed_by_user_id')
    op.drop_column('projects', 'completed_at')
    op.drop_column('projects', 'head_employee_id')
    op.drop_column('projects', 'expected_result')
