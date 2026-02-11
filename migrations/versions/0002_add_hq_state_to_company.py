"""add hq_state to Company"""

revision = "0002"
down_revision = "0001"

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.add_column('company', sa.Column('hq_state', sa.Text(), nullable=True))


def downgrade():
    op.drop_column('company', 'hq_state')
