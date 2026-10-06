"""Вкладка работы с действиями (actions)."""
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime

from db import db
from ui.widgets import (CalendarPopup, ScrollableTable,
                        ask_unsaved_changes, SqlFilterDialog)

COLUMNS = [
    {"key": "date",        "title": "Date",      "width": 90,  "wrap": False},
    {"key": "start_time",  "title": "Start",     "width": 60,  "wrap": False},
    {"key": "end_time",    "title": "End",       "width": 60,  "wrap": False},
    {"key": "duration",    "title": "Dur",       "width": 50,  "wrap": False},
    {"key": "pp",          "title": "PP",        "width": 50,  "wrap": False},
    {"key": "name",        "title": "Name",      "width": 180, "wrap": True},
    {"key": "description", "title": "Description","width": 340, "wrap": True},
    {"key": "task_name",   "title": "Task",      "width": 180, "wrap": True},
    {"key": "epic_name",   "title": "Epic",      "width": 140, "wrap": True},
    {"key": "role_name",   "title": "Роль",      "width": 150, "wrap": True},
    {"key": "subrole_name","title": "Подроль",   "width": 150, "wrap": True},
    {"key": "status_name", "title": "Статус",    "width": 120, "wrap": False},
]

_COMPUTED_COLOR  = "#004080"
_USER_COLOR      = "#606060"
_EMPTY_COLOR     = "#999999"

_DEFAULT_STATUS = "В работе"

_SQL_MODE_ALL = "Все записи"
_SQL_MODE_FILTER = "Применить фильтр"

_ACTION_BASE_SQL = (
    "SELECT a.id, a.name, a.description, a.date, a.pp, "
    "       a.start_time, a.end_time, a.duration, "
    "       a.task_id, t.name AS task_name, "
    "       a.epic_id, e.name AS epic_name, "
    "       a.role_id, r.name AS role_name, "
    "       a.subrole_id, sr.name AS subrole_name, "
    "       a.status_id, st.name AS status_name "
    "FROM actions a "
    "LEFT JOIN tasks t ON t.id = a.task_id "
    "LEFT JOIN epics e ON e.id = a.epic_id "
    "LEFT JOIN roles r ON r.id = a.role_id "
    "LEFT JOIN subroles sr ON sr.id = a.subrole_id "
    "JOIN action_statuses st ON st.id = a.status_id"
)
_ACTION_DEFAULT_ORDER = "ORDER BY a.date DESC, a.start_time IS NULL, a.start_time DESC, a.id DESC"


