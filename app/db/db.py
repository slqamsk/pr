"""Доступ к данным. Все SQL-запросы — здесь."""
import sqlite3
from contextlib import contextmanager
from . import db_init


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(db_init.DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


@contextmanager
def cursor():
    con = connect()
    try:
        yield con
        con.commit()
    except Exception:
        con.rollback()
        raise
    finally:
        con.close()


# ------------------- справочники -------------------

def list_statuses() -> list[dict]:
    with cursor() as con:
        rows = con.execute("SELECT id, name FROM statuses ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def list_p1_levels() -> list[dict]:
    with cursor() as con:
        rows = con.execute("SELECT id, name FROM p1_levels ORDER BY id").fetchall()
        return [dict(r) for r in rows]


# ------------------- settings -------------------

def get_setting(key: str, default: str | None = None) -> str | None:
    with cursor() as con:
        row = con.execute("SELECT value FROM settings WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with cursor() as con:
        con.execute(
            "INSERT INTO settings(key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )


def get_pomodoro_per_day() -> float:
    raw = get_setting(db_init._POMODORO_KEY, db_init._POMODORO_DEFAULT)
    try:
        v = float(raw)
        return v if v > 0 else 8.0
    except (TypeError, ValueError):
        return 8.0


# ------------------- macro_sprints -------------------

def list_macro_sprints() -> list[dict]:
    with cursor() as con:
        rows = con.execute(
            "SELECT m.id, m.code, m.start_date, m.end_date, m.goal, "
            "       m.status_id, s.name AS status_name, m.priority "
            "FROM macro_sprints m "
            "JOIN statuses s ON s.id = m.status_id "
            "ORDER BY m.priority IS NULL, m.priority, m.code"
        ).fetchall()
        return [dict(r) for r in rows]


def list_macro_sprints_brief() -> list[dict]:
    with cursor() as con:
        rows = con.execute(
            "SELECT id, code FROM macro_sprints ORDER BY code"
        ).fetchall()
        return [dict(r) for r in rows]


def insert_macro_sprint(code, start_date, end_date, goal, status_id, priority) -> int:
    with cursor() as con:
        cur = con.execute(
            """INSERT INTO macro_sprints
                   (code, start_date, end_date, goal, status_id, priority)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (code, start_date, end_date, goal, status_id, priority),
        )
        return cur.lastrowid


def update_macro_sprint(sid, code, start_date, end_date, goal, status_id, priority) -> None:
    with cursor() as con:
        con.execute(
            """UPDATE macro_sprints
                  SET code = ?, start_date = ?, end_date = ?,
                      goal = ?, status_id = ?, priority = ?
                WHERE id = ?""",
            (code, start_date, end_date, goal, status_id, priority, sid),
        )


def delete_macro_sprint(sid: int) -> None:
    with cursor() as con:
        con.execute("DELETE FROM macro_sprints WHERE id = ?", (sid,))


def count_sprints_using_macro(macro_id: int) -> int:
    with cursor() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM sprints WHERE macro_sprint_id = ?", (macro_id,)
        ).fetchone()
        return row["n"]


def count_epics_using_macro(macro_id: int) -> int:
    with cursor() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM epics WHERE macro_sprint_id = ?", (macro_id,)
        ).fetchone()
        return row["n"]


def count_tasks_using_macro(macro_id: int) -> int:
    with cursor() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE macro_sprint_id = ?", (macro_id,)
        ).fetchone()
        return row["n"]


# ------------------- sprints -------------------

def list_sprints() -> list[dict]:
    with cursor() as con:
        rows = con.execute(
            "SELECT s.id, s.code, s.start_date, s.end_date, s.goal, "
            "       s.status_id, st.name AS status_name, "
            "       s.macro_sprint_id, m.code AS macro_code "
            "FROM sprints s "
            "JOIN statuses st ON st.id = s.status_id "
            "LEFT JOIN macro_sprints m ON m.id = s.macro_sprint_id "
            "ORDER BY s.start_date, s.code"
        ).fetchall()
        return [dict(r) for r in rows]


def list_sprints_brief() -> list[dict]:
    with cursor() as con:
        rows = con.execute(
            "SELECT id, code, macro_sprint_id FROM sprints ORDER BY code"
        ).fetchall()
        return [dict(r) for r in rows]


def insert_sprint(code, start_date, end_date, goal, status_id, macro_sprint_id) -> int:
    with cursor() as con:
        cur = con.execute(
            """INSERT INTO sprints
                   (code, start_date, end_date, goal, status_id, macro_sprint_id)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (code, start_date, end_date, goal, status_id, macro_sprint_id),
        )
        return cur.lastrowid


def update_sprint(sid, code, start_date, end_date, goal, status_id, macro_sprint_id) -> None:
    with cursor() as con:
        con.execute(
            """UPDATE sprints
                  SET code = ?, start_date = ?, end_date = ?,
                      goal = ?, status_id = ?, macro_sprint_id = ?
                WHERE id = ?""",
            (code, start_date, end_date, goal, status_id, macro_sprint_id, sid),
        )


def delete_sprint(sid: int) -> None:
    with cursor() as con:
        con.execute("DELETE FROM sprints WHERE id = ?", (sid,))


def count_tasks_using_sprint(sprint_id: int) -> int:
    with cursor() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE sprint_id = ?", (sprint_id,)
        ).fetchone()
        return row["n"]


# ------------------- roles -------------------

def list_roles() -> list[dict]:
    with cursor() as con:
        rows = con.execute("SELECT id, name FROM roles ORDER BY id").fetchall()
        return [dict(r) for r in rows]


def insert_role(rid: int, name: str) -> None:
    with cursor() as con:
        con.execute("INSERT INTO roles(id, name) VALUES (?, ?)", (rid, name))


def update_role(old_id: int, new_id: int, name: str) -> None:
    with cursor() as con:
        con.execute("UPDATE roles SET id = ?, name = ? WHERE id = ?",
                    (new_id, name, old_id))


def delete_role(rid: int) -> None:
    with cursor() as con:
        con.execute("DELETE FROM roles WHERE id = ?", (rid,))


def count_subroles_using_role(rid: int) -> int:
    with cursor() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM subroles WHERE role_id = ?", (rid,)
        ).fetchone()
        return row["n"]


def count_epics_using_role(rid: int) -> int:
    with cursor() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM epics WHERE role_id = ?", (rid,)
        ).fetchone()
        return row["n"]


def count_tasks_using_role(rid: int) -> int:
    with cursor() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE role_id = ?", (rid,)
        ).fetchone()
        return row["n"]


