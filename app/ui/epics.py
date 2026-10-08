"""Вкладка работы с эпиками."""
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime

from db import db
from ui.widgets import (CalendarPopup, ScrollableTable, ask_unsaved_changes,
                        setup_vertical_paned)

COLUMNS = [
    {"key": "name",         "title": "Epic Name",   "width": 200, "wrap": True},
    {"key": "goal",         "title": "Цель",        "width": 280, "wrap": True},
    {"key": "role_name",    "title": "Роль",        "width": 150, "wrap": True},
    {"key": "subrole_name", "title": "Подроль",     "width": 150, "wrap": True},
    {"key": "deadline",     "title": "Дедлайн",     "width": 100, "wrap": False},
    {"key": "status_name",  "title": "Статус",      "width": 90,  "wrap": False},
    {"key": "macro_code",   "title": "Macro",       "width": 90,  "wrap": False},
    {"key": "comment",      "title": "Комментарий", "width": 240, "wrap": True},
    {"key": "priority",     "title": "P",           "width": 50,  "wrap": False},
]


def _to_iso(s: str) -> str:
    return datetime.strptime(s.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")


def _to_ru(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")


def _role_display(rid: int, name: str) -> str:
    return f"{rid}. {name}"


class EpicsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=8)
        self.current_id: int | None = None
        self._raw_by_id: dict[int, dict] = {}
        self._snapshot: dict | None = None

        self._statuses: list[dict] = []
        self._status_by_name: dict[str, int] = {}
        self._status_by_id: dict[int, str] = {}

        self._roles_by_display: dict[str, int] = {}
        self._role_display_by_id: dict[int, str] = {}
        self._subrole_display_to_id: dict[str, int] = {}

        self._macros_by_code: dict[str, int] = {}

        self._save_ui_state_impl = None

        self._build_ui()
        self.refresh()
        self._set_snapshot()

    def _build_ui(self):
        self._statuses = db.list_statuses()
        self._status_by_name = {s["name"]: s["id"] for s in self._statuses}
        self._status_by_id = {s["id"]: s["name"] for s in self._statuses}

        btns = ttk.Frame(self, padding=(0, 8, 0, 0))
        ttk.Button(btns, text="Новая",     command=self._new).pack(side="left")
        ttk.Button(btns, text="Сохранить", command=self._on_save_clicked).pack(side="left", padx=6)
        ttk.Button(btns, text="Удалить",   command=self._delete).pack(side="left")
        ttk.Button(btns, text="Обновить",  command=self._on_refresh_clicked).pack(side="right")
        btns.pack(side="bottom", fill="x")

        self._paned, self._save_ui_state_impl = setup_vertical_paned(
            self, "ui.sash.epics"
        )
        self.table = ScrollableTable(self._paned, COLUMNS,
                                     on_select=self._on_table_select,
                                     settings_key="ui.columns.epics")
        self._paned.add(self.table, weight=2)
        self._bottom = ttk.Frame(self._paned)
        self._paned.add(self._bottom, weight=1)

        form = ttk.LabelFrame(self._bottom, text="Запись", padding=8)
        form.pack(fill="both", expand=True, pady=(8, 0))
        form.columnconfigure(0, weight=3)
        form.columnconfigure(1, weight=1)
        form.rowconfigure(0, weight=1)

        # ---------- Левая колонка: Epic Name / Цель / Комментарий ----------
        left = ttk.Frame(form)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=0)   # подписи
        left.columnconfigure(1, weight=1)   # значения
        left.rowconfigure(0, weight=0)      # Epic Name — фиксирован
        left.rowconfigure(1, weight=1)      # Цель — растёт
        left.rowconfigure(2, weight=1)      # Комментарий — растёт

        # --- Epic Name (однострочный, фиксирован по высоте) ---
        ttk.Label(left, text="Epic Name").grid(row=0, column=0, sticky="w",
                                               padx=(0, 8), pady=(0, 4))
        self.var_name = tk.StringVar()
        ttk.Entry(left, textvariable=self.var_name)\
            .grid(row=0, column=1, sticky="ew", pady=(0, 4))

        # --- Цель (Text, растягивается) ---
        ttk.Label(left, text="Цель").grid(row=1, column=0, sticky="nw",
                                          padx=(0, 8), pady=(0, 4))
        goal_wrap = ttk.Frame(left)
        goal_wrap.grid(row=1, column=1, sticky="nsew", pady=(0, 4))
        goal_wrap.columnconfigure(0, weight=1)
        goal_wrap.rowconfigure(0, weight=1)
        self.txt_goal = tk.Text(goal_wrap, height=4, wrap="word",
                                font=("TkDefaultFont", 9), undo=True)
        self.txt_goal.grid(row=0, column=0, sticky="nsew")
        gsb = ttk.Scrollbar(goal_wrap, orient="vertical", command=self.txt_goal.yview)
        self.txt_goal.configure(yscrollcommand=gsb.set)
        gsb.grid(row=0, column=1, sticky="ns")

        # --- Комментарий (Text, растягивается) ---
        ttk.Label(left, text="Комментарий").grid(row=2, column=0, sticky="nw",
                                                 padx=(0, 8))
        cmt_wrap = ttk.Frame(left)
        cmt_wrap.grid(row=2, column=1, sticky="nsew")
        cmt_wrap.columnconfigure(0, weight=1)
        cmt_wrap.rowconfigure(0, weight=1)
        self.txt_comment = tk.Text(cmt_wrap, height=4, wrap="word",
                                   font=("TkDefaultFont", 9), undo=True)
        self.txt_comment.grid(row=0, column=0, sticky="nsew")
        csb = ttk.Scrollbar(cmt_wrap, orient="vertical", command=self.txt_comment.yview)
        self.txt_comment.configure(yscrollcommand=csb.set)
        csb.grid(row=0, column=1, sticky="ns")

        # ---------- Правая колонка: остальные поля ----------
        right = ttk.Frame(form)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(1, weight=1)

        self.var_role     = tk.StringVar()
        self.var_subrole  = tk.StringVar()
        self.var_deadline = tk.StringVar()
        self.var_status   = tk.StringVar()
        self.var_macro    = tk.StringVar(value="")
        self.var_priority = tk.StringVar()

        r = 0
        ttk.Label(right, text="Роль").grid(row=r, column=0, sticky="w",
                                           padx=(0, 8), pady=2)
        self.cmb_role = ttk.Combobox(right, textvariable=self.var_role,
                                     values=[], state="readonly")
        self.cmb_role.grid(row=r, column=1, sticky="ew", pady=2)
        self.cmb_role.bind("<<ComboboxSelected>>", self._on_role_selected)

        r += 1
        ttk.Label(right, text="Подроль").grid(row=r, column=0, sticky="w",
                                              padx=(0, 8), pady=2)
        self.cmb_subrole = ttk.Combobox(right, textvariable=self.var_subrole,
                                        values=[], state="disabled")
        self.cmb_subrole.grid(row=r, column=1, sticky="ew", pady=2)

        r += 1
        ttk.Label(right, text="Дедлайн").grid(row=r, column=0, sticky="w",
                                              padx=(0, 8), pady=2)
        f_dl = ttk.Frame(right)
        f_dl.grid(row=r, column=1, sticky="w", pady=2)
        ttk.Entry(f_dl, textvariable=self.var_deadline, width=12).pack(side="left")
        ttk.Button(f_dl, text="📅", width=3,
                   command=lambda: self._open_cal(self.var_deadline)).pack(side="left", padx=(4, 0))
        ttk.Button(f_dl, text="✕", width=3,
                   command=lambda: self.var_deadline.set("")).pack(side="left", padx=(4, 0))

        r += 1
        ttk.Label(right, text="Статус").grid(row=r, column=0, sticky="w",
                                             padx=(0, 8), pady=2)
        ttk.Combobox(right, textvariable=self.var_status,
                     values=[s["name"] for s in self._statuses],
                     state="readonly")\
            .grid(row=r, column=1, sticky="ew", pady=2)

        r += 1
        ttk.Label(right, text="Macro").grid(row=r, column=0, sticky="w",
                                            padx=(0, 8), pady=2)
        self.cmb_macro = ttk.Combobox(right, textvariable=self.var_macro,
                                      values=[""], state="readonly")
        self.cmb_macro.grid(row=r, column=1, sticky="ew", pady=2)

        r += 1
        ttk.Label(right, text="P").grid(row=r, column=0, sticky="w",
                                        padx=(0, 8), pady=2)
        ttk.Entry(right, textvariable=self.var_priority, width=8)\
            .grid(row=r, column=1, sticky="w", pady=2)

    def save_ui_state(self):
        if self._save_ui_state_impl:
            self._save_ui_state_impl()
        if hasattr(self, "table") and hasattr(self.table, "save_ui_state"):
            self.table.save_ui_state()

    def _on_role_selected(self, _event=None):
        role_display = self.var_role.get().strip()
        role_id = self._roles_by_display.get(role_display)
        if role_id is None:
            self._subrole_display_to_id = {}
            self.cmb_subrole.configure(values=[], state="disabled")
            self.var_subrole.set("")
            return
        subs = db.list_subroles_by_role(role_id)
        self._subrole_display_to_id = {s["name"]: s["id"] for s in subs}
        self.cmb_subrole.configure(values=[""] + list(self._subrole_display_to_id.keys()),
                                   state="readonly")
        self.var_subrole.set("")

    def _refresh_role_combo(self):
        roles = db.list_roles()
        self._roles_by_display = {_role_display(r["id"], r["name"]): r["id"] for r in roles}
        self._role_display_by_id = {r["id"]: _role_display(r["id"], r["name"]) for r in roles}
        self.cmb_role.configure(values=list(self._roles_by_display.keys()))

    def _refresh_macro_combo(self):
        brief = db.list_macro_sprints_brief()
        self._macros_by_code = {m["code"]: m["id"] for m in brief}
        self.cmb_macro.configure(values=[""] + list(self._macros_by_code.keys()))

    def _form_state(self) -> dict:
        return {
            "name":     self.var_name.get().strip(),
            "goal":     self._get_goal(),
            "role":     self.var_role.get().strip(),
            "subrole":  self.var_subrole.get().strip(),
            "deadline": self.var_deadline.get().strip(),
            "status":   self.var_status.get(),
            "macro":    self.var_macro.get().strip(),
            "comment":  self._get_comment(),
            "priority": self.var_priority.get().strip(),
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

    def refresh(self):
        self._refresh_role_combo()
        self._refresh_macro_combo()

        if self.var_role.get().strip():
            role_id = self._roles_by_display.get(self.var_role.get().strip())
            if role_id is not None:
                subs = db.list_subroles_by_role(role_id)
                self._subrole_display_to_id = {s["name"]: s["id"] for s in subs}
                self.cmb_subrole.configure(values=[""] + list(self._subrole_display_to_id.keys()),
                                           state="readonly")

        raw = db.list_epics()
        self._raw_by_id = {r["id"]: r for r in raw}
        display = [{
            "id":           r["id"],
            "name":         r["name"],
            "goal":         r["goal"] or "",
            "role_name":    _role_display(r["role_id"], r["role_name"]) if r["role_id"] else "",
            "subrole_name": r["subrole_name"] or "",
            "deadline":     _to_ru(r["deadline"]) if r["deadline"] else "",
            "status_name":  r["status_name"],
            "macro_code":   r["macro_code"] or "",
            "comment":      r["comment"] or "",
            "priority":     "" if r["priority"] is None else r["priority"],
        } for r in raw]
        self.table.set_rows(display, iid_key="id")
        if self.current_id is not None:
            self.table.select_iid(str(self.current_id))

    def _load_into_form(self, eid: int):
        self.current_id = eid
        src = self._raw_by_id.get(eid)
        if not src:
            return
        self.var_name.set(src["name"])
        self._set_goal(src["goal"] or "")
        self._set_comment(src["comment"] or "")

        if src["role_id"] is not None and src["role_name"]:
            self.var_role.set(_role_display(src["role_id"], src["role_name"]))
        else:
            self.var_role.set("")
        self._on_role_selected()

        self.var_subrole.set(src["subrole_name"] or "")

        self.var_deadline.set(_to_ru(src["deadline"]) if src["deadline"] else "")
        self.var_status.set(src["status_name"])
        self.var_macro.set(src["macro_code"] or "")
        self.var_priority.set("" if src["priority"] is None else str(src["priority"]))
        self._set_snapshot()
        self.table.select_iid(str(eid))

    def _set_goal(self, text):
        self.txt_goal.delete("1.0", "end")
        self.txt_goal.insert("1.0", text or "")

    def _get_goal(self):
        return self.txt_goal.get("1.0", "end-1c").strip()

    def _set_comment(self, text):
        self.txt_comment.delete("1.0", "end")
        self.txt_comment.insert("1.0", text or "")

    def _get_comment(self):
        return self.txt_comment.get("1.0", "end-1c").strip()

    def _clear_form(self):
        self.current_id = None
        self.var_name.set("")
        self._set_goal("")
        self.var_role.set("")
        self._on_role_selected()
        self.var_deadline.set("")
        self.var_status.set(self._statuses[0]["name"] if self._statuses else "")
        self.var_macro.set("")
        self.var_priority.set("")
        self._set_comment("")
        self.table.clear_selection()
        self._set_snapshot()

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
        if not name:
            messagebox.showwarning("Валидация", "Epic Name не может быть пустым.",
                                   parent=self.winfo_toplevel())
            return False

        role_display = self.var_role.get().strip()
        role_id = None
        if role_display:
            role_id = self._roles_by_display.get(role_display)
            if role_id is None:
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

        dl_text = self.var_deadline.get().strip()
        if dl_text:
            try:
                deadline = _to_iso(dl_text)
            except ValueError:
                messagebox.showwarning("Валидация",
                                       "Дедлайн должен быть в формате ДД.ММ.ГГГГ.",
                                       parent=self.winfo_toplevel())
                return False
        else:
            deadline = None

        status_id = self._status_by_name.get(self.var_status.get())
        if status_id is None:
            messagebox.showwarning("Валидация", "Выберите статус.",
                                   parent=self.winfo_toplevel())
            return False

        macro_code = self.var_macro.get().strip()
        macro_id = None
        if macro_code:
            macro_id = self._macros_by_code.get(macro_code)
            if macro_id is None:
                messagebox.showwarning("Валидация",
                                       f"Макро-спринт '{macro_code}' не найден.",
                                       parent=self.winfo_toplevel())
                return False

        pr_text = self.var_priority.get().strip()
        if pr_text == "":
            priority = None
        else:
            try:
                priority = int(pr_text)
            except ValueError:
                messagebox.showwarning("Валидация", "P должно быть целым числом.",
                                       parent=self.winfo_toplevel())
                return False

        goal = self._get_goal() or None
        comment = self._get_comment() or None

        try:
            if self.current_id is None:
                new_id = db.insert_epic(name, goal, role_id, subrole_id, deadline,
                                        status_id, macro_id, comment, priority)
                self.current_id = new_id
            else:
                db.update_epic(self.current_id, name, goal, role_id, subrole_id,
                               deadline, status_id, macro_id, comment, priority)
        except sqlite3.IntegrityError as e:
            msg = str(e)
            if "epics.name" in msg or "UNIQUE" in msg.upper():
                messagebox.showwarning("Валидация",
                                       f"Epic Name «{name}» уже используется.",
                                       parent=self.winfo_toplevel())
            else:
                messagebox.showwarning("Валидация", msg,
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
        name = self.var_name.get().strip()

        n_tasks   = db.count_tasks_using_epic(self.current_id)
        n_actions = db.count_actions_using_epic(self.current_id)
        if n_tasks > 0 or n_actions > 0:
            messagebox.showwarning(
                "Удаление запрещено",
                f"Эпик «{name}» используется:\n"
                f"  задач    — {n_tasks}\n"
                f"  действий — {n_actions}\n\n"
                "Сначала отвяжите или удалите зависимые записи.",
                parent=self.winfo_toplevel(),
            )
            return

        if not messagebox.askyesno("Удаление", f"Удалить эпик «{name}»?",
                                   parent=self.winfo_toplevel()):
            return
        db.delete_epic(self.current_id)
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