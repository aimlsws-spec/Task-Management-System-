"""Import every model module so Base.metadata is complete (used by Alembic, tests, seeding)."""

from app.modules.ai import models as _ai  # noqa: F401
from app.modules.audit import models as _audit  # noqa: F401
from app.modules.auth import models as _auth  # noqa: F401
from app.modules.collab import models as _collab  # noqa: F401
from app.modules.notifications import models as _notifications  # noqa: F401
from app.modules.org import models as _org  # noqa: F401
from app.modules.rbac import models as _rbac  # noqa: F401
from app.modules.tasks import models as _tasks  # noqa: F401
from app.modules.timetracking import models as _timetracking  # noqa: F401
from app.modules.workcal import models as _workcal  # noqa: F401
