"""Allow warehouse, shower and four named SPA inspection points."""

from alembic import op
import sqlalchemy as sa

revision = "20261126_inspection_areas"
down_revision = "20261122_inspection_ai"
branch_labels = None
depends_on = None

OLD_AREAS = "'restroom', 'water_room', 'cashier', 'rest_area', 'foot_area', 'herbal_prep'"
NEW_AREAS = "'warehouse', 'shower_room', 'spa_banxia', 'spa_rendong', 'spa_duruo', 'spa_qingdai'"


def _set_allowed_areas(areas):
    with op.batch_alter_table("daily_area_photos") as photos:
        photos.drop_constraint("ck_daily_area_photo_area", type_="check")
        photos.create_check_constraint("ck_daily_area_photo_area", f"area IN ({areas})")


def upgrade():
    _set_allowed_areas(f"{OLD_AREAS}, {NEW_AREAS}")


def downgrade():
    db = op.get_bind()
    if db.scalar(sa.text(f"SELECT EXISTS (SELECT 1 FROM daily_area_photos WHERE area IN ({NEW_AREAS}))")) or db.scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM daily_store_checkins WHERE checklist_version = 3)")
    ):
        raise RuntimeError("Cannot downgrade while the Huafu inspection checklist is in use")
    _set_allowed_areas(OLD_AREAS)
