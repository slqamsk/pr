"""Вкладка «Настройки» — контейнер с вложенными вкладками."""
from tkinter import ttk

from ui.roles import RolesTab
from ui.subroles import SubrolesTab
from ui.settings_general import GeneralSettingsTab


class SettingsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=8)
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True)

        self.tab_general  = GeneralSettingsTab(self.nb)
        self.tab_roles    = RolesTab(self.nb)
        self.tab_subroles = SubrolesTab(self.nb)

        self.nb.add(self.tab_general,  text="Общие")
        self.nb.add(self.tab_roles,    text="Роль")
        self.nb.add(self.tab_subroles, text="Подроль")

        self._inner_current = self.tab_general
        self.nb.bind("<<NotebookTabChanged>>", self._on_inner_tab_changed)

    def _on_inner_tab_changed(self, _e=None):
        new = self.nb.nametowidget(self.nb.select())
        if new is self._inner_current:
            return
        if not self._inner_current.confirm_leave():
            self.nb.select(self._inner_current)
            return
        self._inner_current = new
        if hasattr(new, "refresh"):
            new.refresh()

    def refresh(self):
        self.tab_general.refresh()
        self.tab_roles.refresh()
        self.tab_subroles.refresh()

    def has_unsaved(self) -> bool:
        return (self.tab_general.has_unsaved()
                or self.tab_roles.has_unsaved()
                or self.tab_subroles.has_unsaved())

    def confirm_leave(self) -> bool:
        for tab in (self.tab_general, self.tab_roles, self.tab_subroles):
            if not tab.confirm_leave():
                return False
        return True