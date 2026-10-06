"""Импорт данных из JSON-файла в текущую БД."""
import json
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

from db import db, db_init
from db.export import EXPORT_SCHEMA_VERSION, APP_NAME


class ImportValidationError(Exception):
    """Ошибка валидации файла — импорт не начат."""
    pass


class ImportPreflightError(Exception):
    """Импорт не может быть начат (бэкап не удался, нет доступа и т.п.)."""
    pass


_DELETE_ORDER = [
    "actions",
    "tasks",
    "epics",
    "macro_sprint_criteria",
    "sprint_criteria",
    "sprints",
    "macro_sprints",
    "subroles",
    "roles",
    "settings",
    "p1_levels",
    "action_statuses",
    "criterion_statuses",
    "statuses",
]

_INSERT_ORDER = [
    "statuses",
    "action_statuses",
    "criterion_statuses",
    "p1_levels",
    "roles",
    "subroles",
    "macro_sprints",
    "sprints",
    "macro_sprint_criteria",
    "sprint_criteria",
    "epics",
    "tasks",
    "actions",
    "settings",
]

# Таблицы, которых не было в schema_version=1 — при импорте старого
# файла считаем их пустыми.
_OPTIONAL_TABLES = {
    "criterion_statuses",
    "macro_sprint_criteria",
    "sprint_criteria",
}

_EXPECTED_TABLES = set(_INSERT_ORDER) - _OPTIONAL_TABLES

_FK_CHECKS = [
    ("subroles",                "role_id",         "roles",             "id",   False),
    ("macro_sprints",           "status_id",       "statuses",          "id",   False),
    ("sprints",                 "status_id",       "statuses",          "id",   False),
    ("sprints",                 "macro_sprint_id", "macro_sprints",     "id",   True),
    ("epics",                   "role_id",         "roles",             "id",   True),
    ("epics",                   "subrole_id",      "subroles",          "id",   True),
    ("epics",                   "status_id",       "statuses",          "id",   False),
    ("epics",                   "macro_sprint_id", "macro_sprints",     "id",   True),
    ("tasks",                   "epic_id",         "epics",             "id",   True),
    ("tasks",                   "role_id",         "roles",             "id",   True),
    ("tasks",                   "subrole_id",      "subroles",          "id",   True),
    ("tasks",                   "status_id",       "statuses",          "id",   False),
    ("tasks",                   "macro_sprint_id", "macro_sprints",     "id",   True),
    ("tasks",                   "sprint_id",       "sprints",           "id",   True),
    ("actions",                 "task_id",         "tasks",             "id",   True),
    ("actions",                 "epic_id",         "epics",             "id",   True),
    ("actions",                 "role_id",         "roles",             "id",   True),
    ("actions",                 "subrole_id",      "subroles",          "id",   True),
    ("actions",                 "status_id",       "action_statuses",   "id",   False),
    ("macro_sprint_criteria",   "macro_sprint_id", "macro_sprints",     "id",   False),
    ("macro_sprint_criteria",   "status_id",       "criterion_statuses","id",   True),
    ("sprint_criteria",         "sprint_id",       "sprints",           "id",   False),
    ("sprint_criteria",         "status_id",       "criterion_statuses","id",   True),
]

_P1_CHECK = ("tasks", "p1", "p1_levels", "name", True)


