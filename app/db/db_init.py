"""Проверка и создание файла БД. Пути считаются от расположения файла."""
import sqlite3
from pathlib import Path

BASE_DIR    = Path(__file__).resolve().parent.parent
DATA_DIR    = BASE_DIR / "data"
DB_PATH     = DATA_DIR / "pr_v01.db"
SCHEMA_PATH = Path(__file__).resolve().parent / "pr_v01_db_schema.sql"

DEFAULT_ROLES = [
    (1, "Управляющий жизнью"),
    (2, "Управляющий здоровьем"),
    (3, "Финансовый обеспечитель"),
    (4, "Ведущий хозяйство"),
    (5, "Творец / Создатель"),
    (6, "Сын"),
    (7, "Муж и отец"),
]

DEFAULT_STATUSES = [
    (1, "Backlog"),
    (2, "Active"),
    (3, "Passed"),
    (4, "Failed"),
]

DEFAULT_P1_LEVELS = [
    (1, "A"),
    (2, "B"),
    (3, "C"),
    (4, "D"),
    (5, "E"),
]

DEFAULT_ACTION_STATUSES = [
    (1, "В работе"),
    (2, "Начал задачу"),
    (3, "Продолжил задачу"),
    (4, "Завершил задачу"),
    (5, "Без задачи"),
]

DEFAULT_CRITERION_STATUSES = [
    (1, "Passed"),
    (2, "Failed"),
    (3, "Partially Passed"),
]

_ROLES_INIT_FLAG              = "roles.initialized"
_STATUSES_INIT_FLAG           = "statuses.initialized"
_P1_INIT_FLAG                 = "p1_levels.initialized"
_ACTION_STATUSES_INIT_FLAG    = "action_statuses.initialized"
_CRITERION_STATUSES_INIT_FLAG = "criterion_statuses.initialized"
_POMODORO_KEY                 = "pomodoro.per_day"
_POMODORO_DEFAULT             = "8"


def db_exists() -> bool:
    return DB_PATH.is_file()


def _seed_once(con, flag_key, table, default_rows):
    row = con.execute("SELECT value FROM settings WHERE key = ?", (flag_key,)).fetchone()
    if row is not None:
        return
    n = con.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    if n == 0:
        con.executemany(f"INSERT INTO {table}(id, name) VALUES (?, ?)", default_rows)
    con.execute("INSERT INTO settings(key, value) VALUES (?, '1')", (flag_key,))


def _seed_setting_default(con, key, default_value):
    row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
    if row is None:
        con.execute("INSERT INTO settings(key, value) VALUES (?, ?)",
                    (key, default_value))


def _column_names(con, table: str) -> list[str]:
    return [r[1] for r in con.execute(f"PRAGMA table_info({table})").fetchall()]


def _migrate(con: sqlite3.Connection) -> None:
    """Добавляет новые колонки к уже существующим таблицам
    и создаёт индексы, которые от них зависят."""
    # tasks.pf — сначала колонка, потом индекс
    if "pf" not in _column_names(con, "tasks"):
        con.execute("ALTER TABLE tasks ADD COLUMN pf REAL")
    con.execute("CREATE INDEX IF NOT EXISTS idx_tasks_pf ON tasks(pf)")


def _apply_schema(con: sqlite3.Connection) -> None:
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    con.executescript(schema)
    _migrate(con)
    _seed_once(con, _ROLES_INIT_FLAG,              "roles",              DEFAULT_ROLES)
    _seed_once(con, _STATUSES_INIT_FLAG,           "statuses",           DEFAULT_STATUSES)
    _seed_once(con, _P1_INIT_FLAG,                 "p1_levels",          DEFAULT_P1_LEVELS)
    _seed_once(con, _ACTION_STATUSES_INIT_FLAG,    "action_statuses",    DEFAULT_ACTION_STATUSES)
    _seed_once(con, _CRITERION_STATUSES_INIT_FLAG, "criterion_statuses", DEFAULT_CRITERION_STATUSES)
    _seed_setting_default(con, _POMODORO_KEY, _POMODORO_DEFAULT)


def create_empty_db() -> None:
    DATA_DIR.mkdir(exist_ok=True)
    con = sqlite3.connect(DB_PATH)
    try:
        _apply_schema(con)
        con.commit()
    finally:
        con.close()


def ensure_db() -> None:
    if not DB_PATH.is_file():
        return
    con = sqlite3.connect(DB_PATH)
    try:
        _apply_schema(con)
        con.commit()
    finally:
        con.close()