# ------------------- subroles -------------------

def list_subroles() -> list[dict]:
    with cursor() as con:
        rows = con.execute(
            "SELECT s.id, s.role_id, s.name, r.name AS role_name "
            "FROM subroles s "
            "JOIN roles r ON r.id = s.role_id "
            "ORDER BY r.id, s.name"
        ).fetchall()
        return [dict(r) for r in rows]


def list_subroles_by_role(role_id: int) -> list[dict]:
    with cursor() as con:
        rows = con.execute(
            "SELECT id, name FROM subroles WHERE role_id = ? ORDER BY name",
            (role_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def insert_subrole(role_id: int, name: str) -> int:
    with cursor() as con:
        cur = con.execute(
            "INSERT INTO subroles(role_id, name) VALUES (?, ?)",
            (role_id, name),
        )
        return cur.lastrowid


def update_subrole(sid: int, role_id: int, name: str) -> None:
    with cursor() as con:
        con.execute(
            "UPDATE subroles SET role_id = ?, name = ? WHERE id = ?",
            (role_id, name, sid),
        )


def delete_subrole(sid: int) -> None:
    with cursor() as con:
        con.execute("DELETE FROM subroles WHERE id = ?", (sid,))


def count_epics_using_subrole(sid: int) -> int:
    with cursor() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM epics WHERE subrole_id = ?", (sid,)
        ).fetchone()
        return row["n"]


def count_tasks_using_subrole(sid: int) -> int:
    with cursor() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE subrole_id = ?", (sid,)
        ).fetchone()
        return row["n"]


# ------------------- epics -------------------

