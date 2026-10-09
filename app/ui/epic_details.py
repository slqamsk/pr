"""Модальное окно «Детали эпика»: слева — форма эпика,
справа — список задач эпика и форма редактирования задачи.

Эпик и задача сохраняются отдельными кнопками.
Наследование: у задачи role/subrole/macro берутся из формы эпика.
Sprint активен только если у эпика выбран Macro.
"""
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime

from db import db
from ui.widgets import CalendarPopup, ScrollableTable, ask_unsaved_changes
from ui.pf import compute_pf


_TASKS_COLUMNS = [
    {"key": "pf",          "title": "PF",        "width": 60,  "wrap": False},
    {"key": "name",        "title": "Name",      "width": 240, "wrap": True},
    {"key": "deadline",    "title": "Дедлайн",   "width": 90,  "wrap": False},
    {"key": "p1",          "title": "P1",        "width": 45,  "wrap": False},
    {"key": "p2",          "title": "P2",        "width": 45,  "wrap": False},
    {"key": "pp",          "title": "PP",        "width": 45,  "wrap": False},
    {"key": "status_name", "title": "Статус",    "width": 90,  "wrap": False},
    {"key": "sprint_code", "title": "Sprint",    "width": 90,  "wrap": False},
    {"key": "comment",     "title": "Комментарий","width": 200, "wrap": True},
]


