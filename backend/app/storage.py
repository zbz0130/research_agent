"""Small SQLite persistence layer for the WishForge first version.

The application intentionally keeps the repository boundary very small.  The
domain services still own validation and workflow rules; this module only
stores validated Pydantic documents and a few indexed columns used for listing
and optimistic concurrency.  A later PostgreSQL repository can implement the
same operations without changing the API contracts.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from threading import RLock

from app.config import Settings
from app.research_schemas import AnalysisJob, ConceptGraph, GraphPatch, IdeaCheckResult
from app.schemas import Project


class Storage:
    """Thread-safe SQLite document store.

    The default path is ignored by git and can be changed with
    ``WISHFORGE_STORAGE_PATH``.  ``:memory:`` is supported for isolated tests,
    but a file is used by default so a server restart keeps the workspace.
    """

    def __init__(self, path: str | None = None) -> None:
        # Reuse the same .env + environment parsing as the API. This matters
        # when a user configures WISHFORGE_STORAGE_PATH in .env rather than
        # exporting it in the shell.
        configured = path or Settings().storage_path
        self.path = configured
        self._lock = RLock()
        self._connection: sqlite3.Connection | None = None
        self._ensure_schema()

    def _connect(self) -> sqlite3.Connection:
        if self.path == ":memory:":
            if self._connection is None:
                self._connection = sqlite3.connect(
                    ":memory:", check_same_thread=False, timeout=30
                )
                self._connection.row_factory = sqlite3.Row
                self._connection.execute("PRAGMA foreign_keys = ON")
            return self._connection

        db_path = Path(self.path)
        db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(str(db_path), check_same_thread=False, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        return connection

    def _run(self, callback):
        with self._lock:
            connection = self._connect()
            try:
                result = callback(connection)
                connection.commit()
                return result
            except Exception:
                connection.rollback()
                raise
            finally:
                if self.path != ":memory:":
                    connection.close()

    def _ensure_schema(self) -> None:
        def create(connection: sqlite3.Connection) -> None:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS analysis_jobs (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS concept_graphs (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    project_id TEXT,
                    version INTEGER NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS graph_patches (
                    id TEXT PRIMARY KEY,
                    graph_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    FOREIGN KEY (graph_id) REFERENCES concept_graphs(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS idea_checks (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    similarity_level TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_analysis_created
                    ON analysis_jobs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_graph_project
                    ON concept_graphs(project_id);
                CREATE INDEX IF NOT EXISTS idx_patch_graph_created
                    ON graph_patches(graph_id, created_at ASC);
                CREATE INDEX IF NOT EXISTS idx_idea_checks_created
                    ON idea_checks(created_at DESC);
                """
            )

        self._run(create)

    # ----- projects -----------------------------------------------------
    def save_project(self, project: Project) -> Project:
        payload = project.model_dump_json()
        self._run(
            lambda connection: connection.execute(
                """
                INSERT INTO projects(id, payload, created_at) VALUES (?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
                    created_at=excluded.created_at
                """,
                (str(project.id), payload, project.created_at.isoformat()),
            )
        )
        return project.model_copy(deep=True)

    def list_projects(self) -> list[Project]:
        def read(connection: sqlite3.Connection) -> list[Project]:
            rows = connection.execute(
                "SELECT payload FROM projects ORDER BY created_at DESC"
            ).fetchall()
            return [Project.model_validate_json(row["payload"]) for row in rows]

        return self._run(read)

    # ----- analyses ----------------------------------------------------
    def save_analysis(self, job: AnalysisJob) -> AnalysisJob:
        self._run(
            lambda connection: connection.execute(
                """
                INSERT INTO analysis_jobs(id, payload, created_at, status)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
                    created_at=excluded.created_at, status=excluded.status
                """,
                (
                    str(job.id),
                    job.model_dump_json(),
                    job.created_at.isoformat(),
                    job.status,
                ),
            )
        )
        return job.model_copy(deep=True)

    def get_analysis(self, job_id: str) -> AnalysisJob | None:
        def read(connection: sqlite3.Connection) -> AnalysisJob | None:
            row = connection.execute(
                "SELECT payload FROM analysis_jobs WHERE id = ?", (job_id,)
            ).fetchone()
            return AnalysisJob.model_validate_json(row["payload"]) if row else None

        return self._run(read)

    def list_analyses(self) -> list[AnalysisJob]:
        def read(connection: sqlite3.Connection) -> list[AnalysisJob]:
            rows = connection.execute(
                "SELECT payload FROM analysis_jobs ORDER BY created_at DESC"
            ).fetchall()
            return [AnalysisJob.model_validate_json(row["payload"]) for row in rows]

        return self._run(read)

    # ----- explicit idea checks ---------------------------------------
    def save_idea_check(self, result: IdeaCheckResult) -> IdeaCheckResult:
        self._run(
            lambda connection: connection.execute(
                """
                INSERT INTO idea_checks(id, payload, created_at, similarity_level)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
                    created_at=excluded.created_at,
                    similarity_level=excluded.similarity_level
                """,
                (
                    result.id,
                    result.model_dump_json(),
                    result.created_at.isoformat(),
                    result.similarity_level,
                ),
            )
        )
        return result.model_copy(deep=True)

    def get_idea_check(self, check_id: str) -> IdeaCheckResult | None:
        def read(connection: sqlite3.Connection) -> IdeaCheckResult | None:
            row = connection.execute(
                "SELECT payload FROM idea_checks WHERE id = ?", (check_id,)
            ).fetchone()
            return IdeaCheckResult.model_validate_json(row["payload"]) if row else None

        return self._run(read)

    def list_idea_checks(self) -> list[IdeaCheckResult]:
        def read(connection: sqlite3.Connection) -> list[IdeaCheckResult]:
            rows = connection.execute(
                "SELECT payload FROM idea_checks ORDER BY created_at DESC"
            ).fetchall()
            return [IdeaCheckResult.model_validate_json(row["payload"]) for row in rows]

        return self._run(read)

    # ----- graphs ------------------------------------------------------
    def save_graph(self, graph: ConceptGraph) -> ConceptGraph:
        self._run(
            lambda connection: connection.execute(
                """
                INSERT INTO concept_graphs(id, payload, project_id, version, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
                    project_id=excluded.project_id, version=excluded.version,
                    updated_at=excluded.updated_at
                """,
                (
                    graph.id,
                    graph.model_dump_json(),
                    str(graph.project_id) if graph.project_id else None,
                    graph.version,
                    graph.updated_at.isoformat(),
                ),
            )
        )
        return graph.model_copy(deep=True)

    def get_graph(self, graph_id: str) -> ConceptGraph | None:
        def read(connection: sqlite3.Connection) -> ConceptGraph | None:
            row = connection.execute(
                "SELECT payload FROM concept_graphs WHERE id = ?", (graph_id,)
            ).fetchone()
            return ConceptGraph.model_validate_json(row["payload"]) if row else None

        return self._run(read)

    def list_graphs(self, project_id: str | None = None) -> list[ConceptGraph]:
        def read(connection: sqlite3.Connection) -> list[ConceptGraph]:
            if project_id is None:
                rows = connection.execute(
                    "SELECT payload FROM concept_graphs ORDER BY updated_at DESC"
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT payload FROM concept_graphs
                    WHERE project_id = ? ORDER BY updated_at DESC
                    """,
                    (project_id,),
                ).fetchall()
            return [ConceptGraph.model_validate_json(row["payload"]) for row in rows]

        return self._run(read)

    def update_graph_if_version(
        self, graph: ConceptGraph, expected_version: int
    ) -> bool:
        """Atomically replace a graph only if its stored version is unchanged."""

        def update(connection: sqlite3.Connection) -> bool:
            cursor = connection.execute(
                """
                UPDATE concept_graphs
                SET payload = ?, project_id = ?, version = ?, updated_at = ?
                WHERE id = ? AND version = ?
                """,
                (
                    graph.model_dump_json(),
                    str(graph.project_id) if graph.project_id else None,
                    graph.version,
                    graph.updated_at.isoformat(),
                    graph.id,
                    expected_version,
                ),
            )
            return cursor.rowcount == 1

        return bool(self._run(update))

    # ----- graph patches -----------------------------------------------
    def save_patch(self, patch: GraphPatch) -> GraphPatch:
        self._run(
            lambda connection: connection.execute(
                """
                INSERT INTO graph_patches(id, graph_id, payload, created_at, status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
                    status=excluded.status
                """,
                (
                    patch.id,
                    patch.graph_id,
                    patch.model_dump_json(),
                    patch.created_at.isoformat(),
                    patch.status,
                ),
            )
        )
        return patch.model_copy(deep=True)

    def save_graph_and_patch(self, graph: ConceptGraph, patch: GraphPatch) -> None:
        """Persist a graph mutation and its patch record in one transaction."""

        def write(connection: sqlite3.Connection) -> None:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO concept_graphs(id, payload, project_id, version, updated_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
                    project_id=excluded.project_id, version=excluded.version,
                    updated_at=excluded.updated_at
                """,
                (
                    graph.id,
                    graph.model_dump_json(),
                    str(graph.project_id) if graph.project_id else None,
                    graph.version,
                    graph.updated_at.isoformat(),
                ),
            )
            connection.execute(
                """
                INSERT INTO graph_patches(id, graph_id, payload, created_at, status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
                    status=excluded.status
                """,
                (
                    patch.id,
                    patch.graph_id,
                    patch.model_dump_json(),
                    patch.created_at.isoformat(),
                    patch.status,
                ),
            )

        self._run(write)

    def update_graph_and_patch_if_version(
        self,
        graph: ConceptGraph,
        patch: GraphPatch,
        expected_version: int,
    ) -> bool:
        """CAS-update a graph and its patch atomically.

        Returning ``False`` means another writer changed the graph after the
        caller read it. In that case neither the graph nor the patch is
        committed.
        """

        def write(connection: sqlite3.Connection) -> bool:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE concept_graphs
                SET payload = ?, project_id = ?, version = ?, updated_at = ?
                WHERE id = ? AND version = ?
                """,
                (
                    graph.model_dump_json(),
                    str(graph.project_id) if graph.project_id else None,
                    graph.version,
                    graph.updated_at.isoformat(),
                    graph.id,
                    expected_version,
                ),
            )
            if cursor.rowcount != 1:
                connection.rollback()
                return False
            connection.execute(
                """
                INSERT INTO graph_patches(id, graph_id, payload, created_at, status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
                    status=excluded.status
                """,
                (
                    patch.id,
                    patch.graph_id,
                    patch.model_dump_json(),
                    patch.created_at.isoformat(),
                    patch.status,
                ),
            )
            return True

        return bool(self._run(write))

    def get_patch(self, patch_id: str) -> GraphPatch | None:
        def read(connection: sqlite3.Connection) -> GraphPatch | None:
            row = connection.execute(
                "SELECT payload FROM graph_patches WHERE id = ?", (patch_id,)
            ).fetchone()
            return GraphPatch.model_validate_json(row["payload"]) if row else None

        return self._run(read)

    def list_patches(self, graph_id: str) -> list[GraphPatch]:
        def read(connection: sqlite3.Connection) -> list[GraphPatch]:
            rows = connection.execute(
                """
                SELECT payload FROM graph_patches
                WHERE graph_id = ? ORDER BY created_at ASC
                """,
                (graph_id,),
            ).fetchall()
            return [GraphPatch.model_validate_json(row["payload"]) for row in rows]

        return self._run(read)

    def clear_projects(self) -> None:
        self._run(lambda connection: connection.execute("DELETE FROM projects"))

    def clear_graphs(self) -> None:
        """Clear graph documents and their patch history only."""

        def clear(connection: sqlite3.Connection) -> None:
            connection.execute("DELETE FROM graph_patches")
            connection.execute("DELETE FROM concept_graphs")

        self._run(clear)

    def clear_research(self) -> None:
        def clear(connection: sqlite3.Connection) -> None:
            connection.execute("DELETE FROM graph_patches")
            connection.execute("DELETE FROM concept_graphs")
            connection.execute("DELETE FROM analysis_jobs")
            connection.execute("DELETE FROM idea_checks")

        self._run(clear)

    def clear(self) -> None:
        """Clear every persisted MVP object; intended for tests and local reset."""

        def clear_all(connection: sqlite3.Connection) -> None:
            connection.execute("DELETE FROM graph_patches")
            connection.execute("DELETE FROM concept_graphs")
            connection.execute("DELETE FROM analysis_jobs")
            connection.execute("DELETE FROM idea_checks")
            connection.execute("DELETE FROM projects")

        self._run(clear_all)

    def close(self) -> None:
        """Close a persistent in-memory connection, if one is open."""

        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None


storage = Storage()
