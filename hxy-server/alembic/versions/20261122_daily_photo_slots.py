"""Version the inspection checklist and allow three photos per area."""

from alembic import op
import sqlalchemy as sa

revision = "20261122_daily_photo_slots"
down_revision = "20261114_member_consumption"
branch_labels = None
depends_on = None

OLD_AREAS = "'restroom', 'water_room', 'cashier', 'rest_area', 'foot_area'"


def upgrade():
    op.add_column("daily_store_checkins", sa.Column("checklist_version", sa.SmallInteger(), nullable=True))
    with op.batch_alter_table("daily_area_photos") as photos:
        photos.add_column(sa.Column("slot", sa.SmallInteger(), nullable=False, server_default="1"))
        photos.drop_constraint("uq_daily_area_photo_area", type_="unique")
        photos.drop_constraint("ck_daily_area_photo_area", type_="check")
        photos.create_unique_constraint("uq_daily_area_photo_slot", ["checkin_id", "area", "slot"])
        photos.create_check_constraint("ck_daily_area_photo_slot", "slot BETWEEN 1 AND 3")
        photos.create_check_constraint("ck_daily_area_photo_area", f"area IN ({OLD_AREAS}, 'herbal_prep')")


def downgrade():
    db = op.get_bind()
    if db.scalar(sa.text("SELECT COUNT(*) FROM daily_area_photos WHERE slot <> 1 OR area = 'herbal_prep'")) or db.scalar(
        sa.text("SELECT COUNT(*) FROM daily_store_checkins WHERE checklist_version = 2")
    ):
        raise RuntimeError("Cannot downgrade while the new checklist or additional photos are in use")
    with op.batch_alter_table("daily_area_photos") as photos:
        photos.drop_constraint("uq_daily_area_photo_slot", type_="unique")
        photos.drop_constraint("ck_daily_area_photo_slot", type_="check")
        photos.drop_constraint("ck_daily_area_photo_area", type_="check")
        photos.create_unique_constraint("uq_daily_area_photo_area", ["checkin_id", "area"])
        photos.create_check_constraint("ck_daily_area_photo_area", f"area IN ({OLD_AREAS})")
        photos.drop_column("slot")
    op.drop_column("daily_store_checkins", "checklist_version")
