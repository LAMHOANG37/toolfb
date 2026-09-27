"""Editorial workflow, durable operations and publication snapshots."""
from alembic import op
import sqlalchemy as sa

revision = "c91a_newsroom_workflow"
down_revision = "35cc4675135e"
branch_labels = depends_on = None


def upgrade():
    op.add_column("sources", sa.Column("strategy", sa.String(), nullable=False, server_default="rss"))
    op.execute("UPDATE sources SET strategy='webpage' WHERE feed_url IS NULL OR feed_url=''")
    for col in [sa.Column("verification_notes", sa.Text()), sa.Column("revision", sa.Integer(), nullable=False, server_default="1"), sa.Column("approved_at", sa.DateTime(timezone=True))]:
        op.add_column("drafts", col)
    for col in [sa.Column("active_key", sa.String()), sa.Column("payload_text", sa.Text()), sa.Column("card_path", sa.String()), sa.Column("content_hash", sa.String()), sa.Column("dry_run", sa.Boolean(), nullable=False, server_default=sa.true()), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True))]:
        op.add_column("publish_jobs", col)
    op.create_index("uq_job_active_key", "publish_jobs", ["active_key"], unique=True)
    op.add_column("publish_jobs", sa.Column("active_content", sa.String()))
    op.add_column("publish_jobs", sa.Column("page_id", sa.String()))
    op.create_index("uq_job_active_content", "publish_jobs", ["active_content"], unique=True)
    op.create_index("ix_publish_jobs_content_hash", "publish_jobs", ["content_hash"])
    op.execute("UPDATE publish_jobs SET status='CANCELLED' WHERE status IN ('PENDING', 'RUNNING')")
    op.execute("UPDATE drafts SET status='NEEDS_REVIEW' WHERE status='SCHEDULED'")
    op.add_column("posts", sa.Column("content_hash", sa.String()))
    op.create_index("uq_post_content_hash", "posts", ["content_hash"], unique=True)
    op.create_table("operations", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("kind", sa.String(), nullable=False), sa.Column("status", sa.String(), nullable=False), sa.Column("active_key", sa.String(), unique=True), sa.Column("started_at", sa.DateTime(timezone=True)), sa.Column("completed_at", sa.DateTime(timezone=True)), sa.Column("detail", sa.Text()))
    op.create_table("activities", sa.Column("id", sa.Integer(), primary_key=True), sa.Column("message", sa.Text(), nullable=False), sa.Column("created_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_table("activities")
    op.drop_table("operations")
    op.drop_index("uq_post_content_hash", table_name="posts")
    op.drop_column("posts", "content_hash")
    op.drop_index("uq_job_active_key", table_name="publish_jobs")
    op.drop_index("uq_job_active_content", table_name="publish_jobs")
    op.drop_column("publish_jobs", "active_content")
    op.drop_column("publish_jobs", "page_id")
    op.drop_index("ix_publish_jobs_content_hash", table_name="publish_jobs")
    for name in ["active_key", "payload_text", "card_path", "content_hash", "dry_run", "started_at", "completed_at"]:
        op.drop_column("publish_jobs", name)
    for name in ["verification_notes", "revision", "approved_at"]:
        op.drop_column("drafts", name)
    op.drop_column("sources", "strategy")
