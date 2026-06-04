import asyncio
import os
import sqlite3
import threading
from typing import Optional

DB_NAME = os.getenv("BRAINFORGE_DB", "brain_memory.db")


class DatabaseManager:
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
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                expression  TEXT,
                universe    TEXT,
                decay       INTEGER,
                alpha_id    TEXT,
                generation  INTEGER,
                sharpe      REAL,
                turnover    REAL,
                fitness     REAL,
                ast_depth   INTEGER,
                is_tuned    BOOLEAN DEFAULT 0,
                timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(expression, universe, decay)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS vector_memory (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expression TEXT UNIQUE,
                vector_blob TEXT
            )
            """
        )

    @staticmethod
    def _save_alpha(conn, expression, universe, decay, alpha_id, gen, sharpe, turnover, fitness, depth, is_tuned=0):
        conn.execute(
            """
            INSERT OR IGNORE INTO alpha_population
                (expression, universe, decay, alpha_id, generation, sharpe, turnover, fitness, ast_depth, is_tuned)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (expression, universe, decay, alpha_id, gen, sharpe, turnover, fitness, depth, is_tuned),
        )

    @staticmethod
    def _get_top_population(conn, limit: int = 150):
        cursor = conn.execute(
            """
            SELECT expression, universe, decay, sharpe, turnover, ast_depth
            FROM alpha_population
            WHERE sharpe > 0.5 AND turnover < 0.8
            ORDER BY sharpe DESC LIMIT ?
            """,
            (limit,),
        )
        return cursor.fetchall()

    @staticmethod
    def _load_history(conn):
        cursor = conn.execute("SELECT expression, universe, decay, sharpe FROM alpha_population")
        return cursor.fetchall()

    def _sync_connection(self) -> sqlite3.Connection:
        if self._sync_conn is None:
            self._sync_conn = self._new_connection()
        return self._sync_conn

    def init_db_sync(self):
        with self._sync_lock:
            self._init_schema(self._sync_connection())

    def save_alpha_sync(self, expression, universe, decay, alpha_id, gen, sharpe, turnover, fitness, depth, is_tuned=0):
        with self._sync_lock:
            self._save_alpha(
                self._sync_connection(),
                expression, universe, decay, alpha_id, gen, sharpe, turnover, fitness, depth, is_tuned,
            )

    def get_top_population_sync(self, limit=150):
        with self._sync_lock:
            return self._get_top_population(self._sync_connection(), limit)

    def load_history_sync(self):
        with self._sync_lock:
            return self._load_history(self._sync_connection())

    def close_sync(self):
        with self._sync_lock:
            if self._sync_conn is not None:
                self._sync_conn.close()
                self._sync_conn = None

    async def init_db(self):
        await asyncio.to_thread(self.init_db_sync)

    async def save_alpha(self, expression, universe, decay, alpha_id, gen, sharpe, turnover, fitness, depth, is_tuned=0):
        await asyncio.to_thread(self.save_alpha_sync, expression, universe, decay, alpha_id, gen, sharpe, turnover, fitness, depth, is_tuned)

    async def get_top_population(self, limit=150):
        return await asyncio.to_thread(self.get_top_population_sync, limit)

    async def load_history(self):
        return await asyncio.to_thread(self.load_history_sync)

    async def close(self):
        await asyncio.to_thread(self.close_sync)


_DEFAULT_DB = DatabaseManager()


def init_db():
    _DEFAULT_DB.init_db_sync()


def save_alpha(expression, universe, decay, alpha_id, gen, sharpe, turnover, fitness, depth, is_tuned=0):
    _DEFAULT_DB.save_alpha_sync(expression, universe, decay, alpha_id, gen, sharpe, turnover, fitness, depth, is_tuned)


def get_top_population(limit=150):
    return _DEFAULT_DB.get_top_population_sync(limit)
