"""SQLite event log for past game runs."""

import sqlite3
from datetime import datetime

from graphcabs.config import DB_FILE


def _connect():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with _connect() as conn:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS game_runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TEXT NOT NULL,
                ended_at TEXT,
                days_reached INTEGER NOT NULL DEFAULT 1,
                days_completed INTEGER NOT NULL DEFAULT 0,
                total_earned REAL NOT NULL DEFAULT 0,
                final_money REAL,
                rides_completed INTEGER NOT NULL DEFAULT 0,
                rides_missed INTEGER NOT NULL DEFAULT 0,
                fleet_size INTEGER NOT NULL DEFAULT 2,
                end_reason TEXT
            );
            CREATE TABLE IF NOT EXISTS day_summaries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                run_id INTEGER NOT NULL,
                day INTEGER NOT NULL,
                earned REAL NOT NULL,
                completed INTEGER NOT NULL,
                missed INTEGER NOT NULL,
                FOREIGN KEY (run_id) REFERENCES game_runs(id)
            );
            """
        )


def start_game_run():
    with _connect() as conn:
        cur = conn.execute(
            "INSERT INTO game_runs (started_at, days_reached) VALUES (?, 1)",
            (datetime.now().isoformat(timespec="seconds"),),
        )
        return cur.lastrowid


def log_day_summary(run_id, day, earned, completed, missed):
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO day_summaries (run_id, day, earned, completed, missed)
            VALUES (?, ?, ?, ?, ?)
            """,
            (run_id, day, earned, completed, missed),
        )


def finish_game_run(
    run_id,
    *,
    days_reached,
    days_completed,
    total_earned,
    final_money,
    rides_completed,
    rides_missed,
    fleet_size,
    end_reason,
):
    with _connect() as conn:
        conn.execute(
            """
            UPDATE game_runs SET
                ended_at = ?,
                days_reached = ?,
                days_completed = ?,
                total_earned = ?,
                final_money = ?,
                rides_completed = ?,
                rides_missed = ?,
                fleet_size = ?,
                end_reason = ?
            WHERE id = ?
            """,
            (
                datetime.now().isoformat(timespec="seconds"),
                days_reached,
                days_completed,
                total_earned,
                final_money,
                rides_completed,
                rides_missed,
                fleet_size,
                end_reason,
                run_id,
            ),
        )


def fetch_game_runs(limit=30):
    with _connect() as conn:
        rows = conn.execute(
            """
            SELECT * FROM game_runs
            WHERE ended_at IS NOT NULL
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]


def fetch_totals():
    with _connect() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS games,
                COALESCE(MAX(days_completed), 0) AS best_days,
                COALESCE(MAX(total_earned), 0) AS best_earned,
                COALESCE(SUM(total_earned), 0) AS all_earned,
                COALESCE(SUM(rides_completed), 0) AS all_rides
            FROM game_runs
            WHERE ended_at IS NOT NULL
            """
        ).fetchone()
        return dict(row) if row else {}
