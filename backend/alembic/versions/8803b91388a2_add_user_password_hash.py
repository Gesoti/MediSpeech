"""add_user_password_hash

Revision ID: 8803b91388a2
Revises: 001_initial_schema
Create Date: 2026-05-18 13:43:58.350047

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '8803b91388a2'
down_revision = '001_initial_schema'
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add password_hash column to users table."""
    op.add_column("users", sa.Column("password_hash", sa.String(255), nullable=True))


def downgrade() -> None:
    """Remove password_hash column from users table."""
    op.drop_column("users", "password_hash")
