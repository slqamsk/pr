"""Вкладка работы со спринтами."""
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime

from db import db
from ui.widgets import (CalendarPopup, ScrollableTable,
                        ask_unsaved_changes, EditableCriteriaList)

COLUMNS = [
    {"key": "code",        "title": "Code",   "width": 90,  "wrap": False},
    {"key": "start_date",  "title": "Start",  "width": 100, "wrap": False},
    {"key": "end_date",    "title": "End",    "width": 100, "wrap": False},
    {"key": "goal",        "title": "Goal",   "width": 400, "wrap": True},
    {"key": "status_name", "title": "Status", "width": 90,  "wrap": False},
    {"key": "macro_code",  "title": "Macro",  "width": 110, "wrap": False},
]


def _to_iso(s: str) -> str:
    return datetime.strptime(s.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")


def _to_ru(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")


class SprintsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=8)
        self.current_id: int | None = None
        self._raw_by_id: dict[int, dict] = {}
        self._snapshot: dict | None = None

        self._statuses: list[dict] = []
        self._status_by_name: dict[str, int] = {}

        self._crit_statuses: list[dict] = []
        self._crit_status_by_name: dict[str, int] = {}

        self._macro_by_code: dict[str, int] = {}

        self._build_ui()
        self.refresh()
        self._set_snapshot()

    # ---------- UI ----------
    def _build_ui(self):
        self._statuses = db.list_statuses()
        self._status_by_name = {s["name"]: s["id"] for s in self._statuses}

        self._crit_statuses = db.list_criterion_statuses()
        self._crit_status_by_name = {s["name"]: s["id"] for s in self._crit_statuses}

        # ---- Нижний ряд кнопок ----
        btns = ttk.Frame(self, padding=(0, 8, 0, 0))
        ttk.Button(btns, text="Новая",     command=self._new).pack(side="left")
        ttk.Button(btns, text="Сохранить", command=self._on_save_clicked).pack(side="left", padx=6)
        ttk.Button(btns, text="Удалить",   command=self._delete).pack(side="left")
        ttk.Button(btns, text="Обновить",  command=self._on_refresh_clicked).pack(side="right")

        # ---- Двухколоночный блок: Запись | Критерии ----
        two_col = ttk.Frame(self)
        two_col.columnconfigure(0, weight=1, uniform="f")
        two_col.columnconfigure(1, weight=1, uniform="f")

        # Форма — слева
        form = ttk.LabelFrame(two_col, text="Запись", padding=8)
        form.grid(row=0, column=0, sticky="nsew", padx=(0, 4))
        form.columnconfigure(1, weight=1)

        self.var_code   = tk.StringVar()
        self.var_start  = tk.StringVar()
        self.var_end    = tk.StringVar()
        self.var_status = tk.StringVar()
        self.var_macro  = tk.StringVar(value="")

        r = 0
        ttk.Label(form, text="Code").grid(row=r, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(form, textvariable=self.var_code, width=14)\
            .grid(row=r, column=1, sticky="w", pady=2)

        r += 1
        ttk.Label(form, text="Start").grid(row=r, column=0, sticky="w", padx=(0, 8), pady=2)
        f_start = ttk.Frame(form)
        f_start.grid(row=r, column=1, sticky="w", pady=2)
        ttk.Entry(f_start, textvariable=self.var_start, width=14).pack(side="left")
        ttk.Button(f_start, text="📅", width=3,
                   command=lambda: self._open_cal(self.var_start)).pack(side="left", padx=(4, 0))

        r += 1
        ttk.Label(form, text="End").grid(row=r, column=0, sticky="w", padx=(0, 8), pady=2)
        f_end = ttk.Frame(form)
        f_end.grid(row=r, column=1, sticky="w", pady=2)
        ttk.Entry(f_end, textvariable=self.var_end, width=14).pack(side="left")
        ttk.Button(f_end, text="📅", width=3,
                   command=lambda: self._open_cal(self.var_end)).pack(side="left", padx=(4, 0))

        r += 1
        ttk.Label(form, text="Goal").grid(row=r, column=0, sticky="nw", padx=(0, 8), pady=2)
        goal_wrap = ttk.Frame(form)
        goal_wrap.grid(row=r, column=1, sticky="ew", pady=2)
        goal_wrap.columnconfigure(0, weight=1)
        self.txt_goal = tk.Text(goal_wrap, height=3, wrap="word",
                                font=("TkDefaultFont", 9), undo=True)
        self.txt_goal.grid(row=0, column=0, sticky="ew")
        goal_sb = ttk.Scrollbar(goal_wrap, orient="vertical", command=self.txt_goal.yview)
        self.txt_goal.configure(yscrollcommand=goal_sb.set)
        goal_sb.grid(row=0, column=1, sticky="ns")

        r += 1
        ttk.Label(form, text="Status").grid(row=r, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Combobox(form, textvariable=self.var_status,
                     values=[s["name"] for s in self._statuses],
                     state="readonly", width=12)\
            .grid(row=r, column=1, sticky="w", pady=2)

        r += 1
        ttk.Label(form, text="Macro").grid(row=r, column=0, sticky="w", padx=(0, 8), pady=2)
        self.cmb_macro = ttk.Combobox(form, textvariable=self.var_macro,
                                      values=[""], state="readonly", width=14)
        self.cmb_macro.grid(row=r, column=1, sticky="w", pady=2)

        # Критерии — справа
        grp_crit = ttk.LabelFrame(two_col, text="Критерии достижения", padding=8)
        grp_crit.grid(row=0, column=1, sticky="nsew", padx=(4, 0))

        self.criteria_list = EditableCriteriaList(
            grp_crit,
            statuses=[s["name"] for s in self._crit_statuses],
        )
        self.criteria_list.pack(fill="both", expand=True)
        self.btn_add_criterion = ttk.Button(grp_crit, text="Добавить",
                                            command=self.criteria_list.add_item)
        self.btn_add_criterion.pack(anchor="w", pady=(6, 0))

        # ---- Таблица ----
        self.table = ScrollableTable(self, COLUMNS, on_select=self._on_table_select,
                                     settings_key="ui.columns.sprints")

        # ---- Упаковка снизу вверх ----
        btns.pack(side="bottom", fill="x")
        two_col.pack(side="bottom", fill="both", expand=False, pady=(8, 0))
        self.table.pack(side="top", fill="both", expand=True)

    # ---------- снимок ----------
    def _form_state(self) -> dict:
        criteria = tuple(
            (c["n"], c["text"], c["status_name"] or "", c["comment"] or "")
            for c in self.criteria_list.get_items()
        )
        return {
            "code":     self.var_code.get().strip(),
            "start":    self.var_start.get().strip(),
            "end":      self.var_end.get().strip(),
            "goal":     self._get_goal(),
            "status":   self.var_status.get(),
            "macro":    self.var_macro.get().strip(),
            "criteria": criteria,
        }

    def _set_snapshot(self):
        self._snapshot = self._form_state()

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
        brief = db.list_macro_sprints_brief()
        self._macro_by_code = {m["code"]: m["id"] for m in brief}
        self.cmb_macro.configure(values=[""] + list(self._macro_by_code.keys()))

        raw = db.list_sprints()
        self._raw_by_id = {r["id"]: r for r in raw}
        display = [{
            "id":          r["id"],
            "code":        r["code"],
            "start_date":  _to_ru(r["start_date"]),
            "end_date":    _to_ru(r["end_date"]),
            "goal":        r["goal"],
            "status_name": r["status_name"],
            "macro_code":  r["macro_code"] or "",
        } for r in raw]
        self.table.set_rows(display, iid_key="id")
        if self.current_id is not None:
            self.table.select_iid(str(self.current_id))

    def _load_into_form(self, sid: int):
        self.current_id = sid
        src = self._raw_by_id.get(sid)
        if not src:
            return
        self.var_code.set(src["code"])
        self.var_start.set(_to_ru(src["start_date"]))
        self.var_end.set(_to_ru(src["end_date"]))
        self.var_status.set(src["status_name"])
        self.var_macro.set(src["macro_code"] or "")
        self._set_goal(src["goal"])

        crit = db.list_sprint_criteria(sid)
        items = [{
            "n":           c["n"],
            "text":        c["text"],
            "status_name": c["status_name"] or "",
            "comment":     c["comment"] or "",
        } for c in crit]
        self.criteria_list.set_items(items)

        self._set_snapshot()
        self.table.select_iid(str(sid))

    def _set_goal(self, text):
        self.txt_goal.delete("1.0", "end")
        self.txt_goal.insert("1.0", text or "")

    def _get_goal(self):
        return self.txt_goal.get("1.0", "end-1c").strip()

    def _clear_form(self):
        self.current_id = None
        self.var_code.set("")
        self.var_start.set("")
        self.var_end.set("")
        self.var_status.set(self._statuses[0]["name"] if self._statuses else "")
        self.var_macro.set("")
        self._set_goal("")
        self.criteria_list.clear()
        self.table.clear_selection()
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

    def _collect_criteria_for_db(self) -> list[dict] | None:
        raw = self.criteria_list.get_items()
        result = []
        for c in raw:
            text = c["text"]
            if not text:
                if not c["status_name"] and not c["comment"]:
                    continue
                messagebox.showwarning("Валидация",
                                       "У критерия должен быть текст.",
                                       parent=self.winfo_toplevel())
                return None
            n = c["n"] if c["n"] is not None else 0
            status_id = None
            if c["status_name"]:
                status_id = self._crit_status_by_name.get(c["status_name"])
                if status_id is None:
                    messagebox.showwarning("Валидация",
                                           f"Неизвестный статус критерия: {c['status_name']!r}",
                                           parent=self.winfo_toplevel())
                    return None
            result.append({
                "n":         n,
                "text":      text,
                "status_id": status_id,
                "comment":   c["comment"],
            })
        return result

    def _save(self) -> bool:
        code = self.var_code.get().strip()
        if not code:
            messagebox.showwarning("Валидация", "Code не может быть пустым.",
                                   parent=self.winfo_toplevel())
            return False
        try:
            start = _to_iso(self.var_start.get())
            end   = _to_iso(self.var_end.get())
        except ValueError:
            messagebox.showwarning("Валидация",
                                   "Даты должны быть в формате ДД.ММ.ГГГГ.",
                                   parent=self.winfo_toplevel())
            return False
        if end < start:
            if not messagebox.askyesno("Валидация",
                                       "End раньше Start. Всё равно сохранить?",
                                       parent=self.winfo_toplevel()):
                return False

        status_name = self.var_status.get()
        status_id = self._status_by_name.get(status_name)
        if status_id is None:
            messagebox.showwarning("Валидация", "Выберите статус.",
                                   parent=self.winfo_toplevel())
            return False

        macro_code = self.var_macro.get().strip()
        macro_id = None
        if macro_code:
            macro_id = self._macro_by_code.get(macro_code)
            if macro_id is None:
                messagebox.showwarning("Валидация",
                                       f"Макро-спринт '{macro_code}' не найден.",
                                       parent=self.winfo_toplevel())
                return False

        criteria = self._collect_criteria_for_db()
        if criteria is None:
            return False

        goal = self._get_goal()

        try:
            if self.current_id is None:
                new_id = db.insert_sprint(code, start, end, goal,
                                          status_id, macro_id)
                self.current_id = new_id
            else:
                db.update_sprint(self.current_id, code, start, end,
                                 goal, status_id, macro_id)
            db.replace_sprint_criteria(self.current_id, criteria)
        except sqlite3.IntegrityError:
            messagebox.showwarning("Валидация", f"Code '{code}' уже существует.",
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
        code = self.var_code.get().strip()

        n_tasks = db.count_tasks_using_sprint(self.current_id)
        if n_tasks > 0:
            messagebox.showwarning(
                "Удаление запрещено",
                f"Спринт «{code}» используется в {n_tasks} задач(ах).\n\n"
                "Сначала отвяжите или удалите эти задачи на вкладке «Задачи».",
                parent=self.winfo_toplevel(),
            )
            return

        if not messagebox.askyesno("Удаление", f"Удалить {code}?",
                                   parent=self.winfo_toplevel()):
            return
        db.delete_sprint(self.current_id)
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