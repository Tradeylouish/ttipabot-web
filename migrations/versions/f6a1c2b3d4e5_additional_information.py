"""Additional information column

Revision ID: f6a1c2b3d4e5
Revises: e0889df2aa48
Create Date: 2026-07-06 13:30:00.000000

"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f6a1c2b3d4e5"
down_revision = "e0889df2aa48"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("attorneys", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("additional_information", sa.String(length=256), nullable=True)
        )


def downgrade():
    with op.batch_alter_table("attorneys", schema=None) as batch_op:
        batch_op.drop_column("additional_information")
