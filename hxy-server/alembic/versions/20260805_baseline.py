"""Mark the existing production schema as the migration baseline.

This revision intentionally makes no DDL changes. It must be stamped only on
a verified production-schema restore, never applied as a schema initializer.
"""

from typing import Sequence, Union

from alembic import op


revision: str = "20260805_baseline"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
