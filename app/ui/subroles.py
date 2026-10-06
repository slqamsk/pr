"""Вкладка работы с подролями (суррогатный ключ, обязательная ссылка на роль)."""
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3

from db import db
from ui.widgets import ScrollableTable, ask_unsaved_changes, setup_vertical_paned

COLUMNS = [
    {"key": "role_display", "title": "Роль",     "width": 280, "wrap": True},
    {"key": "name",         "title": "Название", "width": 400, "wrap": True},
]


class SubrolesTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=8)
        self.current_id: int | None = None
        self._raw_by_id: dict[int, dict] = {}
        self._snapshot: dict | None = None
        self._roles_by_display: dict[str, int] = {}
        self._save_ui_state_impl = None
        self._build_ui()
        self.refresh()
        self._set_snapshot()

    @staticmethod
    def _display(rid: int, rname: str) -> str:
        return f"{rid}. {rname}"

    def _build_ui(self):
        btns = ttk.Frame(self, padding=(0, 8, 0, 0))
        ttk.Button(btns, text="Новая",     command=self._new).pack(side="left")
        ttk.Button(btns, text="Сохранить", command=self._on_save_clicked).pack(side="left", padx=6)
        ttk.Button(btns, text="Удалить",   command=self._delete).pack(side="left")
        ttk.Button(btns, text="Обновить",  command=self._on_refresh_clicked).pack(side="right")
        btns.pack(side="bottom", fill="x")

        self._paned, self._save_ui_state_impl = setup_vertical_paned(
            self, "ui.sash.subroles"
        )
        self.table = ScrollableTable(self._paned, COLUMNS,
                                     on_select=self._on_table_select,
                                     settings_key="ui.columns.subroles")
        self._paned.add(self.table, weight=2)
        self._bottom = ttk.Frame(self._paned)
        self._paned.add(self._bottom, weight=1)

        form = ttk.LabelFrame(self._bottom, text="Запись", padding=8)
        form.pack(fill="both", expand=True, pady=(8, 0))
        form.columnconfigure(1, weight=1)

        self.var_role = tk.StringVar()
        self.var_name = tk.StringVar()

        ttk.Label(form, text="Роль").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        self.cmb_role = ttk.Combobox(form, textvariable=self.var_role,
                                     values=[], state="readonly", width=32)
        self.cmb_role.grid(row=0, column=1, sticky="w", pady=2)

        ttk.Label(form, text="Название").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(form, textvariable=self.var_name)\
            .grid(row=1, column=1, sticky="ew", pady=2)

    def save_ui_state(self):
        if self._save_ui_state_impl:
            self._save_ui_state_impl()
        if hasattr(self, "table") and hasattr(self.table, "save_ui_state"):
            self.table.save_ui_state()

    def _form_state(self) -> dict:
        return {
            "role": self.var_role.get().strip(),
            "name": self.var_name.get().strip(),
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
        roles = db.list_roles()
        self._roles_by_display = {
            self._display(r["id"], r["name"]): r["id"] for r in roles
        }
        self.cmb_role.configure(values=list(self._roles_by_display.keys()))

        raw = db.list_subroles()
        self._raw_by_id = {r["id"]: r for r in raw}
        display = [{
            "id":           r["id"],
            "role_display": self._display(r["role_id"], r["role_name"]),
            "name":         r["name"],
        } for r in raw]
        self.table.set_rows(display, iid_key="id")
        if self.current_id is not None:
            self.table.select_iid(str(self.current_id))

    def _load_into_form(self, sid: int):
        self.current_id = sid
        src = self._raw_by_id.get(sid)
        if not src:
            return
        self.var_role.set(self._display(src["role_id"], src["role_name"]))
        self.var_name.set(src["name"])
        self._set_snapshot()
        self.table.select_iid(str(sid))

    def _clear_form(self):
        self.current_id = None
        self.var_role.set("")
        self.var_name.set("")
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
            messagebox.showwarning("Валидация", "Название не может быть пустым.",
                                   parent=self.winfo_toplevel())
            return False

        role_display = self.var_role.get().strip()
        role_id = self._roles_by_display.get(role_display)
        if role_id is None:
            messagebox.showwarning("Валидация",
                                   "Выберите роль (поле обязательно).",
                                   parent=self.winfo_toplevel())
            return False

        try:
            if self.current_id is None:
                new_id = db.insert_subrole(role_id, name)
                self.current_id = new_id
            else:
                db.update_subrole(self.current_id, role_id, name)
        except sqlite3.IntegrityError as e:
            msg = str(e)
            if "UNIQUE" in msg.upper():
                messagebox.showwarning(
                    "Валидация",
                    f"У этой роли уже есть подроль «{name}».",
                    parent=self.winfo_toplevel(),
                )
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

        n_epics   = db.count_epics_using_subrole(self.current_id)
        n_tasks   = db.count_tasks_using_subrole(self.current_id)
        n_actions = db.count_actions_using_subrole(self.current_id)
        if n_epics > 0 or n_tasks > 0 or n_actions > 0:
            messagebox.showwarning(
                "Удаление запрещено",
                f"Подроль «{name}» используется:\n"
                f"  эпиков   — {n_epics}\n"
                f"  задач    — {n_tasks}\n"
                f"  действий — {n_actions}\n\n"
                "Сначала отвяжите или удалите зависимые записи.",
                parent=self.winfo_toplevel(),
            )
            return

        if not messagebox.askyesno("Удаление", f"Удалить подроль «{name}»?",
                                   parent=self.winfo_toplevel()):
            return
        db.delete_subrole(self.current_id)
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