"""One-time-code sign-in table; replace basic EMP-0001 style employee codes (ADR 008)

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-18 16:00:00
"""
import secrets

from alembic import op
import sqlalchemy as sa

revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None

_L, _D = "ABCDEFGHJKLMNPQRSTUVWXYZ", "23456789"


def _code() -> str:
    chars = [secrets.choice(_L) for _ in range(3)] + [secrets.choice(_D) for _ in range(3)]
    secrets.SystemRandom().shuffle(chars)
    return "SW-" + "".join(chars)


def upgrade() -> None:
    op.add_column('departments', sa.Column('qa_employee_id', sa.BigInteger(), nullable=True))
    op.create_foreign_key('fk_dept_qa', 'departments', 'employees', ['qa_employee_id'], ['id'])
    op.create_table(
        'login_otps',
        sa.Column('id', sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.BigInteger(), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('challenge_hash', sa.String(64), nullable=False, unique=True),
        sa.Column('code_hash', sa.String(64), nullable=False),
        sa.Column('purpose', sa.String(10), nullable=False, server_default='login'),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('attempts', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('sends', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('last_sent_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )
    op.create_index('ix_login_otps_user_id', 'login_otps', ['user_id'])
    # Existing sequential codes (EMP-0001 ...) become random letter+digit codes.
    bind = op.get_bind()
    taken = {r[0] for r in bind.execute(sa.text("SELECT employee_code FROM employees"))}
    for emp_id, code in list(bind.execute(sa.text("SELECT id, employee_code FROM employees"))):
        if code.upper().startswith("EMP") and code[3:].lstrip("-").isdigit():
            new = _code()
            while new in taken:
                new = _code()
            taken.add(new)
            bind.execute(sa.text("UPDATE employees SET employee_code=:c WHERE id=:i"), {"c": new, "i": emp_id})


def downgrade() -> None:
    op.drop_constraint('fk_dept_qa', 'departments', type_='foreignkey')
    op.drop_column('departments', 'qa_employee_id')
    op.drop_table('login_otps')