def _to_iso(s: str) -> str:
    return datetime.strptime(s.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")


def _to_ru(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")


def _role_display(rid: int, name: str) -> str:
    return f"{rid}. {name}"


def _hhmm_to_minutes(s: str) -> int | None:
    try:
        parts = s.strip().split(":")
        if len(parts) != 2:
            return None
        h, m = int(parts[0]), int(parts[1])
        if not (0 <= h <= 23 and 0 <= m <= 59):
            return None
        return h * 60 + m
    except (ValueError, AttributeError):
        return None


def _minutes_to_hhmm(m: int) -> str:
    m = m % (24 * 60)
    return f"{m // 60:02d}:{m % 60:02d}"


def compute_time_block(start_str: str, end_str: str, dur_str: str):
    s = start_str.strip()
    e = end_str.strip()
    d = dur_str.strip()

    s_min = _hhmm_to_minutes(s) if s else None
    e_min = _hhmm_to_minutes(e) if e else None
    d_val = None
    if d:
        try:
            d_val = int(d)
            if d_val < 0:
                d_val = None
        except ValueError:
            d_val = None

    s_computed = False
    e_computed = False
    d_computed = False

    given = sum(1 for x in (s_min, e_min, d_val) if x is not None)
    if given == 2:
        if s_min is not None and e_min is not None and d_val is None:
            d_val = (e_min - s_min) % (24 * 60)
            d_computed = True
        elif s_min is not None and d_val is not None and e_min is None:
            e_min = (s_min + d_val) % (24 * 60)
            e_computed = True
        elif e_min is not None and d_val is not None and s_min is None:
            s_min = (e_min - d_val) % (24 * 60)
            s_computed = True

    s_out = _minutes_to_hhmm(s_min) if s_min is not None else ""
    e_out = _minutes_to_hhmm(e_min) if e_min is not None else ""
    d_out = str(d_val) if d_val is not None else ""

    return s_out, e_out, d_out, s_computed, e_computed, d_computed


def _ask_status_dialog(parent, options) -> str | None:
    result = {"value": None}
    dlg = tk.Toplevel(parent)
    dlg.title("Выбор статуса")
    dlg.transient(parent)
    dlg.resizable(False, False)
    dlg.grab_set()

    ttk.Label(dlg, text="Выберите статус:",
              padding=(12, 12, 12, 6)).pack(anchor="w")

    body = ttk.Frame(dlg, padding=(12, 0, 12, 12))
    body.pack(fill="both", expand=True)

    def pick(v):
        result["value"] = v
        dlg.destroy()

    for opt in options:
        ttk.Button(body, text=opt, width=26,
                   command=lambda v=opt: pick(v)).pack(fill="x", pady=2)

    ttk.Separator(body, orient="horizontal").pack(fill="x", pady=(8, 4))
    ttk.Button(body, text="Отмена", width=26,
               command=dlg.destroy).pack(fill="x", pady=2)

    dlg.update_idletasks()
    px = parent.winfo_rootx() + (parent.winfo_width() - dlg.winfo_reqwidth()) // 2
    py = parent.winfo_rooty() + (parent.winfo_height() - dlg.winfo_reqheight()) // 2
    dlg.geometry(f"+{max(0, px)}+{max(0, py)}")

    parent.wait_window(dlg)
    return result["value"]


class ActionsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=8)
        self.current_id: int | None = None
        self._raw_by_id: dict[int, dict] = {}
        self._snapshot: dict | None = None

        self._statuses: list[dict] = []
        self._status_by_name: dict[str, int] = {}

        self._roles_by_display: dict[str, int] = {}
        self._subrole_display_to_id: dict[str, int] = {}

        self._epics_by_name: dict[str, dict] = {}
        self._tasks_by_name: dict[str, dict] = {}

        self._build_ui()
        self.refresh()
        self._set_snapshot()

    # ---------- UI ----------
    def _build_ui(self):
        self._statuses = db.list_action_statuses()
        self._status_by_name = {s["name"]: s["id"] for s in self._statuses}

        # ---- Нижний ряд кнопок ----
        btns = ttk.Frame(self, padding=(0, 8, 0, 0))
        ttk.Button(btns, text="Новая",     command=self._new).pack(side="left")
        ttk.Button(btns, text="Сохранить", command=self._on_save_clicked).pack(side="left", padx=6)
        ttk.Button(btns, text="Удалить",   command=self._delete).pack(side="left")
        ttk.Button(btns, text="Обновить",  command=self._on_refresh_clicked).pack(side="right")
        self.btn_sql = ttk.Button(btns, text="SQL…", command=self._open_sql_dialog)
        self.btn_sql.pack(side="right", padx=(0, 6))
        self.var_sql_mode = tk.StringVar(value=_SQL_MODE_ALL)
        self.cmb_sql_mode = ttk.Combobox(btns, textvariable=self.var_sql_mode,
                                         values=[_SQL_MODE_ALL, _SQL_MODE_FILTER],
                                         state="readonly", width=20)
        self.cmb_sql_mode.pack(side="right", padx=(0, 6))
        self.cmb_sql_mode.bind("<<ComboboxSelected>>", self._on_sql_mode_changed)

        # ---- Основная форма ----
        body = ttk.Frame(self)
        body.columnconfigure(0, weight=1, uniform="f")
        body.columnconfigure(1, weight=1, uniform="f")

        grp_main = ttk.LabelFrame(body, text="Основное", padding=6)
        grp_main.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=(0, 4))
        grp_main.columnconfigure(1, weight=1)

        self.var_name = tk.StringVar()
        ttk.Label(grp_main, text="Name").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(grp_main, textvariable=self.var_name)\
            .grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(grp_main, text="Description").grid(row=1, column=0, sticky="nw",
                                                     padx=(0, 8), pady=2)
        desc_wrap = ttk.Frame(grp_main)
        desc_wrap.grid(row=1, column=1, sticky="ew", pady=2)
        desc_wrap.columnconfigure(0, weight=1)
        self.txt_desc = tk.Text(desc_wrap, height=3, wrap="word",
                                font=("TkDefaultFont", 9), undo=True)
        self.txt_desc.grid(row=0, column=0, sticky="ew")
        dsb = ttk.Scrollbar(desc_wrap, orient="vertical", command=self.txt_desc.yview)
        self.txt_desc.configure(yscrollcommand=dsb.set)
        dsb.grid(row=0, column=1, sticky="ns")

        grp_links = ttk.LabelFrame(body, text="Привязки", padding=6)
        grp_links.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=(0, 4))
        grp_links.columnconfigure(1, weight=1)

        self.var_epic    = tk.StringVar()
        self.var_task    = tk.StringVar()
        self.var_role    = tk.StringVar()
        self.var_subrole = tk.StringVar()

        ttk.Label(grp_links, text="Эпик").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        self.cmb_epic = ttk.Combobox(grp_links, textvariable=self.var_epic,
                                     values=[""], state="readonly", width=30)
        self.cmb_epic.grid(row=0, column=1, sticky="w", pady=2)
        self.cmb_epic.bind("<<ComboboxSelected>>", self._on_epic_changed)

        ttk.Label(grp_links, text="Задача").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=2)
        self.cmb_task = ttk.Combobox(grp_links, textvariable=self.var_task,
                                     values=[""], state="readonly", width=30)
        self.cmb_task.grid(row=1, column=1, sticky="w", pady=2)
        self.cmb_task.bind("<<ComboboxSelected>>", self._on_task_changed)

        ttk.Label(grp_links, text="Роль").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=2)
        self.cmb_role = ttk.Combobox(grp_links, textvariable=self.var_role,
                                     values=[], state="readonly", width=30)
        self.cmb_role.grid(row=2, column=1, sticky="w", pady=2)
        self.cmb_role.bind("<<ComboboxSelected>>", self._on_role_selected)

        ttk.Label(grp_links, text="Подроль").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=2)
        self.cmb_subrole = ttk.Combobox(grp_links, textvariable=self.var_subrole,
                                        values=[], state="disabled", width=30)
        self.cmb_subrole.grid(row=3, column=1, sticky="w", pady=2)

        grp_time = ttk.LabelFrame(body, text="Время и вес", padding=6)
        grp_time.grid(row=1, column=0, sticky="nsew", padx=(0, 4), pady=(4, 0))
        grp_time.columnconfigure(1, weight=1)

        self.var_date = tk.StringVar()
        ttk.Label(grp_time, text="Date").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        f_date = ttk.Frame(grp_time)
        f_date.grid(row=0, column=1, sticky="w", pady=2)
        ttk.Entry(f_date, textvariable=self.var_date, width=12).pack(side="left")
        ttk.Button(f_date, text="📅", width=3,
                   command=lambda: self._open_cal(self.var_date)).pack(side="left", padx=(4, 0))

        self.var_pp = tk.StringVar()
        ttk.Label(grp_time, text="PP").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(grp_time, textvariable=self.var_pp, width=8)\
            .grid(row=1, column=1, sticky="w", pady=2)

        self.var_start = tk.StringVar()
        ttk.Label(grp_time, text="Start").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(grp_time, textvariable=self.var_start, width=8)\
            .grid(row=2, column=1, sticky="w", pady=2)

        self.var_end = tk.StringVar()
        ttk.Label(grp_time, text="End").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(grp_time, textvariable=self.var_end, width=8)\
            .grid(row=3, column=1, sticky="w", pady=2)

        self.var_duration = tk.StringVar()
        ttk.Label(grp_time, text="Duration").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(grp_time, textvariable=self.var_duration, width=8)\
            .grid(row=4, column=1, sticky="w", pady=2)

        side_btns = ttk.Frame(grp_time)
        side_btns.grid(row=0, column=2, rowspan=5, sticky="ne", padx=(16, 0), pady=2)
        ttk.Button(side_btns, text="Начать",
                   command=self._on_start_clicked).pack(fill="x")
        ttk.Button(side_btns, text="Завершить",
                   command=self._on_finish_clicked).pack(fill="x", pady=(6, 0))

        grp_view = ttk.LabelFrame(body, text="Итоги (только чтение)", padding=6)
        grp_view.grid(row=1, column=1, sticky="nsew", padx=(4, 0), pady=(4, 0))
        grp_view.columnconfigure(1, weight=1)

        self.var_v_pp = tk.StringVar()
        self.var_v_s  = tk.StringVar()
        self.var_v_e  = tk.StringVar()
        self.var_v_d  = tk.StringVar()

        def _row(r, label, var):
            ttk.Label(grp_view, text=label).grid(row=r, column=0, sticky="w",
                                                 padx=(0, 8), pady=2)
            lbl = tk.Label(grp_view, textvariable=var, anchor="w", padx=6, pady=2,
                           relief="solid", borderwidth=1, bg="#f5f5f5")
            lbl.grid(row=r, column=1, sticky="ew", pady=2)
            return lbl

        self.lbl_v_pp = _row(0, "PP",       self.var_v_pp)
        self.lbl_v_s  = _row(1, "Start",    self.var_v_s)
        self.lbl_v_e  = _row(2, "End",      self.var_v_e)
        self.lbl_v_d  = _row(3, "Duration", self.var_v_d)

        grp_other = ttk.LabelFrame(body, text="Прочее", padding=6)
        grp_other.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        grp_other.columnconfigure(1, weight=1)

        self.var_status = tk.StringVar()
        ttk.Label(grp_other, text="Статус").grid(row=0, column=0, sticky="w",
                                                 padx=(0, 8), pady=2)
        ttk.Combobox(grp_other, textvariable=self.var_status,
                     values=[s["name"] for s in self._statuses],
                     state="readonly", width=20)\
            .grid(row=0, column=1, sticky="w", pady=2)

        # ---- Таблица ----
        self.table = ScrollableTable(self, COLUMNS, on_select=self._on_table_select,
                                     settings_key="ui.columns.actions")

        self.var_table_status = tk.StringVar(value="")
        self.lbl_table_status = tk.Label(self, textvariable=self.var_table_status,
                                         anchor="w", padx=8, pady=2, fg="#606060")

        # ---- Упаковка снизу вверх ----
        btns.pack(side="bottom", fill="x")
        body.pack(side="bottom", fill="x", pady=(8, 0))
        self.lbl_table_status.pack(side="bottom", fill="x", padx=8)
        self.table.pack(side="top", fill="both", expand=True)

        for v in (self.var_pp, self.var_start, self.var_end, self.var_duration):
            v.trace_add("write", lambda *_: self._recompute_view())

    # ---------- SQL-фильтр ----------
    def _get_sql_mode(self) -> str:
        return self.var_sql_mode.get() or _SQL_MODE_ALL

    def _get_saved_where(self) -> str:
        return db.get_setting("ui.sql_filter.actions.where", "") or ""

    def _get_saved_order(self) -> str | None:
        return db.get_setting("ui.sql_filter.actions.order_by")

    def _get_effective_order(self) -> str:
        v = self._get_saved_order()
        if v is None:
            return _ACTION_DEFAULT_ORDER
        return v

    def _build_action_sql(self, where: str, order: str) -> str:
        parts = [_ACTION_BASE_SQL]
        if where:
            parts.append(where)
        if order:
            parts.append(order)
        return " ".join(parts)

    def _load_table(self):
        mode = self._get_sql_mode()
        where = self._get_saved_where()
        order = self._get_effective_order()

        if mode == _SQL_MODE_FILTER:
            sql = self._build_action_sql(where, order)
            try:
                rows = db.execute_query(sql)
                summary = " ".join(filter(None, [where, order])).strip()
                if len(summary) > 80:
                    summary = summary[:77] + "..."
                self._set_table_status(f"Применён фильтр: {summary}" if summary
                                       else "Применён фильтр")
            except Exception as e:
                sql = self._build_action_sql("", _ACTION_DEFAULT_ORDER)
                rows = db.execute_query(sql)
                self._set_table_status(f"Фильтр не применён: {e}", error=True)
        else:
            sql = self._build_action_sql("", _ACTION_DEFAULT_ORDER)
            rows = db.execute_query(sql)
            self._set_table_status("Показаны все записи")

        self._raw_by_id = {r["id"]: r for r in rows}
        display = [{
            "id":           r["id"],
            "date":         _to_ru(r["date"]) if r["date"] else "",
            "start_time":   r["start_time"] or "",
            "end_time":     r["end_time"] or "",
            "duration":     "" if r["duration"] is None else r["duration"],
            "pp":           "" if r["pp"] is None else f"{r['pp']:.1f}",
            "name":         r["name"] or "",
            "description":  r["description"] or "",
            "task_name":    r["task_name"] or "",
            "epic_name":    r["epic_name"] or "",
            "role_name":    (_role_display(r["role_id"], r["role_name"])
                             if r["role_id"] else ""),
            "subrole_name": r["subrole_name"] or "",
            "status_name":  r["status_name"],
        } for r in rows]
        self.table.set_rows(display, iid_key="id")
        if self.current_id is not None:
            self.table.select_iid(str(self.current_id))

    def _set_table_status(self, text: str, error: bool = False):
        self.var_table_status.set(text)
        self.lbl_table_status.configure(fg=("#a00000" if error else "#606060"))

    def _on_sql_mode_changed(self, _e=None):
        if self._is_dirty():
            db_enabled = db.get_setting("ui.sql_filter.actions.enabled", "0") == "1"
            self.var_sql_mode.set(_SQL_MODE_FILTER if db_enabled else _SQL_MODE_ALL)
            return
        enabled = (self._get_sql_mode() == _SQL_MODE_FILTER)
        db.set_setting("ui.sql_filter.actions.enabled", "1" if enabled else "0")
        self._load_table()

    def _open_sql_dialog(self):
        if self._is_dirty():
            messagebox.showinfo("SQL-фильтр",
                                "Сначала сохраните или отмените изменения формы.",
                                parent=self.winfo_toplevel())
            return

        where_text = self._get_saved_where()
        order_text = self._get_saved_order()
        if order_text is None:
            order_text = _ACTION_DEFAULT_ORDER

        def _validate(sql):
            return db.count_query(sql)

        def _apply(where, order):
            db.set_setting("ui.sql_filter.actions.where", where or "")
            db.set_setting("ui.sql_filter.actions.order_by", order or "")
            db.set_setting("ui.sql_filter.actions.enabled", "1")
            self.var_sql_mode.set(_SQL_MODE_FILTER)
            self._load_table()

        dlg = SqlFilterDialog(
            parent=self.winfo_toplevel(),
            base_sql=_ACTION_BASE_SQL,
            where_text=where_text,
            order_by_text=order_text,
            default_order_by=_ACTION_DEFAULT_ORDER,
            validate_sql=_validate,
            on_apply=_apply,
        )
        self.wait_window(dlg)

    def _update_sql_button_state(self):
        dirty = self._is_dirty()
        self.btn_sql.configure(state="disabled" if dirty else "normal")
        self.cmb_sql_mode.configure(state="disabled" if dirty else "readonly")

    # ---------- визуальный блок ----------
    def _recompute_view(self):
        pp_text = self.var_pp.get().strip()
        s_out, e_out, d_out, s_c, e_c, d_c = compute_time_block(
            self.var_start.get(), self.var_end.get(), self.var_duration.get()
        )
        self.var_v_pp.set(pp_text)
        self.var_v_s.set(s_out)
        self.var_v_e.set(e_out)
        self.var_v_d.set(d_out)

        self._style_label(self.lbl_v_pp, "user" if pp_text else "empty")
        self._style_label(self.lbl_v_s,
                          "computed" if s_c else ("user" if s_out else "empty"))
        self._style_label(self.lbl_v_e,
                          "computed" if e_c else ("user" if e_out else "empty"))
        self._style_label(self.lbl_v_d,
                          "computed" if d_c else ("user" if d_out else "empty"))

    @staticmethod
    def _style_label(lbl: tk.Label, kind: str):
        if kind == "computed":
            lbl.configure(foreground=_COMPUTED_COLOR, font=("TkDefaultFont", 9, "bold"))
        elif kind == "user":
            lbl.configure(foreground=_USER_COLOR, font=("TkDefaultFont", 9))
        else:
            lbl.configure(foreground=_EMPTY_COLOR, font=("TkDefaultFont", 9))

    # ---------- комбобоксы ----------
    def _refresh_role_combo(self):
        roles = db.list_roles()
        self._roles_by_display = {_role_display(r["id"], r["name"]): r["id"] for r in roles}
        self.cmb_role.configure(values=[""] + list(self._roles_by_display.keys()))

    def _refresh_epic_combo(self):
        brief = db.list_epics_brief()
        self._epics_by_name = {e["name"]: e for e in brief}
        self.cmb_epic.configure(values=[""] + list(self._epics_by_name.keys()))

    def _refresh_task_combo(self, epic_id):
        raw = db.list_tasks()
        if epic_id is not None:
            filtered = [t for t in raw if t["epic_id"] == epic_id]
        else:
            filtered = raw
        self._tasks_by_name = {t["name"]: t for t in filtered}
        self.cmb_task.configure(values=[""] + list(self._tasks_by_name.keys()))

    def _refresh_subrole_combo(self, role_id, keep_value=False):
        if role_id is None:
            self._subrole_display_to_id = {}
            self.cmb_subrole.configure(values=[], state="disabled")
            if not keep_value:
                self.var_subrole.set("")
            return
        subs = db.list_subroles_by_role(role_id)
        self._subrole_display_to_id = {s["name"]: s["id"] for s in subs}
        self.cmb_subrole.configure(values=[""] + list(self._subrole_display_to_id.keys()),
                                   state="readonly")
        if not keep_value:
            self.var_subrole.set("")

    # ---------- обработчики ----------
    def _on_epic_changed(self, _e=None):
        epic_name = self.var_epic.get().strip()
        if not epic_name:
            self._refresh_task_combo(None)
            self.cmb_role.configure(state="readonly")
            self.cmb_subrole.configure(
                state="readonly" if self.var_role.get() else "disabled")
            return

        epic = self._epics_by_name.get(epic_name)
        if not epic:
            return

        self.var_task.set("")
        self._refresh_task_combo(epic["id"])

        if epic["role_id"] is not None:
            role_id = epic["role_id"]
            disp = None
            for d, rid in self._roles_by_display.items():
                if rid == role_id:
                    disp = d
                    break
            self.var_role.set(disp or "")
        else:
            self.var_role.set("")

        if epic["subrole_id"] is not None:
            subs = db.list_subroles_by_role(epic["role_id"]) if epic["role_id"] is not None else []
            name = next((s["name"] for s in subs if s["id"] == epic["subrole_id"]), "")
            self._subrole_display_to_id = {s["name"]: s["id"] for s in subs}
            self.cmb_subrole.configure(values=[""] + list(self._subrole_display_to_id.keys()),
                                       state="readonly")
            self.var_subrole.set(name)
        else:
            self.var_subrole.set("")
            self._refresh_subrole_combo(epic["role_id"], keep_value=True)

        self.cmb_role.configure(state="disabled")
        self.cmb_subrole.configure(state="disabled")

    def _on_task_changed(self, _e=None):
        task_name = self.var_task.get().strip()
        if not task_name:
            self.cmb_role.configure(state="readonly")
            self.cmb_subrole.configure(
                state="readonly" if self.var_role.get() else "disabled")
            self.cmb_epic.configure(state="readonly")
            return

        task = self._tasks_by_name.get(task_name)
        if not task:
            return

        if task["epic_id"] is not None and task["epic_name"]:
            self.var_epic.set(task["epic_name"])
            self._refresh_task_combo(task["epic_id"])
        else:
            self.var_epic.set("")
            self._refresh_task_combo(None)
        self.var_task.set(task["name"])

        if task["role_id"] is not None and task["role_name"]:
            self.var_role.set(_role_display(task["role_id"], task["role_name"]))
        else:
            self.var_role.set("")

        if task["subrole_id"] is not None:
            subs = db.list_subroles_by_role(task["role_id"]) if task["role_id"] is not None else []
            name = next((s["name"] for s in subs if s["id"] == task["subrole_id"]), "")
            self._subrole_display_to_id = {s["name"]: s["id"] for s in subs}
            self.cmb_subrole.configure(values=[""] + list(self._subrole_display_to_id.keys()),
                                       state="readonly")
            self.var_subrole.set(name)
        else:
            self.var_subrole.set("")
            self._refresh_subrole_combo(task["role_id"], keep_value=True)

        self.cmb_epic.configure(state="disabled")
        self.cmb_role.configure(state="disabled")
        self.cmb_subrole.configure(state="disabled")

    def _on_role_selected(self, _e=None):
        if self.var_task.get().strip() or self.var_epic.get().strip():
            return
        role_display = self.var_role.get().strip()
        role_id = self._roles_by_display.get(role_display) if role_display else None
        self._refresh_subrole_combo(role_id, keep_value=False)

    # ---------- снимок ----------
    def _form_state(self) -> dict:
        return {
            "name":        self.var_name.get().strip(),
            "description": self._get_desc(),
            "epic":        self.var_epic.get().strip(),
            "task":        self.var_task.get().strip(),
            "role":        self.var_role.get().strip(),
            "subrole":     self.var_subrole.get().strip(),
            "date":        self.var_date.get().strip(),
            "pp":          self.var_pp.get().strip(),
            "start":       self.var_start.get().strip(),
            "end":         self.var_end.get().strip(),
            "duration":    self.var_duration.get().strip(),
            "status":      self.var_status.get(),
        }

    def _set_snapshot(self):
        self._snapshot = self._form_state()
        if hasattr(self, "btn_sql"):
            self._update_sql_button_state()

    def _is_dirty(self) -> bool:
        if self._snapshot is None:
            return False
        return self._form_state() != self._snapshot

    def has_unsaved(self) -> bool:
        return self._is_dirty()

    def confirm_leave(self) -> bool:
        if not self._is_dirty():
            return True
        action = ask_unsaved_changes(parent=self.winfo_toplevel())
        if action == "cancel":
            return False
        if action == "save":
            return self._save()
        return True

    # ---------- данные ----------
    def refresh(self):
        self._refresh_role_combo()
        self._refresh_epic_combo()
        self._refresh_task_combo(None)

        enabled = db.get_setting("ui.sql_filter.actions.enabled", "0") == "1"
        self.var_sql_mode.set(_SQL_MODE_FILTER if enabled else _SQL_MODE_ALL)

        self._load_table()

    def _load_into_form(self, aid: int):
        self.current_id = aid
        src = self._raw_by_id.get(aid)
        if not src:
            return

        self.var_name.set(src["name"] or "")
        self._set_desc(src["description"] or "")

        self.var_epic.set(src["epic_name"] or "")
        self._refresh_task_combo(src["epic_id"])
        self.var_task.set(src["task_name"] or "")

        if src["role_id"] is not None and src["role_name"]:
            self.var_role.set(_role_display(src["role_id"], src["role_name"]))
        else:
            self.var_role.set("")

        if src["role_id"] is not None:
            subs = db.list_subroles_by_role(src["role_id"])
            self._subrole_display_to_id = {s["name"]: s["id"] for s in subs}
            self.cmb_subrole.configure(values=[""] + list(self._subrole_display_to_id.keys()),
                                       state="readonly")
        else:
            self._subrole_display_to_id = {}
            self.cmb_subrole.configure(values=[], state="disabled")
        self.var_subrole.set(src["subrole_name"] or "")

        self.var_date.set(_to_ru(src["date"]) if src["date"] else "")
        self.var_pp.set("" if src["pp"] is None else f"{src['pp']:.1f}")
        self.var_start.set(src["start_time"] or "")
        self.var_end.set(src["end_time"] or "")
        self.var_duration.set("" if src["duration"] is None else str(src["duration"]))

        self.var_status.set(src["status_name"])

        if src["task_id"] is not None:
            self.cmb_epic.configure(state="disabled")
            self.cmb_role.configure(state="disabled")
            self.cmb_subrole.configure(state="disabled")
        elif src["epic_id"] is not None:
            self.cmb_epic.configure(state="readonly")
            self.cmb_role.configure(state="disabled")
            self.cmb_subrole.configure(state="disabled")
        else:
            self.cmb_epic.configure(state="readonly")
            self.cmb_role.configure(state="readonly")
            self.cmb_subrole.configure(
                state="readonly" if src["role_id"] is not None else "disabled")

        self._recompute_view()
        self._set_snapshot()
        self.table.select_iid(str(aid))

    def _set_desc(self, text):
        self.txt_desc.delete("1.0", "end")
        self.txt_desc.insert("1.0", text or "")

    def _get_desc(self):
        return self.txt_desc.get("1.0", "end-1c")

    def _clear_form(self):
        self.current_id = None
        self.var_name.set("")
        self._set_desc("")
        self.var_epic.set("")
        self.var_task.set("")
        self._refresh_task_combo(None)
        self.var_role.set("")
        self._subrole_display_to_id = {}
        self.cmb_subrole.configure(values=[], state="disabled")
        self.var_subrole.set("")
        self.var_date.set("")
        self.var_pp.set("")
        self.var_start.set("")
        self.var_end.set("")
        self.var_duration.set("")
        if _DEFAULT_STATUS in self._status_by_name:
            self.var_status.set(_DEFAULT_STATUS)
        elif self._statuses:
            self.var_status.set(self._statuses[0]["name"])

        self.cmb_epic.configure(state="readonly")
        self.cmb_task.configure(state="readonly")
        self.cmb_role.configure(state="readonly")
        self.cmb_subrole.configure(state="disabled")

        self.table.clear_selection()
        self._recompute_view()
        self._set_snapshot()

    # ---------- выбор в таблице ----------
    def _on_table_select(self, data):
        new_id = data["id"]
        if new_id == self.current_id:
            return
        if self._is_dirty():
            action = ask_unsaved_changes(parent=self.winfo_toplevel())
            if action == "cancel":
                self._restore_selection()
                return
            if action == "save":
                if not self._save():
                    self._restore_selection()
                    return
        self._load_into_form(new_id)

    def _restore_selection(self):
        if self.current_id is None:
            self.table.clear_selection()
        else:
            self.table.select_iid(str(self.current_id))

    # ---------- кнопки ----------
    def _new(self):
        if self._is_dirty():
            action = ask_unsaved_changes(parent=self.winfo_toplevel())
            if action == "cancel":
                return
            if action == "save":
                if not self._save():
                    return
        self._clear_form()

    def _on_save_clicked(self):
        self._save()

    def _save(self) -> bool:
        name = self.var_name.get().strip()
        description = self._get_desc().strip()

        if not name and not description:
            messagebox.showwarning("Валидация",
                                   "Хотя бы одно из полей «Name» / «Description» "
                                   "должно быть заполнено.",
                                   parent=self.winfo_toplevel())
            return False

        date_text = self.var_date.get().strip()
        if not date_text:
            messagebox.showwarning("Валидация", "Date обязательно.",
                                   parent=self.winfo_toplevel())
            return False
        try:
            date_iso = _to_iso(date_text)
        except ValueError:
            messagebox.showwarning("Валидация",
                                   "Date должна быть в формате ДД.ММ.ГГГГ.",
                                   parent=self.winfo_toplevel())
            return False

        pp_text = self.var_pp.get().strip().replace(",", ".")
        if pp_text:
            try:
                pp = float(pp_text)
            except ValueError:
                messagebox.showwarning("Валидация", "PP должен быть числом.",
                                       parent=self.winfo_toplevel())
                return False
        else:
            pp = None

        s_text = self.var_start.get().strip()
        e_text = self.var_end.get().strip()
        if s_text and _hhmm_to_minutes(s_text) is None:
            messagebox.showwarning("Валидация", "Start должен быть в формате HH:MM.",
                                   parent=self.winfo_toplevel())
            return False
        if e_text and _hhmm_to_minutes(e_text) is None:
            messagebox.showwarning("Валидация", "End должен быть в формате HH:MM.",
                                   parent=self.winfo_toplevel())
            return False
        start_time = s_text or None
        end_time = e_text or None

        d_text = self.var_duration.get().strip()
        if d_text:
            try:
                duration = int(d_text)
            except ValueError:
                messagebox.showwarning("Валидация", "Duration должно быть целым числом.",
                                       parent=self.winfo_toplevel())
                return False
            if duration < 0:
                messagebox.showwarning("Валидация", "Duration не может быть отрицательным.",
                                       parent=self.winfo_toplevel())
                return False
        else:
            duration = None

        epic_name = self.var_epic.get().strip()
        epic_id = None
        epic_row = None
        if epic_name:
            epic_row = self._epics_by_name.get(epic_name)
            if epic_row is None:
                messagebox.showwarning("Валидация",
                                       f"Эпик '{epic_name}' не найден.",
                                       parent=self.winfo_toplevel())
                return False
            epic_id = epic_row["id"]

        task_name = self.var_task.get().strip()
        task_id = None
        task_row = None
        if task_name:
            task_row = self._tasks_by_name.get(task_name)
            if task_row is None:
                messagebox.showwarning("Валидация",
                                       f"Задача '{task_name}' не найдена.",
                                       parent=self.winfo_toplevel())
                return False
            task_id = task_row["id"]

        if task_row is not None:
            epic_id    = task_row["epic_id"]
            role_id    = task_row["role_id"]
            subrole_id = task_row["subrole_id"]
        elif epic_row is not None:
            role_id    = epic_row["role_id"]
            subrole_id = epic_row["subrole_id"]
        else:
            role_display = self.var_role.get().strip()
            role_id = self._roles_by_display.get(role_display) if role_display else None
            if role_display and role_id is None:
                messagebox.showwarning("Валидация",
                                       f"Роль '{role_display}' не найдена.",
                                       parent=self.winfo_toplevel())
                return False

            subrole_display = self.var_subrole.get().strip()
            subrole_id = None
            if subrole_display:
                if role_id is None:
                    messagebox.showwarning("Валидация",
                                           "Нельзя выбрать подроль без роли.",
                                           parent=self.winfo_toplevel())
                    return False
                subrole_id = self._subrole_display_to_id.get(subrole_display)
                if subrole_id is None:
                    messagebox.showwarning("Валидация",
                                           f"Подроль '{subrole_display}' не найдена.",
                                           parent=self.winfo_toplevel())
                    return False

        status_id = self._status_by_name.get(self.var_status.get())
        if status_id is None:
            messagebox.showwarning("Валидация", "Выберите статус.",
                                   parent=self.winfo_toplevel())
            return False

        try:
            if self.current_id is None:
                new_id = db.insert_action(
                    name or None, description or None, date_iso,
                    pp, start_time, end_time, duration,
                    task_id, epic_id, role_id, subrole_id, status_id,
                )
                self.current_id = new_id
            else:
                db.update_action(
                    self.current_id,
                    name or None, description or None, date_iso,
                    pp, start_time, end_time, duration,
                    task_id, epic_id, role_id, subrole_id, status_id,
                )
        except sqlite3.IntegrityError as e:
            messagebox.showwarning("Валидация", str(e),
                                   parent=self.winfo_toplevel())
            return False

        self._set_snapshot()
        self.refresh()
        if self.current_id is not None:
            self.table.select_iid(str(self.current_id))
        return True

    def _delete(self):
        if self.current_id is None:
            messagebox.showinfo("Удаление", "Выбери запись из списка.",
                                parent=self.winfo_toplevel())
            return
        label = self.var_name.get().strip() or "(без имени)"
        if not messagebox.askyesno("Удаление", f"Удалить действие «{label}»?",
                                   parent=self.winfo_toplevel()):
            return
        db.delete_action(self.current_id)
        self._clear_form()
        self.refresh()

    def _on_refresh_clicked(self):
        if self._is_dirty():
            action = ask_unsaved_changes(parent=self.winfo_toplevel())
            if action == "cancel":
                return
            if action == "save":
                if not self._save():
                    return
        self.refresh()

    # ---------- workflow ----------
    def _on_start_clicked(self):
        if self.current_id is None:
            messagebox.showinfo("Начать",
                                "Выбери действие из списка.",
                                parent=self.winfo_toplevel())
            return
        self.var_date.set(datetime.today().strftime("%d.%m.%Y"))
        self.var_start.set(datetime.now().strftime("%H:%M"))
        if _DEFAULT_STATUS in self._status_by_name:
            self.var_status.set(_DEFAULT_STATUS)
        self._save()

    def _on_finish_clicked(self):
        if self.current_id is None:
            messagebox.showinfo("Завершить",
                                "Выбери действие из списка.",
                                parent=self.winfo_toplevel())
            return

        if self.var_status.get().strip() == _DEFAULT_STATUS:
            has_task = bool(self.var_task.get().strip())
            has_epic = bool(self.var_epic.get().strip())
            options = [s["name"] for s in self._statuses]
            if has_task or has_epic:
                options = [o for o in options if o != "Без задачи"]
            chosen = _ask_status_dialog(self.winfo_toplevel(), options)
            if chosen is None:
                return
            self.var_status.set(chosen)

        self.var_end.set(datetime.now().strftime("%H:%M"))
        self._save()

    def new_from_task(self, task: dict):
        if self._is_dirty():
            action = ask_unsaved_changes(parent=self.winfo_toplevel())
            if action == "cancel":
                return
            if action == "save":
                if not self._save():
                    return

        self._clear_form()

        if task.get("epic_id") is not None and task.get("epic_name"):
            self.var_epic.set(task["epic_name"])
            self._refresh_task_combo(task["epic_id"])
        else:
            self.var_epic.set("")
            self._refresh_task_combo(None)

        self.var_task.set(task["name"])

        if task.get("role_id") is not None and task.get("role_name"):
            self.var_role.set(_role_display(task["role_id"], task["role_name"]))
        else:
            self.var_role.set("")

        if task.get("subrole_id") is not None:
            subs = db.list_subroles_by_role(task["role_id"]) if task.get("role_id") is not None else []
            name = next((s["name"] for s in subs if s["id"] == task["subrole_id"]), "")
            self._subrole_display_to_id = {s["name"]: s["id"] for s in subs}
            self.cmb_subrole.configure(values=[""] + list(self._subrole_display_to_id.keys()),
                                       state="readonly")
            self.var_subrole.set(name)
        else:
            self.var_subrole.set("")
            self._refresh_subrole_combo(task.get("role_id"), keep_value=True)

        self.cmb_epic.configure(state="disabled")
        self.cmb_role.configure(state="disabled")
        self.cmb_subrole.configure(state="disabled")

        self.var_name.set(f"Выполнение задачи {task['name']}")
        self.var_date.set(datetime.today().strftime("%d.%m.%Y"))
        self.var_start.set(datetime.now().strftime("%H:%M"))
        if _DEFAULT_STATUS in self._status_by_name:
            self.var_status.set(_DEFAULT_STATUS)

        self._recompute_view()

    # ---------- календарь ----------
    def _open_cal(self, var: tk.StringVar):
        initial = None
        try:
            initial = datetime.strptime(var.get().strip(), "%d.%m.%Y").date()
        except (ValueError, AttributeError):
            pass
        popup = CalendarPopup(
            self,
            initial=initial,
            on_pick=lambda d: var.set(d.strftime("%d.%m.%Y")),
        )
        popup.geometry(f"+{self.winfo_pointerx()}+{self.winfo_pointery()}")