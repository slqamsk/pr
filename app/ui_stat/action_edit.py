"""Модальное окно редактирования одного Action.

Три колонки:
  * Левая   — информация об эпике + список задач эпика + список действий эпика
  * Средняя — информация о задаче + список действий задачи
  * Правая  — редактируемые поля действия и верхняя панель с кнопками

В колонках «Эпик» и «Задача» поля «Цель», «Description» и «Комментарий»
подстраивают высоту под содержимое (от 3 до 15 строк).
Списки в колонках при сужении переносят текст на несколько строк.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime

from db import db
from ui.widgets import CalendarPopup, ScrollableTable


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


_AUTOSIZE_MIN_LINES = 3
_AUTOSIZE_MAX_LINES = 15


# Колонки вспомогательных списков.
_TASKS_LIST_COLUMNS = [
    {"key": "name",        "title": "Name",     "width": 200, "wrap": False},
    {"key": "deadline",    "title": "Дедлайн",  "width": 85,  "wrap": False},
    {"key": "status_name", "title": "Статус",   "width": 110, "wrap": False},
]

_ACTIONS_LIST_COLUMNS = [
    {"key": "name",        "title": "Name",   "width": 240, "wrap": False},
    {"key": "date",        "title": "Date",   "width": 85,  "wrap": False},
    {"key": "start_time",  "title": "Start",  "width": 55,  "wrap": False},
    {"key": "duration",    "title": "Dur",    "width": 50,  "wrap": False},
    {"key": "status_name", "title": "Статус", "width": 120, "wrap": False},
]


class ActionEditDialog(tk.Toplevel):
    """Модальное окно редактирования Action.
    Возвращает True, если пользователь сохранил изменения."""

    def __init__(self, parent, action_row: dict):
        super().__init__(parent)
        self.title("Редактирование действия")
        self.transient(parent)
        self.grab_set()

        self.result = False
        self.action = action_row

        self._statuses = db.list_action_statuses()
        self._status_by_name = {s["name"]: s["id"] for s in self._statuses}

        self._roles_by_display = {}
        self._subrole_display_to_id = {}
        self._epics_full_by_name = {}
        self._tasks_full_by_name = {}

        self._autosize_widgets = []
        self._maximized = False
        self._saved_geometry = None

        self._build_ui()
        self._load()

        # 1. Устанавливаем "нормальную" геометрию
        self.update_idletasks()
        scr_w = self.winfo_screenwidth()
        scr_h = self.winfo_screenheight()
        w = min(1600, scr_w - 60)
        h = min(900, scr_h - 120)
        px = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        px = max(0, min(px, scr_w - w))
        py = max(0, min(py, scr_h - h - 60))
        self.geometry(f"{w}x{h}+{px}+{py}")
        self.update_idletasks()

        # 2. Запоминаем её — на случай «Восстановить»
        self._saved_geometry = self.geometry()

        # 3. Открываем сразу развёрнутым
        self._apply_maximized()

        parent.wait_window(self)

    # ---------- UI ----------
    def _build_ui(self):
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        columns = ttk.Frame(outer)
        columns.pack(fill="both", expand=True)
        columns.columnconfigure(0, weight=1, uniform="col", minsize=400)
        columns.columnconfigure(1, weight=1, uniform="col", minsize=400)
        columns.columnconfigure(2, weight=1, uniform="col", minsize=400)
        columns.rowconfigure(0, weight=1)

        self._build_epic_column(columns)
        self._build_task_column(columns)
        self._build_action_column(columns)

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

    def _apply_maximized(self):
        """Разворачивает окно в рабочую область, не заезжая под панель задач."""
        try:
            scr_w = self.winfo_screenwidth()
            scr_h = self.winfo_screenheight()
            w = scr_w - 20
            h = scr_h - 80
            self.geometry(f"{w}x{h}+10+5")
            self._maximized = True
            if hasattr(self, "btn_maximize"):
                self.btn_maximize.configure(text="Восстановить")
        except tk.TclError:
            pass

    def _toggle_maximize(self):
        try:
            if self._maximized:
                if self._saved_geometry:
                    self.geometry(self._saved_geometry)
                self._maximized = False
                self.btn_maximize.configure(text="Развернуть")
            else:
                self._saved_geometry = self.geometry()
                self._apply_maximized()
        except tk.TclError:
            pass

    def _make_readonly_text(self, parent, r, label, autosize=False):
        ttk.Label(parent, text=label).grid(row=r, column=0, sticky="nw",
                                           padx=(0, 6), pady=2)
        txt = tk.Text(parent, height=1, wrap="word",
                      font=("TkDefaultFont", 9),
                      bg="#f0f0f0", state="disabled",
                      relief="solid", borderwidth=1)
        txt.grid(row=r, column=1, sticky="ew", pady=2)
        if autosize:
            self._autosize_widgets.append(txt)
            txt.bind("<Configure>",
                     lambda e, ww=txt: self._autosize_text(ww), add="+")
        return txt

    # ---------- левая колонка ----------
    def _build_epic_column(self, parent):
        col = ttk.Frame(parent)
        col.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        col.columnconfigure(0, weight=1)
        col.rowconfigure(0, weight=0)
        col.rowconfigure(1, weight=1)
        col.rowconfigure(2, weight=1)

        grp = ttk.LabelFrame(col, text="Эпик (только чтение)", padding=6)
        grp.grid(row=0, column=0, sticky="ew")
        grp.columnconfigure(1, weight=1)

        self.ro_epic_name     = self._make_readonly_text(grp, 0, "Name")
        self.ro_epic_role     = self._make_readonly_text(grp, 1, "Роль")
        self.ro_epic_subrole  = self._make_readonly_text(grp, 2, "Подроль")
        self.ro_epic_deadline = self._make_readonly_text(grp, 3, "Дедлайн")
        self.ro_epic_status   = self._make_readonly_text(grp, 4, "Статус")
        self.ro_epic_macro    = self._make_readonly_text(grp, 5, "Macro")
        self.ro_epic_priority = self._make_readonly_text(grp, 6, "P")
        self.ro_epic_goal     = self._make_readonly_text(grp, 7, "Цель",
                                                         autosize=True)
        self.ro_epic_comment  = self._make_readonly_text(grp, 8, "Комментарий",
                                                         autosize=True)

        grp_tasks = ttk.LabelFrame(col, text="Задачи эпика", padding=4)
        grp_tasks.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        grp_tasks.columnconfigure(0, weight=1)
        grp_tasks.rowconfigure(0, weight=1)
        self.epic_tasks_table = ScrollableTable(
            grp_tasks, _TASKS_LIST_COLUMNS,
            on_select=None, settings_key=None, autofit=True,
            wrap_when_narrow=True,
        )
        self.epic_tasks_table.grid(row=0, column=0, sticky="nsew")

        grp_actions = ttk.LabelFrame(col, text="Действия эпика", padding=4)
        grp_actions.grid(row=2, column=0, sticky="nsew", pady=(4, 0))
        grp_actions.columnconfigure(0, weight=1)
        grp_actions.rowconfigure(0, weight=1)
        self.epic_actions_table = ScrollableTable(
            grp_actions, _ACTIONS_LIST_COLUMNS,
            on_select=None, settings_key=None, autofit=True,
            wrap_when_narrow=True,
        )
        self.epic_actions_table.grid(row=0, column=0, sticky="nsew")

    # ---------- средняя колонка ----------
    def _build_task_column(self, parent):
        col = ttk.Frame(parent)
        col.grid(row=0, column=1, sticky="nsew", padx=4)
        col.columnconfigure(0, weight=1)
        col.rowconfigure(0, weight=0)
        col.rowconfigure(1, weight=1)

        grp = ttk.LabelFrame(col, text="Задача (только чтение)", padding=6)
        grp.grid(row=0, column=0, sticky="ew")
        grp.columnconfigure(1, weight=1)

        self.ro_task_name     = self._make_readonly_text(grp, 0, "Name")
        self.ro_task_epic     = self._make_readonly_text(grp, 1, "Эпик")
        self.ro_task_role     = self._make_readonly_text(grp, 2, "Роль")
        self.ro_task_subrole  = self._make_readonly_text(grp, 3, "Подроль")
        self.ro_task_deadline = self._make_readonly_text(grp, 4, "Дедлайн")
        self.ro_task_p1       = self._make_readonly_text(grp, 5, "P1")
        self.ro_task_p2       = self._make_readonly_text(grp, 6, "P2")
        self.ro_task_pp       = self._make_readonly_text(grp, 7, "PP")
        self.ro_task_status   = self._make_readonly_text(grp, 8, "Статус")
        self.ro_task_macro    = self._make_readonly_text(grp, 9, "Macro")
        self.ro_task_sprint   = self._make_readonly_text(grp, 10, "Sprint")
        self.ro_task_pf       = self._make_readonly_text(grp, 11, "PF")
        self.ro_task_desc     = self._make_readonly_text(grp, 12, "Description",
                                                         autosize=True)
        self.ro_task_comment  = self._make_readonly_text(grp, 13, "Комментарий",
                                                         autosize=True)

        grp_actions = ttk.LabelFrame(col, text="Действия задачи", padding=4)
        grp_actions.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        grp_actions.columnconfigure(0, weight=1)
        grp_actions.rowconfigure(0, weight=1)
        self.task_actions_table = ScrollableTable(
            grp_actions, _ACTIONS_LIST_COLUMNS,
            on_select=None, settings_key=None, autofit=True,
            wrap_when_narrow=True,
        )
        self.task_actions_table.grid(row=0, column=0, sticky="nsew")

    # ---------- правая колонка ----------
    def _build_action_column(self, parent):
        col = ttk.Frame(parent)
        col.grid(row=0, column=2, sticky="nsew", padx=(4, 0))
        col.columnconfigure(0, weight=1)
        col.rowconfigure(0, weight=0)
        col.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(col)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 4))

        self.btn_maximize = ttk.Button(toolbar, text="Развернуть",
                                       command=self._toggle_maximize)
        self.btn_maximize.pack(side="left")

        ttk.Button(toolbar, text="Сохранить", command=self._on_save)\
            .pack(side="right")
        ttk.Button(toolbar, text="Отмена", command=self._on_cancel)\
            .pack(side="right", padx=(0, 6))

        grp = ttk.LabelFrame(col, text="Действие", padding=6)
        grp.grid(row=1, column=0, sticky="nsew")
        grp.columnconfigure(1, weight=1)

        self.var_name     = tk.StringVar()
        self.var_date     = tk.StringVar()
        self.var_pp       = tk.StringVar()
        self.var_start    = tk.StringVar()
        self.var_end      = tk.StringVar()
        self.var_duration = tk.StringVar()
        self.var_epic     = tk.StringVar()
        self.var_task     = tk.StringVar()
        self.var_role     = tk.StringVar()
        self.var_subrole  = tk.StringVar()
        self.var_status   = tk.StringVar()

        r = 0
        ttk.Label(grp, text="Name").grid(row=r, column=0, sticky="w",
                                         padx=(0, 8), pady=2)
        ttk.Entry(grp, textvariable=self.var_name)\
            .grid(row=r, column=1, sticky="ew", pady=2)

        r += 1
        ttk.Label(grp, text="Description").grid(row=r, column=0, sticky="nw",
                                                padx=(0, 8), pady=2)
        desc_wrap = ttk.Frame(grp)
        desc_wrap.grid(row=r, column=1, sticky="ew", pady=2)
        desc_wrap.columnconfigure(0, weight=1)
        self.txt_desc = tk.Text(desc_wrap, height=6, wrap="word",
                                font=("TkDefaultFont", 9), undo=True)
        self.txt_desc.grid(row=0, column=0, sticky="ew")
        dsb = ttk.Scrollbar(desc_wrap, orient="vertical",
                            command=self.txt_desc.yview)
        self.txt_desc.configure(yscrollcommand=dsb.set)
        dsb.grid(row=0, column=1, sticky="ns")

        r += 1
        ttk.Label(grp, text="Date").grid(row=r, column=0, sticky="w",
                                         padx=(0, 8), pady=2)
        f_date = ttk.Frame(grp)
        f_date.grid(row=r, column=1, sticky="w", pady=2)
        ttk.Entry(f_date, textvariable=self.var_date, width=12).pack(side="left")
        ttk.Button(f_date, text="📅", width=3,
                   command=lambda: self._open_cal(self.var_date)).pack(side="left", padx=(4, 0))

        r += 1
        ttk.Label(grp, text="PP").grid(row=r, column=0, sticky="w",
                                       padx=(0, 8), pady=2)
        ttk.Entry(grp, textvariable=self.var_pp, width=8)\
            .grid(row=r, column=1, sticky="w", pady=2)

        r += 1
        ttk.Label(grp, text="Start").grid(row=r, column=0, sticky="w",
                                          padx=(0, 8), pady=2)
        ttk.Entry(grp, textvariable=self.var_start, width=8)\
            .grid(row=r, column=1, sticky="w", pady=2)

        r += 1
        ttk.Label(grp, text="End").grid(row=r, column=0, sticky="w",
                                        padx=(0, 8), pady=2)
        ttk.Entry(grp, textvariable=self.var_end, width=8)\
            .grid(row=r, column=1, sticky="w", pady=2)

        r += 1
        ttk.Label(grp, text="Duration").grid(row=r, column=0, sticky="w",
                                             padx=(0, 8), pady=2)
        ttk.Entry(grp, textvariable=self.var_duration, width=8)\
            .grid(row=r, column=1, sticky="w", pady=2)

        r += 1
        ttk.Label(grp, text="Эпик").grid(row=r, column=0, sticky="w",
                                         padx=(0, 8), pady=2)
        self.cmb_epic = ttk.Combobox(grp, textvariable=self.var_epic,
                                     values=[""], state="readonly")
        self.cmb_epic.grid(row=r, column=1, sticky="ew", pady=2)
        self.cmb_epic.bind("<<ComboboxSelected>>", self._on_epic_changed)

        r += 1
        ttk.Label(grp, text="Задача").grid(row=r, column=0, sticky="w",
                                           padx=(0, 8), pady=2)
        self.cmb_task = ttk.Combobox(grp, textvariable=self.var_task,
                                     values=[""], state="readonly")
        self.cmb_task.grid(row=r, column=1, sticky="ew", pady=2)
        self.cmb_task.bind("<<ComboboxSelected>>", self._on_task_changed)

        r += 1
        ttk.Label(grp, text="Роль").grid(row=r, column=0, sticky="w",
                                         padx=(0, 8), pady=2)
        self.cmb_role = ttk.Combobox(grp, textvariable=self.var_role,
                                     values=[], state="readonly")
        self.cmb_role.grid(row=r, column=1, sticky="ew", pady=2)
        self.cmb_role.bind("<<ComboboxSelected>>", self._on_role_selected)

        r += 1
        ttk.Label(grp, text="Подроль").grid(row=r, column=0, sticky="w",
                                            padx=(0, 8), pady=2)
        self.cmb_subrole = ttk.Combobox(grp, textvariable=self.var_subrole,
                                        values=[], state="disabled")
        self.cmb_subrole.grid(row=r, column=1, sticky="ew", pady=2)

        r += 1
        ttk.Label(grp, text="Статус").grid(row=r, column=0, sticky="w",
                                           padx=(0, 8), pady=2)
        ttk.Combobox(grp, textvariable=self.var_status,
                     values=[s["name"] for s in self._statuses],
                     state="readonly")\
            .grid(row=r, column=1, sticky="w", pady=2)

    # ---------- автоподгонка ----------
    def _autosize_text(self, widget: tk.Text):
        try:
            result = widget.count("1.0", "end", "displaylines")
        except tk.TclError:
            return
        if result is None:
            return
        if isinstance(result, tuple):
            n = result[0]
        else:
            n = result
        if n is None:
            return
        n = max(_AUTOSIZE_MIN_LINES, min(_AUTOSIZE_MAX_LINES, n))
        try:
            current = int(widget.cget("height"))
        except (ValueError, tk.TclError):
            current = None
        if current != n:
            widget.configure(height=n)

    # ---------- readonly-утилита ----------
    def _set_readonly(self, widget: tk.Text, text):
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        if text:
            widget.insert("1.0", str(text))
        widget.configure(state="disabled")
        if widget in self._autosize_widgets:
            self.after_idle(lambda ww=widget: self._autosize_text(ww))

    def _clear_all_readonly(self, widgets):
        for w in widgets:
            self._set_readonly(w, "")

    # ---------- загрузка справочников ----------
    def _refresh_role_combo(self):
        roles = db.list_roles()
        self._roles_by_display = {_role_display(r["id"], r["name"]): r["id"]
                                  for r in roles}
        self.cmb_role.configure(values=[""] + list(self._roles_by_display.keys()))

    def _refresh_epic_combo(self):
        rows = db.list_epics()
        self._epics_full_by_name = {r["name"]: r for r in rows}
        self.cmb_epic.configure(values=[""] + list(self._epics_full_by_name.keys()))

    def _refresh_task_combo(self, epic_id):
        raw = db.list_tasks()
        if epic_id is not None:
            filtered = [t for t in raw if t["epic_id"] == epic_id]
        else:
            filtered = raw
        self._tasks_full_by_name = {t["name"]: t for t in filtered}
        self.cmb_task.configure(
            values=[""] + list(self._tasks_full_by_name.keys()))

    def _refresh_subrole_combo(self, role_id):
        if role_id is None:
            self._subrole_display_to_id = {}
            self.cmb_subrole.configure(values=[], state="disabled")
            return
        subs = db.list_subroles_by_role(role_id)
        self._subrole_display_to_id = {s["name"]: s["id"] for s in subs}
        self.cmb_subrole.configure(
            values=[""] + list(self._subrole_display_to_id.keys()),
            state="readonly")

    # ---------- инфо об эпике и задаче ----------
    def _refresh_epic_info(self):
        name = self.var_epic.get().strip()
        row = self._epics_full_by_name.get(name) if name else None

        if row is None:
            self._clear_all_readonly([
                self.ro_epic_name, self.ro_epic_role, self.ro_epic_subrole,
                self.ro_epic_deadline, self.ro_epic_status, self.ro_epic_macro,
                self.ro_epic_priority, self.ro_epic_goal, self.ro_epic_comment,
            ])
            return

        role_disp = ""
        if row.get("role_id") is not None and row.get("role_name"):
            role_disp = _role_display(row["role_id"], row["role_name"])

        deadline = _to_ru(row["deadline"]) if row.get("deadline") else ""

        self._set_readonly(self.ro_epic_name,     row.get("name") or "")
        self._set_readonly(self.ro_epic_role,     role_disp)
        self._set_readonly(self.ro_epic_subrole,  row.get("subrole_name") or "")
        self._set_readonly(self.ro_epic_deadline, deadline)
        self._set_readonly(self.ro_epic_status,   row.get("status_name") or "")
        self._set_readonly(self.ro_epic_macro,    row.get("macro_code") or "")
        self._set_readonly(self.ro_epic_priority,
                           "" if row.get("priority") is None else str(row["priority"]))
        self._set_readonly(self.ro_epic_goal,     row.get("goal") or "")
        self._set_readonly(self.ro_epic_comment,  row.get("comment") or "")

    def _refresh_task_info(self):
        name = self.var_task.get().strip()
        row = self._tasks_full_by_name.get(name) if name else None

        if row is None:
            self._clear_all_readonly([
                self.ro_task_name, self.ro_task_epic, self.ro_task_role,
                self.ro_task_subrole, self.ro_task_deadline, self.ro_task_p1,
                self.ro_task_p2, self.ro_task_pp, self.ro_task_status,
                self.ro_task_macro, self.ro_task_sprint, self.ro_task_pf,
                self.ro_task_desc, self.ro_task_comment,
            ])
            return

        role_disp = ""
        if row.get("role_id") is not None and row.get("role_name"):
            role_disp = _role_display(row["role_id"], row["role_name"])

        deadline = _to_ru(row["deadline"]) if row.get("deadline") else ""

        self._set_readonly(self.ro_task_name,     row.get("name") or "")
        self._set_readonly(self.ro_task_epic,     row.get("epic_name") or "")
        self._set_readonly(self.ro_task_role,     role_disp)
        self._set_readonly(self.ro_task_subrole,  row.get("subrole_name") or "")
        self._set_readonly(self.ro_task_deadline, deadline)
        self._set_readonly(self.ro_task_p1,       row.get("p1") or "")
        self._set_readonly(self.ro_task_p2,
                           "" if row.get("p2") is None else str(row["p2"]))
        self._set_readonly(self.ro_task_pp,
                           "" if row.get("pp") is None else f"{row['pp']:.1f}")
        self._set_readonly(self.ro_task_status,   row.get("status_name") or "")
        self._set_readonly(self.ro_task_macro,    row.get("macro_code") or "")
        self._set_readonly(self.ro_task_sprint,   row.get("sprint_code") or "")
        self._set_readonly(self.ro_task_pf,
                           "" if row.get("pf") is None else f"{row['pf']:.2f}")
        self._set_readonly(self.ro_task_desc,     row.get("description") or "")
        self._set_readonly(self.ro_task_comment,  row.get("comment") or "")

    # ---------- списки ----------
    def _current_action_list_row(self):
        date_text = self.var_date.get().strip()
        date_iso = ""
        date_disp = ""
        if date_text:
            try:
                date_iso = _to_iso(date_text)
                date_disp = date_text
            except ValueError:
                pass
        return {
            "id":          self.action["id"],
            "name":        self.var_name.get().strip(),
            "date":        date_disp,
            "_sort_key":   (date_iso, self.var_start.get().strip() or ""),
            "start_time":  self.var_start.get().strip(),
            "duration":    self.var_duration.get().strip(),
            "status_name": self.var_status.get().strip(),
        }

    def _db_action_list_row(self, a):
        date_iso = a.get("date") or ""
        return {
            "id":          a["id"],
            "name":        a.get("name") or "",
            "date":        _to_ru(date_iso) if date_iso else "",
            "_sort_key":   (date_iso, a.get("start_time") or ""),
            "start_time":  a.get("start_time") or "",
            "duration":    "" if a.get("duration") is None else str(a["duration"]),
            "status_name": a.get("status_name") or "",
        }

    def _db_task_list_row(self, t):
        return {
            "id":          t["id"],
            "name":        t.get("name") or "",
            "deadline":    _to_ru(t["deadline"]) if t.get("deadline") else "",
            "_sort_key":   (t.get("deadline") or "", t.get("name") or ""),
            "status_name": t.get("status_name") or "",
        }

    def _refresh_lists(self):
        epic_name = self.var_epic.get().strip()
        epic = self._epics_full_by_name.get(epic_name) if epic_name else None
        epic_id = epic["id"] if epic else None

        task_name = self.var_task.get().strip()
        task = self._tasks_full_by_name.get(task_name) if task_name else None
        task_id = task["id"] if task else None

        cur_id = self.action["id"]
        all_actions = db.list_actions()
        all_tasks = db.list_tasks()

        # --- Задачи эпика ---
        if epic_id is None:
            self.epic_tasks_table.set_rows([], iid_key="id")
            epic_task_ids = set()
        else:
            epic_tasks = [t for t in all_tasks if t.get("epic_id") == epic_id]
            epic_task_ids = {t["id"] for t in epic_tasks}
            rows = [self._db_task_list_row(t) for t in epic_tasks]
            rows.sort(key=lambda r: r["_sort_key"])
            self.epic_tasks_table.set_rows(rows, iid_key="id")

        # --- Действия эпика ---
        if epic_id is None:
            self.epic_actions_table.set_rows([], iid_key="id")
        else:
            rows = []
            for a in all_actions:
                if a["id"] == cur_id:
                    continue
                if a.get("epic_id") == epic_id or a.get("task_id") in epic_task_ids:
                    rows.append(self._db_action_list_row(a))
            if self.var_epic.get().strip() == epic_name or (
                    task_id is not None and task_id in epic_task_ids):
                rows.append(self._current_action_list_row())
            rows.sort(key=lambda r: r["_sort_key"])
            self.epic_actions_table.set_rows(rows, iid_key="id")

        # --- Действия задачи ---
        if task_id is None:
            self.task_actions_table.set_rows([], iid_key="id")
        else:
            rows = [self._db_action_list_row(a) for a in all_actions
                    if a.get("task_id") == task_id and a["id"] != cur_id]
            if self.var_task.get().strip() == task_name:
                rows.append(self._current_action_list_row())
            rows.sort(key=lambda r: r["_sort_key"])
            self.task_actions_table.set_rows(rows, iid_key="id")

    # ---------- загрузка действия ----------
    def _load(self):
        a = self.action

        self._refresh_role_combo()
        self._refresh_epic_combo()

        self.var_name.set(a.get("name") or "")
        self._set_desc(a.get("description") or "")
        self.var_date.set(_to_ru(a["date"]) if a.get("date") else "")
        self.var_pp.set("" if a.get("pp") is None else f"{a['pp']:.1f}")
        self.var_start.set(a.get("start_time") or "")
        self.var_end.set(a.get("end_time") or "")
        self.var_duration.set(
            "" if a.get("duration") is None else str(a["duration"]))

        epic_name = a.get("epic_name") or ""
        self.var_epic.set(epic_name)
        epic_id = None
        if epic_name:
            epic = self._epics_full_by_name.get(epic_name)
            if epic:
                epic_id = epic["id"]

        self._refresh_task_combo(epic_id)
        self.var_task.set(a.get("task_name") or "")

        if a.get("role_id") is not None and a.get("role_name"):
            self.var_role.set(_role_display(a["role_id"], a["role_name"]))
        else:
            self.var_role.set("")
        self._refresh_subrole_combo(a.get("role_id"))
        self.var_subrole.set(a.get("subrole_name") or "")

        self.var_status.set(a.get("status_name") or "")

        if a.get("task_id") is not None:
            self.cmb_epic.configure(state="disabled")
            self.cmb_role.configure(state="disabled")
            self.cmb_subrole.configure(state="disabled")
        elif a.get("epic_id") is not None:
            self.cmb_epic.configure(state="readonly")
            self.cmb_role.configure(state="disabled")
            self.cmb_subrole.configure(state="disabled")
        else:
            self.cmb_epic.configure(state="readonly")
            self.cmb_role.configure(state="readonly")
            if a.get("role_id") is not None:
                self.cmb_subrole.configure(state="readonly")

        self._refresh_epic_info()
        self._refresh_task_info()
        self._refresh_lists()

    # ---------- обработчики ----------
    def _on_epic_changed(self, _e=None):
        epic_name = self.var_epic.get().strip()
        if not epic_name:
            self._refresh_task_combo(None)
            self.cmb_role.configure(state="readonly")
            self.cmb_subrole.configure(
                state="readonly" if self.var_role.get() else "disabled")
            self._refresh_epic_info()
            self._refresh_task_info()
            self._refresh_lists()
            return
        epic = self._epics_full_by_name.get(epic_name)
        if not epic:
            return

        self.var_task.set("")
        self._refresh_task_combo(epic["id"])

        if epic.get("role_id") is not None:
            disp = None
            for d, rid in self._roles_by_display.items():
                if rid == epic["role_id"]:
                    disp = d
                    break
            self.var_role.set(disp or "")
        else:
            self.var_role.set("")

        if epic.get("subrole_id") is not None:
            subs = db.list_subroles_by_role(epic["role_id"]) \
                if epic.get("role_id") is not None else []
            name = next((s["name"] for s in subs
                         if s["id"] == epic["subrole_id"]), "")
            self._subrole_display_to_id = {s["name"]: s["id"] for s in subs}
            self.cmb_subrole.configure(
                values=[""] + list(self._subrole_display_to_id.keys()),
                state="readonly")
            self.var_subrole.set(name)
        else:
            self.var_subrole.set("")
            self._refresh_subrole_combo(epic.get("role_id"))

        self.cmb_role.configure(state="disabled")
        self.cmb_subrole.configure(state="disabled")

        self._refresh_epic_info()
        self._refresh_task_info()
        self._refresh_lists()

    def _on_task_changed(self, _e=None):
        task_name = self.var_task.get().strip()
        if not task_name:
            self.cmb_epic.configure(state="readonly")
            self.cmb_role.configure(state="readonly")
            self.cmb_subrole.configure(
                state="readonly" if self.var_role.get() else "disabled")
            self._refresh_task_info()
            self._refresh_lists()
            return
        task = self._tasks_full_by_name.get(task_name)
        if not task:
            return

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
            subs = db.list_subroles_by_role(task["role_id"]) \
                if task.get("role_id") is not None else []
            name = next((s["name"] for s in subs
                         if s["id"] == task["subrole_id"]), "")
            self._subrole_display_to_id = {s["name"]: s["id"] for s in subs}
            self.cmb_subrole.configure(
                values=[""] + list(self._subrole_display_to_id.keys()),
                state="readonly")
            self.var_subrole.set(name)
        else:
            self.var_subrole.set("")
            self._refresh_subrole_combo(task.get("role_id"))

        self.cmb_epic.configure(state="disabled")
        self.cmb_role.configure(state="disabled")
        self.cmb_subrole.configure(state="disabled")

        self._refresh_epic_info()
        self._refresh_task_info()
        self._refresh_lists()

    def _on_role_selected(self, _e=None):
        if self.var_task.get().strip() or self.var_epic.get().strip():
            return
        role_display = self.var_role.get().strip()
        role_id = self._roles_by_display.get(role_display) if role_display else None
        self._refresh_subrole_combo(role_id)
        self.var_subrole.set("")

    # ---------- сохранение ----------
    def _on_save(self):
        name = self.var_name.get().strip()
        description = self._get_desc().strip()

        if not name and not description:
            messagebox.showwarning(
                "Валидация",
                "Хотя бы одно из полей «Name» / «Description» "
                "должно быть заполнено.",
                parent=self)
            return

        date_text = self.var_date.get().strip()
        if not date_text:
            messagebox.showwarning("Валидация", "Date обязательно.", parent=self)
            return
        try:
            date_iso = _to_iso(date_text)
        except ValueError:
            messagebox.showwarning("Валидация",
                                   "Date должна быть в формате ДД.ММ.ГГГГ.",
                                   parent=self)
            return

        pp_text = self.var_pp.get().strip().replace(",", ".")
        if pp_text:
            try:
                pp = float(pp_text)
            except ValueError:
                messagebox.showwarning("Валидация", "PP должен быть числом.",
                                       parent=self)
                return
        else:
            pp = None

        s_text = self.var_start.get().strip()
        e_text = self.var_end.get().strip()
        if s_text and _hhmm_to_minutes(s_text) is None:
            messagebox.showwarning("Валидация",
                                   "Start должен быть в формате HH:MM.",
                                   parent=self)
            return
        if e_text and _hhmm_to_minutes(e_text) is None:
            messagebox.showwarning("Валидация",
                                   "End должен быть в формате HH:MM.",
                                   parent=self)
            return
        start_time = s_text or None
        end_time = e_text or None

        d_text = self.var_duration.get().strip()
        if d_text:
            try:
                duration = int(d_text)
            except ValueError:
                messagebox.showwarning("Валидация",
                                       "Duration должно быть целым числом.",
                                       parent=self)
                return
            if duration < 0:
                messagebox.showwarning("Валидация",
                                       "Duration не может быть отрицательным.",
                                       parent=self)
                return
        else:
            duration = None

        epic_name = self.var_epic.get().strip()
        epic_id = None
        epic_row = None
        if epic_name:
            epic_row = self._epics_full_by_name.get(epic_name)
            if epic_row is None:
                messagebox.showwarning("Валидация",
                                       f"Эпик '{epic_name}' не найден.",
                                       parent=self)
                return
            epic_id = epic_row["id"]

        task_name = self.var_task.get().strip()
        task_id = None
        task_row = None
        if task_name:
            task_row = self._tasks_full_by_name.get(task_name)
            if task_row is None:
                messagebox.showwarning("Валидация",
                                       f"Задача '{task_name}' не найдена.",
                                       parent=self)
                return
            task_id = task_row["id"]

        if task_row is not None:
            epic_id = task_row["epic_id"]
            role_id = task_row["role_id"]
            subrole_id = task_row["subrole_id"]
        elif epic_row is not None:
            role_id = epic_row["role_id"]
            subrole_id = epic_row["subrole_id"]
        else:
            role_display = self.var_role.get().strip()
            role_id = self._roles_by_display.get(role_display) \
                if role_display else None
            if role_display and role_id is None:
                messagebox.showwarning("Валидация",
                                       f"Роль '{role_display}' не найдена.",
                                       parent=self)
                return

            subrole_display = self.var_subrole.get().strip()
            subrole_id = None
            if subrole_display:
                if role_id is None:
                    messagebox.showwarning("Валидация",
                                           "Нельзя выбрать подроль без роли.",
                                           parent=self)
                    return
                subrole_id = self._subrole_display_to_id.get(subrole_display)
                if subrole_id is None:
                    messagebox.showwarning(
                        "Валидация",
                        f"Подроль '{subrole_display}' не найдена.",
                        parent=self)
                    return

        status_id = self._status_by_name.get(self.var_status.get())
        if status_id is None:
            messagebox.showwarning("Валидация", "Выберите статус.",
                                   parent=self)
            return

        try:
            db.update_action(
                self.action["id"],
                name or None, description or None, date_iso,
                pp, start_time, end_time, duration,
                task_id, epic_id, role_id, subrole_id, status_id,
            )
        except sqlite3.IntegrityError as e:
            messagebox.showwarning("Ошибка", str(e), parent=self)
            return

        self.result = True
        self.destroy()

    def _on_cancel(self):
        self.result = False
        self.destroy()

    # ---------- вспомогательные ----------
    def _set_desc(self, text):
        self.txt_desc.delete("1.0", "end")
        self.txt_desc.insert("1.0", text or "")

    def _get_desc(self):
        return self.txt_desc.get("1.0", "end-1c")

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