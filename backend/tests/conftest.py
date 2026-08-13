import os
import tempfile
from pathlib import Path

# Keep the process-wide service singletons on a disposable database. This is
# set before importing any service, so ``app.storage.storage`` opens the test
# database rather than creating data/wishforge.db in the repository.
os.environ.setdefault(
    "WISHFORGE_STORAGE_PATH",
    str(Path(tempfile.gettempdir()) / "wishforge-tests.db"),
)

import pytest

from app.storage import storage
from app.services.project_service import project_service
from app.services.research_service import research_service
from app.services.overview_service import overview_service


@pytest.fixture(autouse=True)
def reset_in_memory_store() -> None:
    # Invalidate asynchronous workers before deleting their durable rows.
    # Otherwise an Overview worker from the preceding test can finish between
    # ``storage.clear`` and ``overview_service.clear`` and recreate a job in
    # the freshly reset database.
    overview_service.clear()
    research_service.clear()
    project_service.clear()
    storage.clear()
    yield
    overview_service.clear()
    research_service.clear()
    project_service.clear()
    storage.clear()
