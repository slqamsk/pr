"""Экспорт всех данных приложения в JSON-файл."""
import json
import sqlite3
from datetime import datetime
from pathlib import Path

from db import db, db_init

EXPORT_SCHEMA_VERSION = 1
APP_NAME = "pr_v01"

# Порядок таблиц в JSON. Здесь же — источник истины по набору таблиц.
# (имя, ключ_сортировки | None)
_TABLES = [
    ("roles",           "id"),
    ("subroles",        "id"),
    ("macro_sprints",   "id"),
    ("sprints",         "id"),
    ("epics",           "id"),
    ("tasks",           "id"),
    ("actions",         "id"),
    ("statuses",        "id"),
    ("action_statuses", "id"),
    ("p1_levels",       "id"),
    ("settings",        "key"),
]


def default_filename() -> str:
    """pr_v01_export_2026-10-02_152311.json"""
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    return f"{APP_NAME}_export_{stamp}.json"


def default_dir() -> Path:
    """Папка data/ — рядом с БД."""
    return db_init.DATA_DIR


def export_to_json(path) -> Path:
    """
    Выгружает все таблицы в JSON. Возвращает фактический путь файла.
    Может бросить OSError, если файл нельзя записать.
    """
    path = Path(path)

    tables_data: dict[str, list[dict]] = {}
    counts: dict[str, int] = {}

    with db.cursor() as con:
        for table, order_key in _TABLES:
            sql = f"SELECT * FROM {table}"
            if order_key:
                sql += f" ORDER BY {order_key}"
            rows = con.execute(sql).fetchall()
            tables_data[table] = [dict(r) for r in rows]
            counts[table] = len(rows)

    payload = {
        "meta": {
            "exported_at": datetime.now().isoformat(timespec="seconds"),
            "schema_version": EXPORT_SCHEMA_VERSION,
            "app_name": APP_NAME,
            "db_path": str(db_init.DB_PATH),
            "table_counts": counts,
        },
        "tables": tables_data,
    }

    # атомарная запись: во временный файл → переименование
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    tmp.replace(path)
    return path