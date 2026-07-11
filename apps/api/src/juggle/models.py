"""Single import point that registers every module's ORM models on
``Base.metadata``.

Alembic (``alembic/env.py``) and any ``create_all`` path imports this module so
the full schema is known. This is deliberately *not* a domain module, so it may
reference every module's ``core.models`` without breaking module independence.
"""

# Import for metadata side effects only. Order is irrelevant; FKs resolve by
# table name at create time.
from juggle.modules.admin.core import models as admin_models  # noqa: F401
from juggle.modules.audit.core import models as audit_models  # noqa: F401
from juggle.modules.booking.core import models as booking_models  # noqa: F401
from juggle.modules.catalog.core import models as catalog_models  # noqa: F401
from juggle.modules.comms.core import models as comms_models  # noqa: F401
from juggle.modules.config.core import models as config_models  # noqa: F401
from juggle.modules.flags.core import models as flags_models  # noqa: F401
from juggle.modules.identity.core import models as identity_models  # noqa: F401
from juggle.modules.inventory.core import models as inventory_models  # noqa: F401
from juggle.modules.notifications.core import models as notifications_models  # noqa: F401
from juggle.modules.org.core import models as org_models  # noqa: F401
from juggle.modules.payments.core import models as payments_models  # noqa: F401
from juggle.modules.reviews.core import models as reviews_models  # noqa: F401
from juggle.modules.roster.core import models as roster_models  # noqa: F401
from juggle.modules.scheduler.core import models as scheduler_models  # noqa: F401
from juggle.modules.waitlist.core import models as waitlist_models  # noqa: F401