def _to_iso(s: str) -> str:
    return datetime.strptime(s.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")


def _to_ru(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")


def _role_display(rid: int, name: str) -> str:
    return f"{rid}. {name}"


class EpicDetailsDialog(tk.Toplevel):
    def __init__(self, parent, epic_row: dict):
        super().__init__(parent)
        self.title(f"Детали эпика — {epic_row.get('name', '')}")
        self.transient(parent)
        self.grab_set()

        self.result = False
        self.epic_row = dict(epic_row)
        self.epic_id = epic_row["id"]

        # Справочники
        self._statuses = db.list_statuses()
        self._status_by_name = {s["name"]: s["id"] for s in self._statuses}
        self._p1_levels = [p["name"] for p in db.list_p1_levels()]
        self._roles_by_display = {}
        self._subrole_display_to_id = {}
        self._macros_by_code = {}    # code -> id
        self._sprints_by_code = {}   # code -> id (для макро эпика)
        self._tasks_by_id = {}       # id -> row

        self._pf_pomodoro = db.get_pomodoro_per_day()

        self.current_task_id = None
        self._epic_snapshot = None
        self._task_snapshot = None

        self._maximized = False
        self._saved_geometry = None

        self._build_ui()
        self._refresh_role_combo()
        self._refresh_macro_combo()
        self._load_epic_form()
        self._refresh_epic_snapshot()
        self._refresh_tasks_list()
        self._clear_task_form()

        # размеры: сначала нормальный, потом развернуть
        self.update_idletasks()
        scr_w = self.winfo_screenwidth()
        scr_h = self.winfo_screenheight()
        w = min(1500, scr_w - 60)
        h = min(900, scr_h - 120)
        px = parent.winfo_rootx() + (parent.winfo_width() - w) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        px = max(0, min(px, scr_w - w))
        py = max(0, min(py, scr_h - h - 60))
        self.geometry(f"{w}x{h}+{px}+{py}")
        self.update_idletasks()
        self._saved_geometry = self.geometry()
        self._apply_maximized()

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        parent.wait_window(self)

    # ---------- построение ----------
    def _build_ui(self):
        outer = ttk.Frame(self, padding=10)
        outer.pack(fill="both", expand=True)

        toolbar = ttk.Frame(outer)
        toolbar.pack(fill="x", pady=(0, 6))
        self.btn_maximize = ttk.Button(toolbar, text="Развернуть",
                                       command=self._toggle_maximize)
        self.btn_maximize.pack(side="left")
        ttk.Button(toolbar, text="Закрыть",
                   command=self._on_close).pack(side="right")

        cols = ttk.Frame(outer)
        cols.pack(fill="both", expand=True)
        cols.columnconfigure(0, weight=1, uniform="c", minsize=400)
        cols.columnconfigure(1, weight=2, uniform="c", minsize=600)
        cols.rowconfigure(0, weight=1)

        self._build_left(cols)
        self._build_right(cols)

    def _apply_maximized(self):
        try:
            scr_w = self.winfo_screenwidth()
            scr_h = self.winfo_screenheight()
            self.geometry(f"{scr_w - 20}x{scr_h - 80}+10+5")
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

    # ---------- левая колонка: эпик ----------
    def _build_left(self, parent):
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        frame.rowconfigure(1, weight=0)

        grp = ttk.LabelFrame(frame, text="Эпик", padding=6)
        grp.grid(row=0, column=0, sticky="nsew")
        grp.columnconfigure(1, weight=1)

        self.var_epic_name      = tk.StringVar()
        self.var_epic_role      = tk.StringVar()
        self.var_epic_subrole   = tk.StringVar()
        self.var_epic_deadline  = tk.StringVar()
        self.var_epic_status    = tk.StringVar()
        self.var_epic_macro     = tk.StringVar()
        self.var_epic_priority  = tk.StringVar()

        r = 0
        ttk.Label(grp, text="Name").grid(row=r, column=0, sticky="w",
                                         padx=(0, 6), pady=2)
        ttk.Entry(grp, textvariable=self.var_epic_name)\
            .grid(row=r, column=1, sticky="ew", pady=2)

        r += 1
        ttk.Label(grp, text="Цель").grid(row=r, column=0, sticky="nw",
                                         padx=(0, 6), pady=2)
        self.txt_epic_goal = tk.Text(grp, height=3, wrap="word",
                                     font=("TkDefaultFont", 9), undo=True)
        self.txt_epic_goal.grid(row=r, column=1, sticky="ew", pady=2)

        r += 1
        ttk.Label(grp, text="Роль").grid(row=r, column=0, sticky="w",
                                         padx=(0, 6), pady=2)
        self.cmb_epic_role = ttk.Combobox(grp, textvariable=self.var_epic_role,
                                          state="readonly")
        self.cmb_epic_role.grid(row=r, column=1, sticky="ew", pady=2)
        self.cmb_epic_role.bind("<<ComboboxSelected>>",
                                self._on_epic_role_selected)

        r += 1
        ttk.Label(grp, text="Подроль").grid(row=r, column=0, sticky="w",
                                            padx=(0, 6), pady=2)
        self.cmb_epic_subrole = ttk.Combobox(grp,
                                             textvariable=self.var_epic_subrole,
                                             state="disabled")
        self.cmb_epic_subrole.grid(row=r, column=1, sticky="ew", pady=2)

        r += 1
        ttk.Label(grp, text="Дедлайн").grid(row=r, column=0, sticky="w",
                                            padx=(0, 6), pady=2)
        f_dl = ttk.Frame(grp)
        f_dl.grid(row=r, column=1, sticky="w", pady=2)
        ttk.Entry(f_dl, textvariable=self.var_epic_deadline, width=12)\
            .pack(side="left")
        ttk.Button(f_dl, text="📅", width=3,
                   command=lambda: self._open_cal(self.var_epic_deadline))\
            .pack(side="left", padx=(4, 0))
        ttk.Button(f_dl, text="✕", width=3,
                   command=lambda: self.var_epic_deadline.set(""))\
            .pack(side="left", padx=(4, 0))

        r += 1
        ttk.Label(grp, text="Статус").grid(row=r, column=0, sticky="w",
                                           padx=(0, 6), pady=2)
        ttk.Combobox(grp, textvariable=self.var_epic_status,
                     values=[s["name"] for s in self._statuses],
                     state="readonly")\
            .grid(row=r, column=1, sticky="ew", pady=2)

        r += 1
        ttk.Label(grp, text="Macro").grid(row=r, column=0, sticky="w",
                                          padx=(0, 6), pady=2)
        self.cmb_epic_macro = ttk.Combobox(grp, textvariable=self.var_epic_macro,
                                           state="readonly")
        self.cmb_epic_macro.grid(row=r, column=1, sticky="ew", pady=2)
        self.cmb_epic_macro.bind("<<ComboboxSelected>>",
                                 self._on_epic_macro_changed)

        r += 1
        ttk.Label(grp, text="P").grid(row=r, column=0, sticky="w",
                                      padx=(0, 6), pady=2)
        ttk.Entry(grp, textvariable=self.var_epic_priority, width=8)\
            .grid(row=r, column=1, sticky="w", pady=2)

        r += 1
        ttk.Label(grp, text="Комментарий").grid(row=r, column=0, sticky="nw",
                                                padx=(0, 6), pady=2)
        self.txt_epic_comment = tk.Text(grp, height=3, wrap="word",
                                        font=("TkDefaultFont", 9), undo=True)
        self.txt_epic_comment.grid(row=r, column=1, sticky="ew", pady=2)

        btns = ttk.Frame(frame)
        btns.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(btns, text="Сохранить эпик",
                   command=self._save_epic).pack(side="left")

    # ---------- правая колонка ----------
    def _build_right(self, parent):
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=1, sticky="nsew", padx=(4, 0))
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        frame.rowconfigure(1, weight=0)
        frame.rowconfigure(2, weight=0)

        # Список задач
        grp_tasks = ttk.LabelFrame(frame, text="Задачи эпика", padding=4)
        grp_tasks.grid(row=0, column=0, sticky="nsew")
        grp_tasks.columnconfigure(0, weight=1)
        grp_tasks.rowconfigure(0, weight=1)
        self.tasks_table = ScrollableTable(grp_tasks, _TASKS_COLUMNS,
                                           on_select=self._on_task_select,
                                           settings_key=None)
        self.tasks_table.grid(row=0, column=0, sticky="nsew")

        # Форма задачи
        grp_task = ttk.LabelFrame(frame, text="Задача", padding=6)
        grp_task.grid(row=1, column=0, sticky="ew", pady=(4, 0))
        grp_task.columnconfigure(1, weight=1)

        self.var_task_name     = tk.StringVar()
        self.var_task_deadline = tk.StringVar()
        self.var_task_pp       = tk.StringVar()
        self.var_task_p1       = tk.StringVar()
        self.var_task_p2       = tk.StringVar()
        self.var_task_pf       = tk.StringVar()
        self.var_task_sprint   = tk.StringVar()
        self.var_task_status   = tk.StringVar()

        r = 0
        ttk.Label(grp_task, text="Name").grid(row=r, column=0, sticky="w",
                                              padx=(0, 6), pady=2)
        ttk.Entry(grp_task, textvariable=self.var_task_name)\
            .grid(row=r, column=1, sticky="ew", pady=2)

        r += 1
        ttk.Label(grp_task, text="Description").grid(row=r, column=0,
                                                     sticky="nw",
                                                     padx=(0, 6), pady=2)
        self.txt_task_desc = tk.Text(grp_task, height=4, wrap="word",
                                     font=("TkDefaultFont", 9), undo=True)
        self.txt_task_desc.grid(row=r, column=1, sticky="ew", pady=2)

        r += 1
        ttk.Label(grp_task, text="Дедлайн").grid(row=r, column=0, sticky="w",
                                                 padx=(0, 6), pady=2)
        f_dl = ttk.Frame(grp_task)
        f_dl.grid(row=r, column=1, sticky="w", pady=2)
        ttk.Entry(f_dl, textvariable=self.var_task_deadline, width=12)\
            .pack(side="left")
        ttk.Button(f_dl, text="📅", width=3,
                   command=lambda: self._open_cal(self.var_task_deadline))\
            .pack(side="left", padx=(4, 0))
        ttk.Button(f_dl, text="✕", width=3,
                   command=lambda: self.var_task_deadline.set(""))\
            .pack(side="left", padx=(4, 0))

        r += 1
        ttk.Label(grp_task, text="PP").grid(row=r, column=0, sticky="w",
                                            padx=(0, 6), pady=2)
        ttk.Entry(grp_task, textvariable=self.var_task_pp, width=8)\
            .grid(row=r, column=1, sticky="w", pady=2)

        r += 1
        ttk.Label(grp_task, text="P1").grid(row=r, column=0, sticky="w",
                                            padx=(0, 6), pady=2)
        ttk.Combobox(grp_task, textvariable=self.var_task_p1,
                     values=[""] + self._p1_levels, state="readonly", width=6)\
            .grid(row=r, column=1, sticky="w", pady=2)

        r += 1
        ttk.Label(grp_task, text="P2").grid(row=r, column=0, sticky="w",
                                            padx=(0, 6), pady=2)
        ttk.Entry(grp_task, textvariable=self.var_task_p2, width=8)\
            .grid(row=r, column=1, sticky="w", pady=2)

        r += 1
        ttk.Label(grp_task, text="PF").grid(row=r, column=0, sticky="w",
                                            padx=(0, 6), pady=2)
        ttk.Label(grp_task, textvariable=self.var_task_pf,
                  foreground="#004080",
                  font=("TkDefaultFont", 10, "bold"))\
            .grid(row=r, column=1, sticky="w", pady=2)

        r += 1
        ttk.Label(grp_task, text="Sprint").grid(row=r, column=0, sticky="w",
                                                padx=(0, 6), pady=2)
        self.cmb_task_sprint = ttk.Combobox(grp_task,
                                            textvariable=self.var_task_sprint,
                                            state="disabled")
        self.cmb_task_sprint.grid(row=r, column=1, sticky="ew", pady=2)

        r += 1
        ttk.Label(grp_task, text="Статус").grid(row=r, column=0, sticky="w",
                                                padx=(0, 6), pady=2)
        ttk.Combobox(grp_task, textvariable=self.var_task_status,
                     values=[s["name"] for s in self._statuses],
                     state="readonly")\
            .grid(row=r, column=1, sticky="ew", pady=2)

        r += 1
        ttk.Label(grp_task, text="Комментарий").grid(row=r, column=0,
                                                     sticky="nw",
                                                     padx=(0, 6), pady=2)
        self.txt_task_comment = tk.Text(grp_task, height=3, wrap="word",
                                        font=("TkDefaultFont", 9), undo=True)
        self.txt_task_comment.grid(row=r, column=1, sticky="ew", pady=2)

        # Кнопки
        btns = ttk.Frame(frame)
        btns.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(btns, text="Новая задача", command=self._new_task)\
            .pack(side="left")
        ttk.Button(btns, text="Сохранить задачу", command=self._save_task)\
            .pack(side="left", padx=6)
        ttk.Button(btns, text="Удалить", command=self._delete_task)\
            .pack(side="left")

        # Автопересчёт PF на лету
        for v in (self.var_task_p1, self.var_task_p2, self.var_task_pp,
                  self.var_task_deadline, self.var_task_status):
            v.trace_add("write", lambda *_: self._recompute_task_pf())

    # ---------- справочники ----------
    def _refresh_role_combo(self):
        roles = db.list_roles()
        self._roles_by_display = {_role_display(r["id"], r["name"]): r["id"]
                                  for r in roles}
        self.cmb_epic_role.configure(values=[""] +
                                     list(self._roles_by_display.keys()))

    def _refresh_macro_combo(self):
        brief = db.list_macro_sprints_brief()
        self._macros_by_code = {m["code"]: m["id"] for m in brief}
        self.cmb_epic_macro.configure(values=[""] +
                                      list(self._macros_by_code.keys()))

    def _refresh_sprint_combo(self):
        """Sprint у задачи — из макро эпика (текущее значение формы эпика)."""
        macro_code = self.var_epic_macro.get().strip()
        if not macro_code:
            self._sprints_by_code = {}
            self.cmb_task_sprint.configure(values=[], state="disabled")
            return
        macro_id = self._macros_by_code.get(macro_code)
        if macro_id is None:
            self._sprints_by_code = {}
            self.cmb_task_sprint.configure(values=[], state="disabled")
            return
        brief = db.list_sprints_brief()
        sprints = [s for s in brief if s["macro_sprint_id"] == macro_id]
        self._sprints_by_code = {s["code"]: s["id"] for s in sprints}
        self.cmb_task_sprint.configure(
            values=[""] + list(self._sprints_by_code.keys()),
            state="readonly")

    def _refresh_subrole_combo(self, role_id):
        if role_id is None:
            self._subrole_display_to_id = {}
            self.cmb_epic_subrole.configure(values=[], state="disabled")
            return
        subs = db.list_subroles_by_role(role_id)
        self._subrole_display_to_id = {s["name"]: s["id"] for s in subs}
        self.cmb_epic_subrole.configure(
            values=[""] + list(self._subrole_display_to_id.keys()),
            state="readonly")

    # ---------- обработчики эпика ----------
    def _on_epic_role_selected(self, _e=None):
        role_display = self.var_epic_role.get().strip()
        role_id = self._roles_by_display.get(role_display) if role_display else None
        self._refresh_subrole_combo(role_id)
        self.var_epic_subrole.set("")

    def _on_epic_macro_changed(self, _e=None):
        # макро эпика влияет на доступность спринта у задачи
        self._refresh_sprint_combo()
        # сбрасываем спринт, если он не из нового макро
        current = self.var_task_sprint.get().strip()
        if current and current not in self._sprints_by_code:
            self.var_task_sprint.set("")

    # ---------- загрузка формы эпика ----------
    def _load_epic_form(self):
        r = self.epic_row
        self.var_epic_name.set(r.get("name") or "")
        self._set_text(self.txt_epic_goal, r.get("goal") or "")

        if r.get("role_id") is not None and r.get("role_name"):
            self.var_epic_role.set(_role_display(r["role_id"], r["role_name"]))
        else:
            self.var_epic_role.set("")
        self._on_epic_role_selected()  # заполнить список подролей

        self.var_epic_subrole.set(r.get("subrole_name") or "")
        self.var_epic_deadline.set(
            _to_ru(r["deadline"]) if r.get("deadline") else "")
        self.var_epic_status.set(r.get("status_name") or "")
        self.var_epic_macro.set(r.get("macro_code") or "")
        self.var_epic_priority.set(
            "" if r.get("priority") is None else str(r["priority"]))
        self._set_text(self.txt_epic_comment, r.get("comment") or "")

        # после установки макро — обновить доступность спринта у задачи
        self._refresh_sprint_combo()

    def _reload_epic_row(self):
        for r in db.list_epics():
            if r["id"] == self.epic_id:
                self.epic_row = dict(r)
                return

    # ---------- сохранение эпика ----------
    def _save_epic(self) -> bool:
        name = self.var_epic_name.get().strip()
        if not name:
            messagebox.showwarning("Валидация", "Epic Name не может быть пустым.",
                                   parent=self)
            return False

        role_display = self.var_epic_role.get().strip()
        role_id = None
        if role_display:
            role_id = self._roles_by_display.get(role_display)
            if role_id is None:
                messagebox.showwarning("Валидация",
                                       f"Роль '{role_display}' не найдена.",
                                       parent=self)
                return False

        subrole_display = self.var_epic_subrole.get().strip()
        subrole_id = None
        if subrole_display:
            if role_id is None:
                messagebox.showwarning("Валидация",
                                       "Нельзя выбрать подроль без роли.",
                                       parent=self)
                return False
            subrole_id = self._subrole_display_to_id.get(subrole_display)
            if subrole_id is None:
                messagebox.showwarning(
                    "Валидация",
                    f"Подроль '{subrole_display}' не найдена.",
                    parent=self)
                return False

        dl_text = self.var_epic_deadline.get().strip()
        if dl_text:
            try:
                deadline = _to_iso(dl_text)
            except ValueError:
                messagebox.showwarning(
                    "Валидация",
                    "Дедлайн должен быть в формате ДД.ММ.ГГГГ.",
                    parent=self)
                return False
        else:
            deadline = None

        status_id = self._status_by_name.get(self.var_epic_status.get())
        if status_id is None:
            messagebox.showwarning("Валидация", "Выберите статус.",
                                   parent=self)
            return False

        macro_code = self.var_epic_macro.get().strip()
        macro_id = None
        if macro_code:
            macro_id = self._macros_by_code.get(macro_code)
            if macro_id is None:
                messagebox.showwarning(
                    "Валидация",
                    f"Макро-спринт '{macro_code}' не найден.",
                    parent=self)
                return False

        pr_text = self.var_epic_priority.get().strip()
        if pr_text == "":
            priority = None
        else:
            try:
                priority = int(pr_text)
            except ValueError:
                messagebox.showwarning("Валидация",
                                       "P должно быть целым числом.",
                                       parent=self)
                return False

        goal = self._get_text(self.txt_epic_goal).strip() or None
        comment = self._get_text(self.txt_epic_comment).strip() or None

        try:
            db.update_epic(self.epic_id, name, goal, role_id, subrole_id,
                           deadline, status_id, macro_id, comment, priority)
        except sqlite3.IntegrityError as e:
            msg = str(e)
            if "epics.name" in msg or "UNIQUE" in msg.upper():
                messagebox.showwarning(
                    "Валидация",
                    f"Epic Name «{name}» уже используется.",
                    parent=self)
            else:
                messagebox.showwarning("Валидация", msg, parent=self)
            return False

        self._reload_epic_row()
        self._refresh_epic_snapshot()
        self.result = True
        return True

    # ---------- работа с задачами ----------
    def _refresh_tasks_list(self):
        all_tasks = db.list_tasks()
        rows = [t for t in all_tasks if t["epic_id"] == self.epic_id]
        rows.sort(key=lambda t: (
            t["pf"] is None,
            t["pf"] if t["pf"] is not None else 0.0,
            t["name"] or "",
        ))
        self._tasks_by_id = {t["id"]: t for t in rows}

        display = []
        for t in rows:
            pf_val = t.get("pf")
            display.append({
                "id":          t["id"],
                "pf":          "" if pf_val is None else f"{float(pf_val):.2f}",
                "name":        t["name"] or "",
                "deadline":    _to_ru(t["deadline"]) if t["deadline"] else "",
                "p1":          t["p1"] or "",
                "p2":          "" if t["p2"] is None else t["p2"],
                "pp":          "" if t["pp"] is None else f"{t['pp']:.1f}",
                "status_name": t["status_name"] or "",
                "sprint_code": t["sprint_code"] or "",
                "comment":     t["comment"] or "",
            })
        self.tasks_table.set_rows(display, iid_key="id")
        if self.current_task_id is not None and self.current_task_id in self._tasks_by_id:
            self.tasks_table.select_iid(str(self.current_task_id))

    def _load_task_into_form(self, task_row: dict):
        self.current_task_id = task_row["id"]
        self.var_task_name.set(task_row["name"] or "")
        self._set_text(self.txt_task_desc, task_row.get("description") or "")
        self.var_task_deadline.set(
            _to_ru(task_row["deadline"]) if task_row.get("deadline") else "")
        self.var_task_pp.set(
            "" if task_row.get("pp") is None else f"{task_row['pp']:.1f}")
        self.var_task_p1.set(task_row.get("p1") or "")
        self.var_task_p2.set(
            "" if task_row.get("p2") is None else str(task_row["p2"]))
        pf_val = task_row.get("pf")
        self.var_task_pf.set("" if pf_val is None else f"{float(pf_val):.2f}")
        self.var_task_status.set(task_row.get("status_name") or "")
        self._refresh_sprint_combo()
        self.var_task_sprint.set(task_row.get("sprint_code") or "")
        self._set_text(self.txt_task_comment, task_row.get("comment") or "")
        self._refresh_task_snapshot()

    def _clear_task_form(self):
        self.current_task_id = None
        self.var_task_name.set("")
        self._set_text(self.txt_task_desc, "")
        self.var_task_deadline.set("")
        self.var_task_pp.set("")
        self.var_task_p1.set("")
        self.var_task_p2.set("")
        self.var_task_pf.set("")
        if self._statuses:
            self.var_task_status.set(self._statuses[0]["name"])
        self._refresh_sprint_combo()
        self.var_task_sprint.set("")
        self._set_text(self.txt_task_comment, "")
        self.tasks_table.clear_selection()
        self._refresh_task_snapshot()

    def _on_task_select(self, data):
        new_id = data["id"]
        if new_id == self.current_task_id:
            return
        if self._is_task_dirty():
            ans = ask_unsaved_changes(parent=self)
            if ans == "cancel":
                self._restore_task_selection()
                return
            if ans == "save":
                if not self._save_task():
                    self._restore_task_selection()
                    return
        row = self._tasks_by_id.get(new_id)
        if row is not None:
            self._load_task_into_form(row)

    def _restore_task_selection(self):
        if self.current_task_id is None:
            self.tasks_table.clear_selection()
        else:
            self.tasks_table.select_iid(str(self.current_task_id))

    def _new_task(self):
        if self._is_task_dirty():
            ans = ask_unsaved_changes(parent=self)
            if ans == "cancel":
                return
            if ans == "save":
                if not self._save_task():
                    return
        self._clear_task_form()

    def _save_task(self) -> bool:
        if self._is_epic_dirty():
            messagebox.showinfo(
                "Сначала сохраните эпик",
                "Есть несохранённые изменения в эпике. "
                "Сохраните их перед сохранением задачи.",
                parent=self)
            return False

        name = self.var_task_name.get().strip()
        if not name:
            messagebox.showwarning("Валидация",
                                   "Task Name не может быть пустым.",
                                   parent=self)
            return False

        dl_text = self.var_task_deadline.get().strip()
        if dl_text:
            try:
                deadline = _to_iso(dl_text)
            except ValueError:
                messagebox.showwarning(
                    "Валидация",
                    "Дедлайн должен быть в формате ДД.ММ.ГГГГ.",
                    parent=self)
                return False
        else:
            deadline = None

        pp_text = self.var_task_pp.get().strip().replace(",", ".")
        if pp_text:
            try:
                pp = float(pp_text)
            except ValueError:
                messagebox.showwarning("Валидация", "PP должен быть числом.",
                                       parent=self)
                return False
        else:
            pp = None

        p1 = self.var_task_p1.get().strip() or None
        if p1 is not None and p1 not in self._p1_levels:
            messagebox.showwarning("Валидация",
                                   f"P1 '{p1}' не из справочника.",
                                   parent=self)
            return False

        p2_text = self.var_task_p2.get().strip()
        if p2_text:
            try:
                p2 = int(p2_text)
            except ValueError:
                messagebox.showwarning("Валидация",
                                       "P2 должен быть целым числом.",
                                       parent=self)
                return False
            if p2 <= 0:
                messagebox.showwarning("Валидация",
                                       "P2 должен быть положительным числом.",
                                       parent=self)
                return False
        else:
            p2 = None

        status_id = self._status_by_name.get(self.var_task_status.get())
        if status_id is None:
            messagebox.showwarning("Валидация", "Выберите статус.",
                                   parent=self)
            return False

        # Роль/подроль/макро — из формы эпика (актуальные)
        role_display = self.var_epic_role.get().strip()
        role_id = self._roles_by_display.get(role_display) if role_display else None

        subrole_display = self.var_epic_subrole.get().strip()
        subrole_id = (self._subrole_display_to_id.get(subrole_display)
                      if subrole_display else None)

        macro_code = self.var_epic_macro.get().strip()
        macro_id = self._macros_by_code.get(macro_code) if macro_code else None

        # Sprint — только из выбранного
        sprint_code = self.var_task_sprint.get().strip()
        sprint_id = None
        if sprint_code:
            if macro_id is None:
                messagebox.showwarning(
                    "Валидация",
                    "Sprint нельзя указать, у эпика не выбран Macro.",
                    parent=self)
                return False
            sprint_id = self._sprints_by_code.get(sprint_code)
            if sprint_id is None:
                messagebox.showwarning(
                    "Валидация",
                    f"Sprint '{sprint_code}' не принадлежит макро эпика.",
                    parent=self)
                return False

        description = self._get_text(self.txt_task_desc).strip() or None
        comment = self._get_text(self.txt_task_comment).strip() or None

        try:
            if self.current_task_id is None:
                new_id = db.insert_task(
                    name, description, self.epic_id, role_id, subrole_id,
                    p1, p2, deadline, pp, status_id,
                    macro_id, sprint_id, comment,
                )
                self.current_task_id = new_id
            else:
                db.update_task(
                    self.current_task_id, name, description,
                    self.epic_id, role_id, subrole_id,
                    p1, p2, deadline, pp, status_id,
                    macro_id, sprint_id, comment,
                )
        except sqlite3.IntegrityError as e:
            msg = str(e)
            if "tasks.name" in msg or "UNIQUE" in msg.upper():
                messagebox.showwarning("Валидация",
                                       f"Task Name «{name}» уже используется.",
                                       parent=self)
            else:
                messagebox.showwarning("Валидация", msg, parent=self)
            return False

        # Пересчёт PF и сохранение в БД
        pf = compute_pf(self.var_task_status.get().strip(),
                        p1, p2, deadline, pp,
                        pomodoro_per_day=self._pf_pomodoro)
        try:
            db.update_task_pf(self.current_task_id, pf)
        except Exception:
            pass

        self._refresh_task_snapshot()
        self._refresh_tasks_list()
        self.result = True
        return True

    def _delete_task(self):
        if self.current_task_id is None:
            messagebox.showinfo("Удаление", "Выбери задачу из списка.",
                                parent=self)
            return
        name = self.var_task_name.get().strip()
        if not messagebox.askyesno("Удаление", f"Удалить задачу «{name}»?",
                                   parent=self):
            return
        db.delete_task(self.current_task_id)
        self._clear_task_form()
        self._refresh_tasks_list()
        self.result = True

    # ---------- пересчёт PF ----------
    def _recompute_task_pf(self):
        p1 = self.var_task_p1.get().strip() or None
        p2_text = self.var_task_p2.get().strip()
        p2 = None
        if p2_text:
            try:
                p2 = int(p2_text)
            except ValueError:
                p2 = None
        dl_text = self.var_task_deadline.get().strip()
        deadline_iso = None
        if dl_text:
            try:
                deadline_iso = _to_iso(dl_text)
            except ValueError:
                deadline_iso = None
        pp_text = self.var_task_pp.get().strip().replace(",", ".")
        pp = None
        if pp_text:
            try:
                pp = float(pp_text)
            except ValueError:
                pp = None
        status = self.var_task_status.get().strip() or None
        pf = compute_pf(status, p1, p2, deadline_iso, pp,
                        pomodoro_per_day=self._pf_pomodoro)
        self.var_task_pf.set(f"{pf:.2f}")

    # ---------- снимки для контроля изменений ----------
    def _epic_form_state(self) -> dict:
        return {
            "name":     self.var_epic_name.get().strip(),
            "goal":     self._get_text(self.txt_epic_goal).strip(),
            "role":     self.var_epic_role.get().strip(),
            "subrole":  self.var_epic_subrole.get().strip(),
            "deadline": self.var_epic_deadline.get().strip(),
            "status":   self.var_epic_status.get(),
            "macro":    self.var_epic_macro.get().strip(),
            "priority": self.var_epic_priority.get().strip(),
            "comment":  self._get_text(self.txt_epic_comment).strip(),
        }

    def _refresh_epic_snapshot(self):
        self._epic_snapshot = self._epic_form_state()

    def _is_epic_dirty(self) -> bool:
        if self._epic_snapshot is None:
            return False
        return self._epic_form_state() != self._epic_snapshot

    def _task_form_state(self) -> dict:
        return {
            "name":     self.var_task_name.get().strip(),
            "desc":     self._get_text(self.txt_task_desc).strip(),
            "deadline": self.var_task_deadline.get().strip(),
            "pp":       self.var_task_pp.get().strip(),
            "p1":       self.var_task_p1.get().strip(),
            "p2":       self.var_task_p2.get().strip(),
            "sprint":   self.var_task_sprint.get().strip(),
            "status":   self.var_task_status.get(),
            "comment":  self._get_text(self.txt_task_comment).strip(),
        }

    def _refresh_task_snapshot(self):
        self._task_snapshot = self._task_form_state()

    def _is_task_dirty(self) -> bool:
        if self._task_snapshot is None:
            return False
        return self._task_form_state() != self._task_snapshot

    # ---------- закрытие ----------
    def _on_close(self):
        if self._is_task_dirty():
            ans = ask_unsaved_changes(parent=self)
            if ans == "cancel":
                return
            if ans == "save":
                if not self._save_task():
                    return
        if self._is_epic_dirty():
            ans = ask_unsaved_changes(parent=self)
            if ans == "cancel":
                return
            if ans == "save":
                if not self._save_epic():
                    return
        self.destroy()

    # ---------- вспомогательные ----------
    @staticmethod
    def _set_text(widget: tk.Text, text: str):
        widget.delete("1.0", "end")
        if text:
            widget.insert("1.0", text)

    @staticmethod
    def _get_text(widget: tk.Text) -> str:
        return widget.get("1.0", "end-1c")

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