def _load_payload(path) -> dict:
    path = Path(path)
    if not path.is_file():
        raise ImportValidationError(f"Файл не найден: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise ImportValidationError(f"Некорректный JSON: {e}")
    except OSError as e:
        raise ImportValidationError(f"Не удалось прочитать файл: {e}")

    if not isinstance(data, dict):
        raise ImportValidationError("Корень JSON должен быть объектом.")

    if "meta" not in data or not isinstance(data["meta"], dict):
        raise ImportValidationError("Файл без шапки meta — импорт отклонён.")

    if "tables" not in data or not isinstance(data["tables"], dict):
        raise ImportValidationError("В файле отсутствует раздел tables.")

    return data


def _validate_structure(tables: dict) -> None:
    missing = _EXPECTED_TABLES - set(tables.keys())
    if missing:
        raise ImportValidationError(
            "В файле отсутствуют таблицы: " + ", ".join(sorted(missing))
        )
    for tname, rows in tables.items():
        if not isinstance(rows, list):
            raise ImportValidationError(f"tables.{tname} должен быть списком.")
        for i, row in enumerate(rows):
            if not isinstance(row, dict):
                raise ImportValidationError(
                    f"tables.{tname}[{i}] должен быть объектом."
                )


def _validate_fk(tables: dict) -> None:
    values_by_col: dict[tuple[str, str], set] = {}

    def _collect(table: str, column: str):
        key = (table, column)
        if key in values_by_col:
            return
        rows = tables.get(table, [])
        values_by_col[key] = {r.get(column) for r in rows if column in r}

    checks = list(_FK_CHECKS) + [_P1_CHECK]
    for src_tbl, src_col, dst_tbl, dst_col, nullable in checks:
        if src_tbl not in tables or dst_tbl not in tables:
            continue
        _collect(dst_tbl, dst_col)
        target_values = values_by_col[(dst_tbl, dst_col)]
        for i, row in enumerate(tables[src_tbl]):
            val = row.get(src_col, None)
            if val is None:
                if not nullable:
                    raise ImportValidationError(
                        f"{src_tbl}[{i}].{src_col} обязателен, но в файле пусто."
                    )
                continue
            if val not in target_values:
                raise ImportValidationError(
                    f"{src_tbl}[{i}].{src_col} = {val!r} ссылается на несуществующий "
                    f"{dst_tbl}.{dst_col}."
                )


def _make_backup() -> Path:
    if not db_init.DB_PATH.is_file():
        raise ImportPreflightError(
            f"Файл БД не найден: {db_init.DB_PATH}"
        )
    backup_dir = db_init.DATA_DIR / "backup"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y-%m-%d_%H%M%S")
    target = backup_dir / f"pr_v01_backup_{stamp}.db"
    try:
        shutil.copy2(db_init.DB_PATH, target)
    except OSError as e:
        raise ImportPreflightError(f"Не удалось создать бэкап: {e}")
    return target


def _table_columns(con: sqlite3.Connection, table: str) -> dict[str, dict]:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    info = {}
    for r in rows:
        name = r["name"]
        notnull = bool(r["notnull"]) and r["pk"] == 0
        has_default = r["dflt_value"] is not None
        info[name] = {
            "notnull":     notnull,
            "has_default": has_default,
            "pk":          r["pk"] == 1,
        }
    return info


def _insert_rows(con: sqlite3.Connection, table: str,
                 rows: list[dict], strict: bool) -> int:
    if not rows:
        return 0

    cols_info = _table_columns(con, table)

    union_keys = set()
    for r in rows:
        union_keys.update(r.keys())

    extra = union_keys - set(cols_info.keys())
    if strict and extra:
        raise ImportValidationError(
            f"{table}: в файле есть неизвестные колонки: {sorted(extra)}"
        )

    required = {c for c, meta in cols_info.items()
                if meta["notnull"] and not meta["has_default"] and not meta["pk"]}
    for i, r in enumerate(rows):
        missing_required = required - set(r.keys())
        if missing_required:
            raise ImportValidationError(
                f"{table}[{i}]: отсутствуют обязательные колонки: "
                f"{sorted(missing_required)}"
            )

    inserted = 0
    for r in rows:
        use_cols = [c for c in cols_info.keys() if c in r.keys()]
        if not use_cols:
            continue
        placeholders = ", ".join("?" for _ in use_cols)
        col_names = ", ".join(use_cols)
        values = tuple(r[c] for c in use_cols)
        con.execute(
            f"INSERT INTO {table} ({col_names}) VALUES ({placeholders})",
            values,
        )
        inserted += 1
    return inserted


def import_from_json(path) -> dict:
    data = _load_payload(path)
    meta = data["meta"]
    tables = data["tables"]

    # недостающие «новые» таблицы считаем пустыми
    for t in _OPTIONAL_TABLES:
        if t not in tables:
            tables[t] = []

    warnings: list[str] = []
    file_version = meta.get("schema_version")
    file_app = meta.get("app_name")

    strict = (file_version == EXPORT_SCHEMA_VERSION)
    if not strict:
        warnings.append(
            f"Версия схемы в файле: {file_version!r}, "
            f"текущая: {EXPORT_SCHEMA_VERSION}. Импорт в гибком режиме."
        )
    if file_app is not None and file_app != APP_NAME:
        warnings.append(
            f"Файл помечен приложением {file_app!r}, текущее: {APP_NAME!r}."
        )

    _validate_structure(tables)
    _validate_fk(tables)

    backup_path = _make_backup()

    counts: dict[str, int] = {t: 0 for t in _INSERT_ORDER}

    with db.cursor() as con:
        for t in _DELETE_ORDER:
            con.execute(f"DELETE FROM {t}")

        for t in _INSERT_ORDER:
            counts[t] = _insert_rows(con, t, tables[t], strict=strict)

        fk_problems = con.execute("PRAGMA foreign_key_check").fetchall()
        if fk_problems:
            raise ImportValidationError(
                "PRAGMA foreign_key_check выявил проблемы: "
                + "; ".join(str(r) for r in fk_problems)
            )

    return {
        "strict": strict,
        "backup_path": str(backup_path),
        "counts": counts,
        "warnings": warnings,
    }