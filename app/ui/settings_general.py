"""Вкладка «Общие»: настройки приложения."""
import tkinter as tk
from tkinter import ttk, messagebox

from db import db, db_init


class GeneralSettingsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=8)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        grp_prio = ttk.LabelFrame(self, text="Приоритизация задач", padding=8)
        grp_prio.pack(fill="x", anchor="nw", pady=(0, 8))

        self.var_pomodoro = tk.StringVar()
        ttk.Label(grp_prio, text="Базовая трудоёмкость в Pomodoro (в день):")\
            .grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(grp_prio, textvariable=self.var_pomodoro, width=10)\
            .grid(row=0, column=1, sticky="w", pady=2)

        ttk.Button(grp_prio, text="Сохранить", command=self._save_pomodoro)\
            .grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

    def refresh(self):
        val = db.get_setting(db_init._POMODORO_KEY, db_init._POMODORO_DEFAULT)
        self.var_pomodoro.set(val if val else db_init._POMODORO_DEFAULT)

    def _save_pomodoro(self):
        text = self.var_pomodoro.get().strip().replace(",", ".")
        try:
            v = float(text)
        except ValueError:
            messagebox.showwarning("Валидация", "Должно быть числом.",
                                   parent=self.winfo_toplevel())
            return
        if v <= 0:
            messagebox.showwarning("Валидация", "Должно быть положительным.",
                                   parent=self.winfo_toplevel())
            return
        db.set_setting(db_init._POMODORO_KEY, str(v))
        messagebox.showinfo("Сохранено",
                            "Настройка обновлена. Применится при следующем "
                            "пересчёте PF.",
                            parent=self.winfo_toplevel())

    # ---------- совместимость с внешним API ----------
    def has_unsaved(self) -> bool:
        return False

    def confirm_leave(self) -> bool:
        return True