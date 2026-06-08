import asyncio
import os
import sqlite3
import threading
from typing import Optional

DB_NAME = os.getenv("BRAINFORGE_DB", "brain_memory.db")

# Columns selected for resume / history. Keep this in one place so every query
# and every consumer agrees on column order.
_POPULATION_COLUMNS = (
    "expression", "universe", "decay", "sharpe", "turnover",
    "ast_depth", "skew", "kurtosis", "track_record_length",
    "max_correlation", "alpha_id", "fitness",
    "returns", "oos_sharpe", "is_qualified",
)


class DatabaseManager:
    """Single owner of the SQLite connection.

    All access goes through this class (sync helpers for one-off scripts, async
    wrappers for the orchestrator). There is intentionally no module-level
    singleton so we never end up with two connections to the same WAL file.
    """

    def __init__(self, db_name: str = DB_NAME):
        self.db_name = db_name
        self._sync_conn: Optional[sqlite3.Connection] = None
        self._sync_lock = threading.RLock()

    def _new_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_name, timeout=30, isolation_level=None, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    @staticmethod
    def _init_schema(conn: sqlite3.Connection):
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS alpha_population (
                id                   INTEGER PRIMARY KEY AUTOINCREMENT,
                expression           TEXT,
                universe             TEXT,
                decay                INTEGER,
                alpha_id             TEXT,
                generation           INTEGER,
                sharpe               REAL,
                turnover             REAL,
                fitness              REAL,
                ast_depth            INTEGER,
                skew                 REAL,
                kurtosis             REAL,
                track_record_length  INTEGER,
                max_correlation      REAL,
                returns              REAL,
                oos_sharpe           REAL,
                is_qualified         INTEGER DEFAULT 0,
                failed_checks        TEXT,
                is_tuned             BOOLEAN DEFAULT 0,
                timestamp            DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(expression, universe, decay)
            )
            """
        )
        # OPTIMIZATION: Add indexes for fast queries
        conn.execute("CREATE INDEX IF NOT EXISTS idx_qualified ON alpha_population(is_qualified) WHERE is_qualified = 1")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_sharpe ON alpha_population(sharpe DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_fitness ON alpha_population(fitness DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_generation ON alpha_population(generation)")
        DatabaseManager._migrate_schema(conn)

    @staticmethod
    def _migrate_schema(conn: sqlite3.Connection):
        # Idempotently add columns introduced after the original schema so an
        # existing brain_memory.db keeps working without a manual rebuild.
        existing = {row[1] for row in conn.execute("PRAGMA table_info(alpha_population)")}
        migrations = (
            ("returns", "ALTER TABLE alpha_population ADD COLUMN returns REAL"),
            ("oos_sharpe", "ALTER TABLE alpha_population ADD COLUMN oos_sharpe REAL"),
            ("is_qualified", "ALTER TABLE alpha_population ADD COLUMN is_qualified INTEGER DEFAULT 0"),
            ("failed_checks", "ALTER TABLE alpha_population ADD COLUMN failed_checks TEXT"),
        )
        for column, ddl in migrations:
            if column not in existing:
                conn.execute(ddl)

    # --- low-level (assume lock held / single thread) ------------------------
    @staticmethod
    def _save_alpha(conn, expression, universe, decay, alpha_id, gen, sharpe,
                    turnover, fitness, depth, skew, kurtosis,
                    track_record_length, max_correlation, is_tuned=0,
                    returns=0.0, oos_sharpe=None, is_qualified=0,
                    failed_checks=""):
        # Upsert: keep the BETTER-OR-EQUAL result on conflict. ">" alone would
        # drop the batch ENRICHMENT pass in the orchestrator: each simulation is
        # first saved raw (real sharpe, fitness/is_qualified/max_correlation still
        # blank) the instant it completes -- so a completed WorldQuant simulation
        # is durable even if the run is interrupted mid-generation -- and then
        # re-saved with the SAME sharpe plus the computed fitness/qualification
        # once the generation's batch finishes. ">=" lets that equal-sharpe
        # enrichment overwrite while still keeping a later, genuinely better
        # simulation and never regressing to a failure/placeholder (NULL existing
        # sharpe is treated as -inf so the first real score always wins).
        conn.execute(
            """
            INSERT INTO alpha_population
                (expression, universe, decay, alpha_id, generation, sharpe,
                 turnover, fitness, ast_depth, skew, kurtosis,
                 track_record_length, max_correlation, is_tuned,
                 returns, oos_sharpe, is_qualified, failed_checks)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(expression, universe, decay) DO UPDATE SET
                alpha_id            = excluded.alpha_id,
                generation          = excluded.generation,
                sharpe              = excluded.sharpe,
                turnover            = excluded.turnover,
                fitness             = excluded.fitness,
                ast_depth           = excluded.ast_depth,
                skew                = excluded.skew,
                kurtosis            = excluded.kurtosis,
                track_record_length = excluded.track_record_length,
                max_correlation     = excluded.max_correlation,
                is_tuned            = excluded.is_tuned,
                returns             = excluded.returns,
                oos_sharpe          = excluded.oos_sharpe,
                is_qualified        = excluded.is_qualified,
                failed_checks       = excluded.failed_checks,
                timestamp           = CURRENT_TIMESTAMP
            WHERE excluded.sharpe >= COALESCE(alpha_population.sharpe, -1e18)
            """,
            (expression, universe, decay, alpha_id, gen, sharpe, turnover,
             fitness, depth, skew, kurtosis, track_record_length,
             max_correlation, is_tuned, returns, oos_sharpe, is_qualified,
             failed_checks),
        )

    @staticmethod
    def _insert_seed(conn, expression, universe, decay):
        # Seeds are stored UNSCORED (sharpe NULL) so the engine must actually
        # simulate them before trusting them. Never fabricate metrics here.
        conn.execute(
            """
            INSERT OR IGNORE INTO alpha_population
                (expression, universe, decay, alpha_id, generation, sharpe,
                 turnover, fitness, ast_depth, is_tuned)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (expression, universe, decay, "MANUAL_SEED", 0, None, None, None, None, 0),
        )

    @staticmethod
    def _get_top_population(conn, limit: int = 150):
        cursor = conn.execute(
            f"""
            SELECT {', '.join(_POPULATION_COLUMNS)}
            FROM alpha_population
            WHERE sharpe IS NOT NULL AND sharpe > 0.5 AND turnover < 0.8
            ORDER BY fitness DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cursor.fetchall()

    @staticmethod
    def _load_history(conn):
        cursor = conn.execute(
            """
            SELECT expression, universe, decay, sharpe, turnover, skew, kurtosis,
                   track_record_length, alpha_id
            FROM alpha_population
            WHERE sharpe IS NOT NULL
            """
        )
        return cursor.fetchall()

    @staticmethod
    def _count_trials(conn) -> int:
        cursor = conn.execute(
            "SELECT COUNT(*) FROM alpha_population WHERE sharpe IS NOT NULL"
        )
        row = cursor.fetchone()
        return int(row[0]) if row else 0

    @staticmethod
    def _get_submission_candidates(conn, min_sharpe, max_turnover, max_correlation,
                                   min_turnover=0.0):
        # turnover >= min_turnover enforces WorldQuant's HARD submittable floor
        # (BRAIN rejects sub-~1% turnover). Belt-and-suspenders alongside the
        # orchestrator's qualification gate: it also screens out any legacy rows
        # that were marked qualified before the floor existed.
        cursor = conn.execute(
            """
            SELECT expression, alpha_id, sharpe, turnover, fitness, max_correlation
            FROM alpha_population
            WHERE is_qualified = 1
              AND sharpe >= ? AND turnover <= ? AND turnover >= ?
              AND alpha_id IS NOT NULL AND alpha_id != '' AND alpha_id != 'MANUAL_SEED'
              AND (max_correlation IS NULL OR max_correlation <= ?)
              AND (failed_checks IS NULL OR failed_checks = '')
            ORDER BY fitness DESC
            """,
            (min_sharpe, max_turnover, min_turnover, max_correlation),
        )
        return cursor.fetchall()

    @staticmethod
    def _get_top_for_review(conn, limit: int = 10):
        cursor = conn.execute(
            """
            SELECT expression, sharpe, turnover, fitness, ast_depth,
                   max_correlation, is_tuned
            FROM alpha_population
            WHERE sharpe IS NOT NULL
            ORDER BY fitness DESC
            LIMIT ?
            """,
            (limit,),
        )
        return cursor.fetchall()

    def _sync_connection(self) -> sqlite3.Connection:
        if self._sync_conn is None:
            self._sync_conn = self._new_connection()
        return self._sync_conn

    # --- sync API (for standalone scripts) -----------------------------------
    def init_db_sync(self):
        with self._sync_lock:
            self._init_schema(self._sync_connection())

    def save_alpha_sync(self, expression, universe, decay, alpha_id, gen, sharpe,
                        turnover, fitness, depth, skew=0.0, kurtosis=3.0,
                        track_record_length=None, max_correlation=None, is_tuned=0,
                        returns=0.0, oos_sharpe=None, is_qualified=0,
                        failed_checks=""):
        with self._sync_lock:
            self._save_alpha(
                self._sync_connection(), expression, universe, decay, alpha_id,
                gen, sharpe, turnover, fitness, depth, skew, kurtosis,
                track_record_length, max_correlation, is_tuned,
                returns, oos_sharpe, is_qualified, failed_checks,
            )

    def insert_seed_sync(self, expression, universe, decay):
        with self._sync_lock:
            self._insert_seed(self._sync_connection(), expression, universe, decay)

    def get_top_population_sync(self, limit=150):
        with self._sync_lock:
            return self._get_top_population(self._sync_connection(), limit)

    def load_history_sync(self):
        with self._sync_lock:
            return self._load_history(self._sync_connection())

    def count_trials_sync(self):
        with self._sync_lock:
            return self._count_trials(self._sync_connection())

    def get_submission_candidates_sync(self, min_sharpe, max_turnover, max_correlation,
                                       min_turnover=0.0):
        with self._sync_lock:
            return self._get_submission_candidates(
                self._sync_connection(), min_sharpe, max_turnover, max_correlation,
                min_turnover,
            )

    def get_top_for_review_sync(self, limit=10):
        with self._sync_lock:
            return self._get_top_for_review(self._sync_connection(), limit)

    def close_sync(self):
        with self._sync_lock:
            if self._sync_conn is not None:
                self._sync_conn.close()
                self._sync_conn = None

    # --- async API (for the orchestrator) ------------------------------------
    async def init_db(self):
        await asyncio.to_thread(self.init_db_sync)

    async def save_alpha(self, expression, universe, decay, alpha_id, gen, sharpe,
                         turnover, fitness, depth, skew=0.0, kurtosis=3.0,
                         track_record_length=None, max_correlation=None, is_tuned=0,
                         returns=0.0, oos_sharpe=None, is_qualified=0,
                         failed_checks=""):
        await asyncio.to_thread(
            self.save_alpha_sync, expression, universe, decay, alpha_id, gen,
            sharpe, turnover, fitness, depth, skew, kurtosis,
            track_record_length, max_correlation, is_tuned,
            returns, oos_sharpe, is_qualified, failed_checks,
        )

    async def get_top_population(self, limit=150):
        return await asyncio.to_thread(self.get_top_population_sync, limit)

    async def load_history(self):
        return await asyncio.to_thread(self.load_history_sync)

    async def count_trials(self):
        return await asyncio.to_thread(self.count_trials_sync)

    async def close(self):
        await asyncio.to_thread(self.close_sync)