def list_epics() -> list[dict]:
    with cursor() as con:
        rows = con.execute(
            "SELECT e.id, e.name, e.goal, e.deadline, e.comment, e.priority, "
            "       e.role_id, r.name AS role_name, "
            "       e.subrole_id, sr.name AS subrole_name, "
            "       e.status_id, st.name AS status_name, "
            "       e.macro_sprint_id, m.code AS macro_code "
            "FROM epics e "
            "LEFT JOIN roles r ON r.id = e.role_id "
            "LEFT JOIN subroles sr ON sr.id = e.subrole_id "
            "JOIN statuses st ON st.id = e.status_id "
            "LEFT JOIN macro_sprints m ON m.id = e.macro_sprint_id "
            "ORDER BY e.priority IS NULL, e.priority, "
            "         e.deadline IS NULL, e.deadline, e.name"
        ).fetchall()
        return [dict(r) for r in rows]


def list_epics_brief() -> list[dict]:
    with cursor() as con:
        rows = con.execute(
            "SELECT e.id, e.name, e.role_id, e.subrole_id, e.macro_sprint_id "
            "FROM epics e ORDER BY e.name"
        ).fetchall()
        return [dict(r) for r in rows]


def insert_epic(name, goal, role_id, subrole_id, deadline,
                status_id, macro_sprint_id, comment, priority) -> int:
    with cursor() as con:
        cur = con.execute(
            """INSERT INTO epics
                   (name, goal, role_id, subrole_id, deadline,
                    status_id, macro_sprint_id, comment, priority)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, goal, role_id, subrole_id, deadline,
             status_id, macro_sprint_id, comment, priority),
        )
        return cur.lastrowid


def update_epic(eid, name, goal, role_id, subrole_id, deadline,
                status_id, macro_sprint_id, comment, priority) -> None:
    with cursor() as con:
        con.execute(
            """UPDATE epics
                  SET name = ?, goal = ?, role_id = ?, subrole_id = ?,
                      deadline = ?, status_id = ?, macro_sprint_id = ?,
                      comment = ?, priority = ?
                WHERE id = ?""",
            (name, goal, role_id, subrole_id, deadline,
             status_id, macro_sprint_id, comment, priority, eid),
        )


def delete_epic(eid: int) -> None:
    with cursor() as con:
        con.execute("DELETE FROM epics WHERE id = ?", (eid,))


def count_tasks_using_epic(eid: int) -> int:
    with cursor() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM tasks WHERE epic_id = ?", (eid,)
        ).fetchone()
        return row["n"]


# ------------------- tasks -------------------

def insert_task(name, description, epic_id, role_id, subrole_id,
                p1, p2, deadline, pp, status_id,
                macro_sprint_id, sprint_id, comment) -> int:
    with cursor() as con:
        cur = con.execute(
            """INSERT INTO tasks
                   (name, description, epic_id, role_id, subrole_id,
                    p1, p2, deadline, pp, status_id,
                    macro_sprint_id, sprint_id, comment)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, description, epic_id, role_id, subrole_id,
             p1, p2, deadline, pp, status_id,
             macro_sprint_id, sprint_id, comment),
        )
        return cur.lastrowid


def update_task(tid, name, description, epic_id, role_id, subrole_id,
                p1, p2, deadline, pp, status_id,
                macro_sprint_id, sprint_id, comment) -> None:
    with cursor() as con:
        con.execute(
            """UPDATE tasks
                  SET name = ?, description = ?, epic_id = ?, role_id = ?,
                      subrole_id = ?, p1 = ?, p2 = ?, deadline = ?, pp = ?,
                      status_id = ?, macro_sprint_id = ?, sprint_id = ?,
                      comment = ?
                WHERE id = ?""",
            (name, description, epic_id, role_id, subrole_id,
             p1, p2, deadline, pp, status_id,
             macro_sprint_id, sprint_id, comment, tid),
        )


def delete_task(tid: int) -> None:
    with cursor() as con:
        con.execute("DELETE FROM tasks WHERE id = ?", (tid,))


# ------------------- action_statuses -------------------

