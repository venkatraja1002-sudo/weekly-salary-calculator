import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

DB_PATH = Path(__file__).parent / "data.db"

def conn():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with conn() as c:
        c.execute("""
        CREATE TABLE IF NOT EXISTS workers (
          id TEXT PRIMARY KEY,
          name TEXT NOT NULL,
          phone TEXT DEFAULT '',
          daily_rate REAL NOT NULL
        )
        """)
        c.execute("""
        CREATE TABLE IF NOT EXISTS weeks (
          id TEXT PRIMARY KEY,
          worker_id TEXT NOT NULL,
          week_start TEXT NOT NULL,
          days_json TEXT NOT NULL,
          ot_hours REAL NOT NULL,
          ot_rate REAL,
          bonus REAL NOT NULL,
          deduction REAL NOT NULL,
          total_salary REAL NOT NULL,
          breakdown_json TEXT NOT NULL,
          status TEXT NOT NULL DEFAULT 'UNPAID',
          updated_at TEXT NOT NULL,
          UNIQUE(worker_id, week_start)
        )
        """)
        c.commit()

def list_workers() -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute("SELECT id, name, phone, daily_rate FROM workers ORDER BY name").fetchall()
    return [{"id": r["id"], "name": r["name"], "phone": r["phone"], "dailyRate": r["daily_rate"]} for r in rows]

def add_worker(worker_id: str, name: str, phone: str, daily_rate: float):
    with conn() as c:
        c.execute("INSERT INTO workers(id, name, phone, daily_rate) VALUES(?,?,?,?)",
                  (worker_id, name, phone, float(daily_rate)))
        c.commit()

def delete_worker(worker_id: str):
    with conn() as c:
        c.execute("DELETE FROM weeks WHERE worker_id = ?", (worker_id,))
        c.execute("DELETE FROM workers WHERE id = ?", (worker_id,))
        c.commit()

def upsert_week(record: Dict[str, Any]):
    with conn() as c:
        c.execute("""
        INSERT INTO weeks(
          id, worker_id, week_start, days_json, ot_hours, ot_rate, bonus, deduction,
          total_salary, breakdown_json, status, updated_at
        ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(worker_id, week_start) DO UPDATE SET
          days_json=excluded.days_json,
          ot_hours=excluded.ot_hours,
          ot_rate=excluded.ot_rate,
          bonus=excluded.bonus,
          deduction=excluded.deduction,
          total_salary=excluded.total_salary,
          breakdown_json=excluded.breakdown_json,
          status=excluded.status,
          updated_at=excluded.updated_at
        """, (
            record["id"], record["workerId"], record["weekStartDate"],
            record["daysJson"], record["otHours"], record["otRate"],
            record["bonus"], record["deduction"], record["totalSalary"],
            record["breakdownJson"], record["status"], record["updatedAt"]
        ))
        c.commit()

def list_weeks(worker_id: str) -> List[Dict[str, Any]]:
    with conn() as c:
        rows = c.execute("""
          SELECT id, worker_id, week_start, days_json, ot_hours, ot_rate, bonus, deduction,
                 total_salary, breakdown_json, status, updated_at
          FROM weeks WHERE worker_id = ?
          ORDER BY week_start DESC
        """, (worker_id,)).fetchall()

    out = []
    for r in rows:
        out.append({
            "id": r["id"],
            "workerId": r["worker_id"],
            "weekStartDate": r["week_start"],
            "daysJson": r["days_json"],
            "otHours": r["ot_hours"],
            "otRate": r["ot_rate"],
            "bonus": r["bonus"],
            "deduction": r["deduction"],
            "totalSalary": r["total_salary"],
            "breakdownJson": r["breakdown_json"],
            "status": r["status"],
            "updatedAt": r["updated_at"],
        })
    return out