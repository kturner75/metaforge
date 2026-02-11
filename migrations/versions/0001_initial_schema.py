"""initial schema"""

revision = "0001"
down_revision = None

from alembic import op
import sqlalchemy as sa


def upgrade():
    op.create_table(
        'company',
        sa.Column('createdBy', sa.Text(), nullable=True),
        sa.Column('createdAt', sa.Text(), nullable=True),
        sa.Column('updatedBy', sa.Text(), nullable=True),
        sa.Column('updatedAt', sa.Text(), nullable=True),
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('tenantId', sa.Text(), nullable=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('industry', sa.Text(), nullable=True),
        sa.Column('website', sa.Text(), nullable=True),
        sa.Column('phone', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
    )
    op.create_table(
        'tenant',
        sa.Column('createdBy', sa.Text(), nullable=True),
        sa.Column('createdAt', sa.Text(), nullable=True),
        sa.Column('updatedBy', sa.Text(), nullable=True),
        sa.Column('updatedAt', sa.Text(), nullable=True),
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('slug', sa.Text(), nullable=False),
        sa.Column('active', sa.Integer(), nullable=True),
    )
    op.create_table(
        'tenant_membership',
        sa.Column('createdBy', sa.Text(), nullable=True),
        sa.Column('createdAt', sa.Text(), nullable=True),
        sa.Column('updatedBy', sa.Text(), nullable=True),
        sa.Column('updatedAt', sa.Text(), nullable=True),
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('userId', sa.Text(), nullable=False),
        sa.Column('tenantId', sa.Text(), nullable=False),
        sa.Column('role', sa.Text(), nullable=False),
    )
    op.create_table(
        'user',
        sa.Column('createdBy', sa.Text(), nullable=True),
        sa.Column('createdAt', sa.Text(), nullable=True),
        sa.Column('updatedBy', sa.Text(), nullable=True),
        sa.Column('updatedAt', sa.Text(), nullable=True),
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('email', sa.Text(), nullable=False),
        sa.Column('passwordHash', sa.Text(), nullable=True),
        sa.Column('name', sa.Text(), nullable=False),
        sa.Column('active', sa.Integer(), nullable=True),
    )
    op.create_table(
        'contact',
        sa.Column('createdBy', sa.Text(), nullable=True),
        sa.Column('createdAt', sa.Text(), nullable=True),
        sa.Column('updatedBy', sa.Text(), nullable=True),
        sa.Column('updatedAt', sa.Text(), nullable=True),
        sa.Column('id', sa.Text(), primary_key=True),
        sa.Column('tenantId', sa.Text(), nullable=True),
        sa.Column('firstName', sa.Text(), nullable=False),
        sa.Column('lastName', sa.Text(), nullable=False),
        sa.Column('email', sa.Text(), nullable=True),
        sa.Column('phone', sa.Text(), nullable=True),
        sa.Column('companyId', sa.Text(), nullable=True),
        sa.Column('status', sa.Text(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('fullName', sa.Text(), nullable=True),
    )


def downgrade():
    op.drop_table('company')
    op.drop_table('tenant')
    op.drop_table('tenant_membership')
    op.drop_table('user')
    op.drop_table('contact')
