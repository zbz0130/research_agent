"""Small SQLite persistence layer for the WishForge first version.

The application intentionally keeps the repository boundary very small.  The
domain services still own validation and workflow rules; this module only
stores validated Pydantic documents and a few indexed columns used for listing
and optimistic concurrency.  A later PostgreSQL repository can implement the
same operations without changing the API contracts.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock

from app.config import Settings
from app.experiment_schemas import ExperimentPlan
from app.research_schemas import (
    AnalysisJob,
    ConceptGraph,
    GraphPatch,
    IdeaCheckResult,
    OverviewJob,
)
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
                    updated_at TEXT NOT NULL,
                    graph_kind TEXT NOT NULL DEFAULT 'concept_network',
                    source_analysis_id TEXT,
                    source_scope TEXT NOT NULL DEFAULT 'metadata_abstract',
                    save_state TEXT NOT NULL DEFAULT 'saved',
                    generation_id TEXT
                );
                CREATE TABLE IF NOT EXISTS graph_patches (
                    id TEXT PRIMARY KEY,
                    graph_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    FOREIGN KEY (graph_id) REFERENCES concept_graphs(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS analysis_graph_patches (
                    id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    status TEXT NOT NULL,
                    base_version INTEGER,
                    FOREIGN KEY (analysis_id) REFERENCES analysis_jobs(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS idea_checks (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    similarity_level TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS experiment_plans (
                    id TEXT PRIMARY KEY,
                    payload TEXT NOT NULL,
                    project_id TEXT,
                    created_at TEXT NOT NULL,
                    approval_status TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_analysis_created
                    ON analysis_jobs(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_graph_project
                    ON concept_graphs(project_id);
                CREATE INDEX IF NOT EXISTS idx_patch_graph_created
                    ON graph_patches(graph_id, created_at ASC);
                CREATE INDEX IF NOT EXISTS idx_analysis_patch_created
                    ON analysis_graph_patches(analysis_id, created_at ASC);
                CREATE INDEX IF NOT EXISTS idx_idea_checks_created
                    ON idea_checks(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_experiment_plans_created
                    ON experiment_plans(created_at DESC);
                CREATE INDEX IF NOT EXISTS idx_experiment_plans_project
                    ON experiment_plans(project_id);
                """
            )

            # ``CREATE TABLE IF NOT EXISTS`` does not add columns to a
            # database created by an earlier WishForge release.  Keep this
            # migration deliberately small and idempotent so a user's existing
            # SQLite file remains readable after upgrading.
            existing_columns = {
                row[1]
                for row in connection.execute("PRAGMA table_info(concept_graphs)").fetchall()
            }
            migrations = {
                "graph_kind": "TEXT NOT NULL DEFAULT 'concept_network'",
                "source_analysis_id": "TEXT",
                "source_scope": "TEXT NOT NULL DEFAULT 'metadata_abstract'",
                "save_state": "TEXT NOT NULL DEFAULT 'saved'",
                "generation_id": "TEXT",
            }
            for column, definition in migrations.items():
                if column not in existing_columns:
                    connection.execute(
                        f"ALTER TABLE concept_graphs ADD COLUMN {column} {definition}"
                    )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_graph_save_state
                    ON concept_graphs(save_state, updated_at DESC)
                """
            )

            # Reserved for the asynchronous research-direction Overview
            # pipeline.  Creating the table here keeps the schema migration
            # forward-compatible without coupling Phase 1 to its workers.
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS overview_jobs (
                    id TEXT PRIMARY KEY,
                    analysis_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    progress INTEGER NOT NULL DEFAULT 0,
                    payload TEXT NOT NULL,
                    result_payload TEXT,
                    save_state TEXT NOT NULL DEFAULT 'transient',
                    error TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    version INTEGER NOT NULL DEFAULT 1
                );
                CREATE INDEX IF NOT EXISTS idx_overview_analysis
                    ON overview_jobs(analysis_id, updated_at DESC);
                """
            )
            current_user_version = int(
                connection.execute("PRAGMA user_version").fetchone()[0]
            )
            if current_user_version < 2:
                connection.execute("PRAGMA user_version = 2")

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
            return self._decode_analysis(row["payload"]) if row else None

        return self._run(read)

    def list_analyses(self) -> list[AnalysisJob]:
        def read(connection: sqlite3.Connection) -> list[AnalysisJob]:
            rows = connection.execute(
                "SELECT payload FROM analysis_jobs ORDER BY created_at DESC"
            ).fetchall()
            return [self._decode_analysis(row["payload"]) for row in rows]

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

    # ----- experiment plans ------------------------------------------
    def save_experiment_plan(self, plan: ExperimentPlan) -> ExperimentPlan:
        self._run(
            lambda connection: connection.execute(
                """
                INSERT INTO experiment_plans(id, payload, project_id, created_at, approval_status)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
                    project_id=excluded.project_id, created_at=excluded.created_at,
                    approval_status=excluded.approval_status
                """,
                (
                    plan.id,
                    json.dumps(plan.persistence_payload(), ensure_ascii=False),
                    str(plan.project_id) if plan.project_id else None,
                    plan.generated_at.isoformat(),
                    plan.approval_status,
                ),
            )
        )
        return plan.model_copy(deep=True)

    def get_experiment_plan(self, plan_id: str) -> ExperimentPlan | None:
        def read(connection: sqlite3.Connection) -> ExperimentPlan | None:
            row = connection.execute(
                "SELECT payload FROM experiment_plans WHERE id = ?", (plan_id,)
            ).fetchone()
            return ExperimentPlan.model_validate_json(row["payload"]) if row else None

        return self._run(read)

    def list_experiment_plans(self, project_id: str | None = None) -> list[ExperimentPlan]:
        def read(connection: sqlite3.Connection) -> list[ExperimentPlan]:
            if project_id is None:
                rows = connection.execute(
                    "SELECT payload FROM experiment_plans ORDER BY created_at DESC"
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT payload FROM experiment_plans
                    WHERE project_id = ? ORDER BY created_at DESC
                    """,
                    (project_id,),
                ).fetchall()
            return [ExperimentPlan.model_validate_json(row["payload"]) for row in rows]

        return self._run(read)

    # ----- graphs ------------------------------------------------------
    def save_graph(self, graph: ConceptGraph) -> ConceptGraph:
        # A row in ``concept_graphs`` is, by definition, a saved graph.  The
        # transient representation lives inside ``analysis_jobs`` and should
        # never leak into this library even if an internal caller forgets to
        # promote it first.
        graph = graph.model_copy(update={"save_state": "saved"})
        self._run(
            lambda connection: connection.execute(
                """
                INSERT INTO concept_graphs(
                    id, payload, project_id, version, updated_at,
                    graph_kind, source_analysis_id, source_scope, save_state, generation_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
                    project_id=excluded.project_id, version=excluded.version,
                    updated_at=excluded.updated_at,
                    graph_kind=excluded.graph_kind,
                    source_analysis_id=excluded.source_analysis_id,
                    source_scope=excluded.source_scope,
                    save_state=excluded.save_state,
                    generation_id=excluded.generation_id
                """,
                (
                    graph.id,
                    graph.model_dump_json(),
                    str(graph.project_id) if graph.project_id else None,
                    graph.version,
                    graph.updated_at.isoformat(),
                    graph.graph_kind,
                    graph.source_analysis_id,
                    graph.source_scope,
                    graph.save_state,
                    graph.generation_id,
                ),
            )
        )
        return graph.model_copy(deep=True)

    def get_graph(self, graph_id: str) -> ConceptGraph | None:
        def read(connection: sqlite3.Connection) -> ConceptGraph | None:
            row = connection.execute(
                """
                SELECT payload, graph_kind, source_analysis_id, source_scope,
                       save_state, generation_id
                FROM concept_graphs WHERE id = ?
                """,
                (graph_id,),
            ).fetchone()
            return self._decode_graph(row) if row else None

        return self._run(read)

    def list_graphs(self, project_id: str | None = None) -> list[ConceptGraph]:
        def read(connection: sqlite3.Connection) -> list[ConceptGraph]:
            if project_id is None:
                rows = connection.execute(
                    """
                    SELECT payload, save_state FROM concept_graphs
                    WHERE COALESCE(save_state, 'saved') = 'saved'
                    ORDER BY updated_at DESC
                    """
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT payload, save_state FROM concept_graphs
                    WHERE project_id = ? AND COALESCE(save_state, 'saved') = 'saved'
                    ORDER BY updated_at DESC
                    """,
                    (project_id,),
                ).fetchall()
            return [self._decode_graph(row) for row in rows]

        return self._run(read)

    def update_graph_if_version(
        self, graph: ConceptGraph, expected_version: int
    ) -> bool:
        """Atomically replace a graph only if its stored version is unchanged."""

        graph = graph.model_copy(update={"save_state": "saved"})

        def update(connection: sqlite3.Connection) -> bool:
            cursor = connection.execute(
                """
                UPDATE concept_graphs
                SET payload = ?, project_id = ?, version = ?, updated_at = ?
                    , graph_kind = ?, source_analysis_id = ?, source_scope = ?,
                    save_state = ?, generation_id = ?
                WHERE id = ? AND version = ?
                """,
                (
                    graph.model_dump_json(),
                    str(graph.project_id) if graph.project_id else None,
                    graph.version,
                    graph.updated_at.isoformat(),
                    graph.graph_kind,
                    graph.source_analysis_id,
                    graph.source_scope,
                    graph.save_state,
                    graph.generation_id,
                    graph.id,
                    expected_version,
                ),
            )
            return cursor.rowcount == 1

        return bool(self._run(update))

    def delete_graph(self, graph_id: str, expected_version: int | None = None) -> bool:
        """Delete a saved graph and cascade its patch history atomically.

        ``False`` means either the graph was not found or its version did not
        match.  The service layer performs a read first to turn those cases
        into a 404 or 409 without exposing storage-specific details.

        When a graph was created from an analysis, the analysis keeps an
        independent snapshot so deleting the library copy must not make that
        snapshot claim that it is still saved.  The snapshot is therefore
        marked transient in the same SQLite transaction as the graph delete.
        """

        def delete(connection: sqlite3.Connection) -> bool:
            row = connection.execute(
                "SELECT payload, source_analysis_id, version FROM concept_graphs WHERE id = ?",
                (graph_id,),
            ).fetchone()
            if row is None:
                return False
            if expected_version is not None and row["version"] != expected_version:
                return False

            source_analysis_id = row["source_analysis_id"]
            if expected_version is None:
                cursor = connection.execute(
                    "DELETE FROM concept_graphs WHERE id = ?", (graph_id,)
                )
            else:
                cursor = connection.execute(
                    "DELETE FROM concept_graphs WHERE id = ? AND version = ?",
                    (graph_id, expected_version),
                )
            if cursor.rowcount != 1:
                return False

            analysis_rows = (
                connection.execute(
                    "SELECT id, payload FROM analysis_jobs WHERE id = ?",
                    (source_analysis_id,),
                ).fetchall()
                if source_analysis_id
                else connection.execute(
                    "SELECT id, payload FROM analysis_jobs"
                ).fetchall()
            )
            for analysis_row in analysis_rows:
                analysis_id = analysis_row["id"]
                analysis_payload = json.loads(analysis_row["payload"])
                result = analysis_payload.get("result")
                graph = result.get("graph") if isinstance(result, dict) else None
                # Only rewrite the snapshot that points at the deleted graph.
                # The fallback scan keeps deletion compatible with graphs
                # created before ``source_analysis_id`` was indexed.
                if isinstance(result, dict) and isinstance(graph, dict) and (
                    graph.get("id") == graph_id
                    or result.get("saved_graph_id") == graph_id
                ):
                    graph["save_state"] = "transient"
                    result["graph"] = graph
                    result["graph_save_state"] = "transient"
                    result["saved_graph_id"] = None
                    analysis_payload["result"] = result
                    connection.execute(
                        "UPDATE analysis_jobs SET payload = ? WHERE id = ?",
                        (json.dumps(analysis_payload, ensure_ascii=False), analysis_id),
                    )
            return True

        return bool(self._run(delete))

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

        graph = graph.model_copy(update={"save_state": "saved"})

        def write(connection: sqlite3.Connection) -> None:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO concept_graphs(
                    id, payload, project_id, version, updated_at,
                    graph_kind, source_analysis_id, source_scope, save_state, generation_id
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
                    project_id=excluded.project_id, version=excluded.version,
                    updated_at=excluded.updated_at,
                    graph_kind=excluded.graph_kind,
                    source_analysis_id=excluded.source_analysis_id,
                    source_scope=excluded.source_scope,
                    save_state=excluded.save_state,
                    generation_id=excluded.generation_id
                """,
                (
                    graph.id,
                    graph.model_dump_json(),
                    str(graph.project_id) if graph.project_id else None,
                    graph.version,
                    graph.updated_at.isoformat(),
                    graph.graph_kind,
                    graph.source_analysis_id,
                    graph.source_scope,
                    graph.save_state,
                    graph.generation_id,
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

        graph = graph.model_copy(update={"save_state": "saved"})

        def write(connection: sqlite3.Connection) -> bool:
            connection.execute("BEGIN IMMEDIATE")
            cursor = connection.execute(
                """
                UPDATE concept_graphs
                SET payload = ?, project_id = ?, version = ?, updated_at = ?,
                    graph_kind = ?, source_analysis_id = ?, source_scope = ?,
                    save_state = ?, generation_id = ?
                WHERE id = ? AND version = ?
                """,
                (
                    graph.model_dump_json(),
                    str(graph.project_id) if graph.project_id else None,
                    graph.version,
                    graph.updated_at.isoformat(),
                    graph.graph_kind,
                    graph.source_analysis_id,
                    graph.source_scope,
                    graph.save_state,
                    graph.generation_id,
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

    # ----- transient analysis graph patches ---------------------------
    def save_analysis_patch(self, analysis_id: str, patch: GraphPatch) -> GraphPatch:
        """Persist a proposal for the graph embedded in an analysis snapshot."""

        self._run(
            lambda connection: connection.execute(
                """
                INSERT INTO analysis_graph_patches(
                    id, analysis_id, payload, created_at, status, base_version
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
                    status=excluded.status, base_version=excluded.base_version
                """,
                (
                    patch.id,
                    analysis_id,
                    patch.model_dump_json(),
                    patch.created_at.isoformat(),
                    patch.status,
                    patch.base_version,
                ),
            )
        )
        return patch.model_copy(deep=True)

    def get_analysis_patch(self, analysis_id: str, patch_id: str) -> GraphPatch | None:
        def read(connection: sqlite3.Connection) -> GraphPatch | None:
            row = connection.execute(
                """
                SELECT payload FROM analysis_graph_patches
                WHERE analysis_id = ? AND id = ?
                """,
                (analysis_id, patch_id),
            ).fetchone()
            return GraphPatch.model_validate_json(row["payload"]) if row else None

        return self._run(read)

    def list_analysis_patches(self, analysis_id: str) -> list[GraphPatch]:
        def read(connection: sqlite3.Connection) -> list[GraphPatch]:
            rows = connection.execute(
                """
                SELECT payload FROM analysis_graph_patches
                WHERE analysis_id = ? ORDER BY created_at ASC
                """,
                (analysis_id,),
            ).fetchall()
            return [GraphPatch.model_validate_json(row["payload"]) for row in rows]

        return self._run(read)

    def update_analysis_and_patch_if_graph_version(
        self,
        job: AnalysisJob,
        patch: GraphPatch,
        expected_graph_version: int,
    ) -> bool:
        """Atomically mutate an embedded graph and record its reviewed patch."""

        def write(connection: sqlite3.Connection) -> bool:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT payload FROM analysis_jobs WHERE id = ?", (str(job.id),)
            ).fetchone()
            if row is None:
                connection.rollback()
                return False
            current = AnalysisJob.model_validate_json(row["payload"])
            if current.result is None or current.result.graph.version != expected_graph_version:
                connection.rollback()
                return False
            connection.execute(
                "UPDATE analysis_jobs SET payload = ?, status = ? WHERE id = ?",
                (job.model_dump_json(), job.status, str(job.id)),
            )
            connection.execute(
                """
                INSERT INTO analysis_graph_patches(
                    id, analysis_id, payload, created_at, status, base_version
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET payload=excluded.payload,
                    status=excluded.status, base_version=excluded.base_version
                """,
                (
                    patch.id,
                    str(job.id),
                    patch.model_dump_json(),
                    patch.created_at.isoformat(),
                    patch.status,
                    patch.base_version,
                ),
            )
            return True

        return bool(self._run(write))

    # ----- research-direction overview jobs --------------------------
    def save_overview(self, job: OverviewJob) -> OverviewJob:
        """Persist one complete Overview job document.

        ``result_payload`` deliberately duplicates the result portion for
        forward-compatible workers that may later stream partial graph
        snapshots.  ``payload`` remains authoritative in this version.
        """

        self._run(
            lambda connection: connection.execute(
                """
                INSERT INTO overview_jobs(
                    id, analysis_id, status, stage, progress, payload,
                    result_payload, save_state, error, created_at, updated_at,
                    version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    analysis_id=excluded.analysis_id,
                    status=excluded.status,
                    stage=excluded.stage,
                    progress=excluded.progress,
                    payload=excluded.payload,
                    result_payload=excluded.result_payload,
                    save_state=excluded.save_state,
                    error=excluded.error,
                    updated_at=excluded.updated_at,
                    version=excluded.version
                """,
                (
                    str(job.id),
                    str(job.analysis_id),
                    job.status,
                    job.stage,
                    job.progress,
                    job.model_dump_json(),
                    job.result.model_dump_json() if job.result is not None else None,
                    job.save_state,
                    job.error,
                    job.created_at.isoformat(),
                    job.updated_at.isoformat(),
                    job.version,
                ),
            )
        )
        return job.model_copy(deep=True)

    def get_overview(self, overview_id: str) -> OverviewJob | None:
        def read(connection: sqlite3.Connection) -> OverviewJob | None:
            row = connection.execute(
                "SELECT payload FROM overview_jobs WHERE id = ?", (overview_id,)
            ).fetchone()
            return OverviewJob.model_validate_json(row["payload"]) if row else None

        return self._run(read)

    def list_overviews(self, analysis_id: str | None = None) -> list[OverviewJob]:
        def read(connection: sqlite3.Connection) -> list[OverviewJob]:
            if analysis_id is None:
                rows = connection.execute(
                    "SELECT payload FROM overview_jobs ORDER BY updated_at DESC"
                ).fetchall()
            else:
                rows = connection.execute(
                    """
                    SELECT payload FROM overview_jobs
                    WHERE analysis_id = ? ORDER BY updated_at DESC
                    """,
                    (analysis_id,),
                ).fetchall()
            return [OverviewJob.model_validate_json(row["payload"]) for row in rows]

        return self._run(read)

    def mark_overview_graph_deleted(self, graph_id: str) -> list[str]:
        """Return Overview snapshots for a deleted library graph to transient.

        The Overview job is the durable history copy, just as ``analysis_jobs``
        is for a normal concept graph.  Removing the saved library row must not
        erase that history or leave it claiming that the graph is still saved.
        """

        def update(connection: sqlite3.Connection) -> list[str]:
            rows = connection.execute(
                "SELECT id, payload FROM overview_jobs"
            ).fetchall()
            changed: list[str] = []
            for row in rows:
                job = OverviewJob.model_validate_json(row["payload"])
                graph = job.result.graph if job.result is not None else None
                if job.saved_graph_id != graph_id and (graph is None or graph.id != graph_id):
                    continue
                if job.result is not None:
                    transient_graph = job.result.graph.model_copy(
                        update={"save_state": "transient"}
                    )
                    result = job.result.model_copy(update={"graph": transient_graph})
                else:
                    result = None
                job = job.model_copy(
                    update={
                        "result": result,
                        "save_state": "transient",
                        "saved_graph_id": None,
                        "updated_at": datetime.now(timezone.utc),
                        "version": job.version + 1,
                    }
                )
                connection.execute(
                    """
                    UPDATE overview_jobs SET status = ?, stage = ?, progress = ?,
                        payload = ?, result_payload = ?, save_state = ?, error = ?,
                        updated_at = ?, version = ? WHERE id = ?
                    """,
                    (
                        job.status,
                        job.stage,
                        job.progress,
                        job.model_dump_json(),
                        job.result.model_dump_json() if job.result else None,
                        job.save_state,
                        job.error,
                        job.updated_at.isoformat(),
                        job.version,
                        str(job.id),
                    ),
                )
                changed.append(str(job.id))
            return changed

        return self._run(update)

    def mark_unfinished_overviews_interrupted(self) -> int:
        """Make process-restart semantics explicit for abandoned workers."""

        def update(connection: sqlite3.Connection) -> int:
            rows = connection.execute(
                """
                SELECT id, payload FROM overview_jobs
                WHERE status IN ('queued', 'running')
                """
            ).fetchall()
            changed = 0
            for row in rows:
                job = OverviewJob.model_validate_json(row["payload"])
                job = job.model_copy(
                    update={
                        "status": "interrupted",
                        "message": "应用上次退出时任务尚未完成，可重新生成。",
                        "updated_at": datetime.now(timezone.utc),
                    }
                )
                connection.execute(
                    """
                    UPDATE overview_jobs SET status = ?, stage = ?, progress = ?,
                        payload = ?, result_payload = ?, save_state = ?, error = ?,
                        updated_at = ?, version = ? WHERE id = ?
                    """,
                    (
                        job.status,
                        job.stage,
                        job.progress,
                        job.model_dump_json(),
                        job.result.model_dump_json() if job.result else None,
                        job.save_state,
                        job.error,
                        job.updated_at.isoformat(),
                        job.version,
                        str(job.id),
                    ),
                )
                changed += 1
            return changed

        return int(self._run(update))

    @staticmethod
    def _decode_graph(row: sqlite3.Row) -> ConceptGraph:
        """Decode a graph row while preserving pre-lifecycle snapshots.

        Before the transient/saved lifecycle existed, every graph row was a
        durable graph.  If its JSON payload has no ``save_state`` field, the
        indexed column (whose migration default is ``saved``) supplies the
        compatibility value explicitly.
        """

        payload = json.loads(row["payload"])
        if "graph_kind" not in payload:
            payload["graph_kind"] = row["graph_kind"] if "graph_kind" in row.keys() else "concept_network"
        if "source_scope" not in payload:
            payload["source_scope"] = (
                row["source_scope"] if "source_scope" in row.keys() else "metadata_abstract"
            )
        if "save_state" not in payload:
            payload["save_state"] = row["save_state"] if "save_state" in row.keys() else "saved"
        if "source_analysis_id" not in payload and "source_analysis_id" in row.keys():
            payload["source_analysis_id"] = row["source_analysis_id"]
        if "generation_id" not in payload and "generation_id" in row.keys():
            payload["generation_id"] = row["generation_id"]
        return ConceptGraph.model_validate(payload)

    @staticmethod
    def _decode_analysis(payload_text: str) -> AnalysisJob:
        """Decode an analysis and mark legacy auto-saved graphs as saved."""

        payload = json.loads(payload_text)
        result = payload.get("result")
        if isinstance(result, dict):
            graph = result.get("graph")
            if isinstance(graph, dict):
                # New snapshots always include both fields.  Missing fields
                # identify a pre-lifecycle analysis whose generated graph was
                # automatically persisted in ``concept_graphs``.
                if "save_state" not in graph:
                    graph["save_state"] = "saved"
                if "graph_save_state" not in result:
                    result["graph_save_state"] = graph.get("save_state", "saved")
                if result.get("graph_save_state") == "saved" and not result.get(
                    "saved_graph_id"
                ):
                    result["saved_graph_id"] = graph.get("id")
        return AnalysisJob.model_validate(payload)

    def clear_projects(self) -> None:
        self._run(lambda connection: connection.execute("DELETE FROM projects"))

    def clear_graphs(self) -> None:
        """Clear graph documents and their patch history only."""

        def clear(connection: sqlite3.Connection) -> None:
            connection.execute("DELETE FROM analysis_graph_patches")
            connection.execute("DELETE FROM graph_patches")
            connection.execute("DELETE FROM concept_graphs")

        self._run(clear)

    def clear_research(self) -> None:
        def clear(connection: sqlite3.Connection) -> None:
            connection.execute("DELETE FROM analysis_graph_patches")
            connection.execute("DELETE FROM graph_patches")
            connection.execute("DELETE FROM concept_graphs")
            connection.execute("DELETE FROM analysis_jobs")
            connection.execute("DELETE FROM overview_jobs")
            connection.execute("DELETE FROM idea_checks")
            connection.execute("DELETE FROM experiment_plans")

        self._run(clear)

    def clear(self) -> None:
        """Clear every persisted MVP object; intended for tests and local reset."""

        def clear_all(connection: sqlite3.Connection) -> None:
            connection.execute("DELETE FROM analysis_graph_patches")
            connection.execute("DELETE FROM graph_patches")
            connection.execute("DELETE FROM concept_graphs")
            connection.execute("DELETE FROM analysis_jobs")
            connection.execute("DELETE FROM overview_jobs")
            connection.execute("DELETE FROM idea_checks")
            connection.execute("DELETE FROM experiment_plans")
            connection.execute("DELETE FROM projects")

        self._run(clear_all)

    def close(self) -> None:
        """Close a persistent in-memory connection, if one is open."""

        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None


storage = Storage()
