-- Схема БД приложения pr_v01. Все CREATE идемпотентны (IF NOT EXISTS).

CREATE TABLE IF NOT EXISTS statuses (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS p1_levels (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS macro_sprints (
    id          INTEGER PRIMARY KEY,
    code        TEXT    NOT NULL UNIQUE,
    start_date  TEXT    NOT NULL,
    end_date    TEXT    NOT NULL,
    goal        TEXT    NOT NULL DEFAULT '',
    status_id   INTEGER NOT NULL REFERENCES statuses(id) ON DELETE RESTRICT,
    priority    INTEGER NULL
);

CREATE INDEX IF NOT EXISTS idx_macro_sprints_status   ON macro_sprints(status_id);
CREATE INDEX IF NOT EXISTS idx_macro_sprints_priority ON macro_sprints(priority);

CREATE TABLE IF NOT EXISTS sprints (
    id              INTEGER PRIMARY KEY,
    code            TEXT    NOT NULL UNIQUE,
    start_date      TEXT    NOT NULL,
    end_date        TEXT    NOT NULL,
    goal            TEXT    NOT NULL DEFAULT '',
    status_id       INTEGER NOT NULL REFERENCES statuses(id) ON DELETE RESTRICT,
    macro_sprint_id INTEGER NULL REFERENCES macro_sprints(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_sprints_status ON sprints(status_id);
CREATE INDEX IF NOT EXISTS idx_sprints_macro  ON sprints(macro_sprint_id);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS roles (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS subroles (
    id      INTEGER PRIMARY KEY,
    role_id INTEGER NOT NULL REFERENCES roles(id)
                ON DELETE RESTRICT
                ON UPDATE CASCADE,
    name    TEXT NOT NULL,
    UNIQUE(role_id, name)
);

CREATE INDEX IF NOT EXISTS idx_subroles_role ON subroles(role_id);

CREATE TABLE IF NOT EXISTS epics (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE,
    goal            TEXT    NULL,
    role_id         INTEGER NULL REFERENCES roles(id)
                        ON DELETE RESTRICT
                        ON UPDATE CASCADE,
    subrole_id      INTEGER NULL REFERENCES subroles(id) ON DELETE RESTRICT,
    deadline        TEXT    NULL,
    status_id       INTEGER NOT NULL REFERENCES statuses(id) ON DELETE RESTRICT,
    macro_sprint_id INTEGER NULL REFERENCES macro_sprints(id) ON DELETE RESTRICT,
    comment         TEXT    NULL,
    priority        INTEGER NULL
);

CREATE INDEX IF NOT EXISTS idx_epics_role    ON epics(role_id);
CREATE INDEX IF NOT EXISTS idx_epics_subrole ON epics(subrole_id);
CREATE INDEX IF NOT EXISTS idx_epics_status  ON epics(status_id);
CREATE INDEX IF NOT EXISTS idx_epics_macro   ON epics(macro_sprint_id);
CREATE INDEX IF NOT EXISTS idx_epics_deadline ON epics(deadline);

CREATE TABLE IF NOT EXISTS tasks (
    id              INTEGER PRIMARY KEY,
    name            TEXT    NOT NULL UNIQUE,
    description     TEXT    NULL,
    epic_id         INTEGER NULL REFERENCES epics(id) ON DELETE RESTRICT,
    role_id         INTEGER NULL REFERENCES roles(id)
                        ON DELETE RESTRICT
                        ON UPDATE CASCADE,
    subrole_id      INTEGER NULL REFERENCES subroles(id) ON DELETE RESTRICT,
    p1              TEXT    NULL REFERENCES p1_levels(name) ON DELETE RESTRICT,
    p2              INTEGER NULL,
    deadline        TEXT    NULL,
    pp              REAL    NULL,
    status_id       INTEGER NOT NULL REFERENCES statuses(id) ON DELETE RESTRICT,
    macro_sprint_id INTEGER NULL REFERENCES macro_sprints(id) ON DELETE RESTRICT,
    sprint_id       INTEGER NULL REFERENCES sprints(id) ON DELETE RESTRICT,
    comment         TEXT    NULL
);

CREATE INDEX IF NOT EXISTS idx_tasks_epic    ON tasks(epic_id);
CREATE INDEX IF NOT EXISTS idx_tasks_role    ON tasks(role_id);
CREATE INDEX IF NOT EXISTS idx_tasks_subrole ON tasks(subrole_id);
CREATE INDEX IF NOT EXISTS idx_tasks_status  ON tasks(status_id);
CREATE INDEX IF NOT EXISTS idx_tasks_macro   ON tasks(macro_sprint_id);
CREATE INDEX IF NOT EXISTS idx_tasks_sprint  ON tasks(sprint_id);
CREATE INDEX IF NOT EXISTS idx_tasks_p1      ON tasks(p1);
CREATE INDEX IF NOT EXISTS idx_tasks_deadline ON tasks(deadline);


-- ==================== ACTIONS ====================

CREATE TABLE IF NOT EXISTS action_statuses (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS actions (
    id          INTEGER PRIMARY KEY,
    name        TEXT    NULL,
    description TEXT    NULL,
    date        TEXT    NOT NULL,
    pp          REAL    NULL,
    start_time  TEXT    NULL,
    end_time    TEXT    NULL,
    duration    INTEGER NULL,
    task_id     INTEGER NULL REFERENCES tasks(id)   ON DELETE RESTRICT,
    epic_id     INTEGER NULL REFERENCES epics(id)   ON DELETE RESTRICT,
    role_id     INTEGER NULL REFERENCES roles(id)
                    ON DELETE RESTRICT
                    ON UPDATE CASCADE,
    subrole_id  INTEGER NULL REFERENCES subroles(id) ON DELETE RESTRICT,
    status_id   INTEGER NOT NULL REFERENCES action_statuses(id) ON DELETE RESTRICT
);

CREATE INDEX IF NOT EXISTS idx_actions_task     ON actions(task_id);
CREATE INDEX IF NOT EXISTS idx_actions_epic     ON actions(epic_id);
CREATE INDEX IF NOT EXISTS idx_actions_role     ON actions(role_id);
CREATE INDEX IF NOT EXISTS idx_actions_subrole  ON actions(subrole_id);
CREATE INDEX IF NOT EXISTS idx_actions_status   ON actions(status_id);
CREATE INDEX IF NOT EXISTS idx_actions_date     ON actions(date);


-- ==================== CRITERIA ====================

CREATE TABLE IF NOT EXISTS criterion_statuses (
    id   INTEGER PRIMARY KEY,
    name TEXT NOT NULL UNIQUE
);

CREATE TABLE IF NOT EXISTS macro_sprint_criteria (
    id              INTEGER PRIMARY KEY,
    macro_sprint_id INTEGER NOT NULL REFERENCES macro_sprints(id) ON DELETE CASCADE,
    n               INTEGER NOT NULL,
    text            TEXT    NOT NULL,
    status_id       INTEGER NULL REFERENCES criterion_statuses(id) ON DELETE RESTRICT,
    comment         TEXT    NULL
);

CREATE INDEX IF NOT EXISTS idx_ms_criteria_macro ON macro_sprint_criteria(macro_sprint_id);
CREATE INDEX IF NOT EXISTS idx_ms_criteria_order ON macro_sprint_criteria(macro_sprint_id, n);

CREATE TABLE IF NOT EXISTS sprint_criteria (
    id          INTEGER PRIMARY KEY,
    sprint_id   INTEGER NOT NULL REFERENCES sprints(id) ON DELETE CASCADE,
    n           INTEGER NOT NULL,
    text        TEXT    NOT NULL,
    status_id   INTEGER NULL REFERENCES criterion_statuses(id) ON DELETE RESTRICT,
    comment     TEXT    NULL
);

CREATE INDEX IF NOT EXISTS idx_sp_criteria_sprint ON sprint_criteria(sprint_id);
CREATE INDEX IF NOT EXISTS idx_sp_criteria_order  ON sprint_criteria(sprint_id, n);