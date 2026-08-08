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


@pytest.fixture(autouse=True)
def reset_in_memory_store() -> None:
    storage.clear()
    project_service.clear()
    research_service.clear()
    yield
    storage.clear()
    project_service.clear()
    research_service.clear()