def list_action_statuses() -> list[dict]:
    with cursor() as con:
        rows = con.execute(
            "SELECT id, name FROM action_statuses ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


# ------------------- actions -------------------

def list_actions() -> list[dict]:
    with cursor() as con:
        rows = con.execute(
            "SELECT a.id, a.name, a.description, a.date, a.pp, "
            "       a.start_time, a.end_time, a.duration, "
            "       a.task_id, t.name AS task_name, "
            "       a.epic_id, e.name AS epic_name, "
            "       a.role_id, r.name AS role_name, "
            "       a.subrole_id, sr.name AS subrole_name, "
            "       a.status_id, st.name AS status_name "
            "FROM actions a "
            "LEFT JOIN tasks    t  ON t.id  = a.task_id "
            "LEFT JOIN epics    e  ON e.id  = a.epic_id "
            "LEFT JOIN roles    r  ON r.id  = a.role_id "
            "LEFT JOIN subroles sr ON sr.id = a.subrole_id "
            "JOIN      action_statuses st ON st.id = a.status_id "
            "ORDER BY a.date DESC, a.start_time IS NULL, a.start_time DESC, a.id DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def insert_action(name, description, date, pp, start_time, end_time, duration,
                  task_id, epic_id, role_id, subrole_id, status_id) -> int:
    with cursor() as con:
        cur = con.execute(
            """INSERT INTO actions
                   (name, description, date, pp, start_time, end_time, duration,
                    task_id, epic_id, role_id, subrole_id, status_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (name, description, date, pp, start_time, end_time, duration,
             task_id, epic_id, role_id, subrole_id, status_id),
        )
        return cur.lastrowid


def update_action(aid, name, description, date, pp, start_time, end_time, duration,
                  task_id, epic_id, role_id, subrole_id, status_id) -> None:
    with cursor() as con:
        con.execute(
            """UPDATE actions
                  SET name = ?, description = ?, date = ?, pp = ?,
                      start_time = ?, end_time = ?, duration = ?,
                      task_id = ?, epic_id = ?, role_id = ?,
                      subrole_id = ?, status_id = ?
                WHERE id = ?""",
            (name, description, date, pp, start_time, end_time, duration,
             task_id, epic_id, role_id, subrole_id, status_id, aid),
        )


def delete_action(aid: int) -> None:
    with cursor() as con:
        con.execute("DELETE FROM actions WHERE id = ?", (aid,))


# ------------------- счётчики для каскадов -------------------

def count_actions_using_task(task_id: int) -> int:
    with cursor() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM actions WHERE task_id = ?", (task_id,)
        ).fetchone()
        return row["n"]


def count_actions_using_epic(epic_id: int) -> int:
    with cursor() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM actions WHERE epic_id = ?", (epic_id,)
        ).fetchone()
        return row["n"]


def count_actions_using_role(role_id: int) -> int:
    with cursor() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM actions WHERE role_id = ?", (role_id,)
        ).fetchone()
        return row["n"]


def count_actions_using_subrole(subrole_id: int) -> int:
    with cursor() as con:
        row = con.execute(
            "SELECT COUNT(*) AS n FROM actions WHERE subrole_id = ?", (subrole_id,)
        ).fetchone()
        return row["n"]

# ------------------- criterion_statuses -------------------

def list_criterion_statuses() -> list[dict]:
    with cursor() as con:
        rows = con.execute(
            "SELECT id, name FROM criterion_statuses ORDER BY id"
        ).fetchall()
        return [dict(r) for r in rows]


# ------------------- macro_sprint_criteria -------------------

def list_macro_sprint_criteria(macro_sprint_id: int) -> list[dict]:
    with cursor() as con:
        rows = con.execute(
            "SELECT c.id, c.macro_sprint_id, c.n, c.text, "
            "       c.status_id, s.name AS status_name, c.comment "
            "FROM macro_sprint_criteria c "
            "LEFT JOIN criterion_statuses s ON s.id = c.status_id "
            "WHERE c.macro_sprint_id = ? "
            "ORDER BY c.n, c.id",
            (macro_sprint_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def replace_macro_sprint_criteria(macro_sprint_id: int,
                                  criteria: list[dict]) -> None:
    """Полностью заменяет набор критериев макро-спринта в одной транзакции."""
    with cursor() as con:
        con.execute(
            "DELETE FROM macro_sprint_criteria WHERE macro_sprint_id = ?",
            (macro_sprint_id,),
        )
        for c in criteria:
            con.execute(
                """INSERT INTO macro_sprint_criteria
                       (macro_sprint_id, n, text, status_id, comment)
                   VALUES (?, ?, ?, ?, ?)""",
                (macro_sprint_id, c["n"], c["text"],
                 c.get("status_id"), c.get("comment")),
            )


# ------------------- sprint_criteria -------------------

def list_sprint_criteria(sprint_id: int) -> list[dict]:
    with cursor() as con:
        rows = con.execute(
            "SELECT c.id, c.sprint_id, c.n, c.text, "
            "       c.status_id, s.name AS status_name, c.comment "
            "FROM sprint_criteria c "
            "LEFT JOIN criterion_statuses s ON s.id = c.status_id "
            "WHERE c.sprint_id = ? "
            "ORDER BY c.n, c.id",
            (sprint_id,),
        ).fetchall()
        return [dict(r) for r in rows]


def replace_sprint_criteria(sprint_id: int, criteria: list[dict]) -> None:
    with cursor() as con:
        con.execute(
            "DELETE FROM sprint_criteria WHERE sprint_id = ?",
            (sprint_id,),
        )
        for c in criteria:
            con.execute(
                """INSERT INTO sprint_criteria
                       (sprint_id, n, text, status_id, comment)
                   VALUES (?, ?, ?, ?, ?)""",
                (sprint_id, c["n"], c["text"],
                 c.get("status_id"), c.get("comment")),
            )


# ------------------- tasks: pf / вспомогательные -------------------

def list_tasks_pf_data() -> list[dict]:
    """Минимум полей для пересчёта PF по всем задачам."""
    with cursor() as con:
        rows = con.execute(
            "SELECT t.id, t.p1, t.p2, t.deadline, t.pp, "
            "       st.name AS status_name "
            "FROM tasks t "
            "JOIN statuses st ON st.id = t.status_id"
        ).fetchall()
        return [dict(r) for r in rows]


def bulk_update_task_pf(updates: list[tuple[float, int]]) -> None:
    """updates = [(pf, task_id), ...]"""
    if not updates:
        return
    with cursor() as con:
        con.executemany(
            "UPDATE tasks SET pf = ? WHERE id = ?",
            updates,
        )


def update_task_pf(task_id: int, pf: float) -> None:
    with cursor() as con:
        con.execute("UPDATE tasks SET pf = ? WHERE id = ?", (pf, task_id))


def list_tasks() -> list[dict]:
    with cursor() as con:
        rows = con.execute(
            "SELECT t.id, t.name, t.description, "
            "       t.epic_id, e.name AS epic_name, "
            "       t.role_id, r.name AS role_name, "
            "       t.subrole_id, sr.name AS subrole_name, "
            "       t.p1, t.p2, t.deadline, t.pp, "
            "       t.status_id, st.name AS status_name, "
            "       t.macro_sprint_id, m.code AS macro_code, "
            "       t.sprint_id, sp.code AS sprint_code, "
            "       t.comment, t.pf "
            "FROM tasks t "
            "LEFT JOIN epics e ON e.id = t.epic_id "
            "LEFT JOIN roles r ON r.id = t.role_id "
            "LEFT JOIN subroles sr ON sr.id = t.subrole_id "
            "JOIN statuses st ON st.id = t.status_id "
            "LEFT JOIN macro_sprints m ON m.id = t.macro_sprint_id "
            "LEFT JOIN sprints sp ON sp.id = t.sprint_id"
        ).fetchall()
        return [dict(r) for r in rows]


def execute_query(sql: str) -> list[dict]:
    """Выполняет произвольный SELECT и возвращает результат."""
    with cursor() as con:
        rows = con.execute(sql).fetchall()
        return [dict(r) for r in rows]


def count_query(sql: str) -> int:
    """Выполняет SELECT, возвращает число строк."""
    with cursor() as con:
        cur = con.execute(sql)
        # fetchall, чтобы получить всё и посчитать
        return len(cur.fetchall())