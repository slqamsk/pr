"""pr_v01 — точка входа. Запускать через pythonw.exe (двойной клик)."""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tkinter as tk
from tkinter import ttk, messagebox

from db import db_init
from ui.macro_sprints import MacroSprintsTab
from ui.sprints import SprintsTab
from ui.epics import EpicsTab
from ui.tasks import TasksTab
from ui.actions import ActionsTab
from ui.settings import SettingsTab


def _run() -> None:
    if not db_init.db_exists():
        root = tk.Tk(); root.withdraw()
        answer = messagebox.askyesno(
            "База данных не найдена",
            f"Файл {db_init.DB_PATH.name} не найден в папке data/.\n\n"
            "Создать новую пустую базу данных?",
        )
        root.destroy()
        if not answer:
            return
        db_init.create_empty_db()

    db_init.ensure_db()

    root = tk.Tk()
    root.title("pr_v01")

    # Размер окна рассчитываем от размера экрана,
    # чтобы форма гарантированно поместилась.
    scr_w = root.winfo_screenwidth()
    scr_h = root.winfo_screenheight()

    want_w = 1400
    want_h = 900

    width  = max(1000, min(want_w, scr_w - 40))
    height = max(650,  min(want_h, scr_h - 80))

    root.geometry(f"{width}x{height}")
    root.minsize(1000, 650)

    nb = ttk.Notebook(root)
    nb.pack(fill="both", expand=True)

    # Actions нужен раньше Tasks, потому что Tasks получает callback,
    # который переключает на вкладку Actions и вызывает её метод.
    tab_macro    = MacroSprintsTab(nb)
    tab_sprint   = SprintsTab(nb)
    tab_epics    = EpicsTab(nb)
    tab_actions  = ActionsTab(nb)
    tab_settings = SettingsTab(nb)

    def make_action_from_task(task):
        nb.select(tab_actions)
        if nb.nametowidget(nb.select()) is not tab_actions:
            return
        tab_actions.new_from_task(task)

    tab_tasks = TasksTab(nb, on_make_action=make_action_from_task)

    nb.add(tab_macro,    text="Макро-спринты")
    nb.add(tab_sprint,   text="Спринты")
    nb.add(tab_epics,    text="Эпики")
    nb.add(tab_tasks,    text="Задачи")
    nb.add(tab_actions,  text="Действия")
    nb.add(tab_settings, text="Настройки")

    all_tabs = (tab_macro, tab_sprint, tab_epics, tab_tasks, tab_actions, tab_settings)
    state = {"current": tab_macro}

    def on_tab_changed(_e=None):
        new = nb.nametowidget(nb.select())
        if new is state["current"]:
            return
        if not state["current"].confirm_leave():
            nb.select(state["current"])
            return
        state["current"] = new
        if hasattr(new, "refresh"):
            new.refresh()

    nb.bind("<<NotebookTabChanged>>", on_tab_changed)

    def on_close():
        for tab in all_tabs:
            if not tab.confirm_leave():
                return
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    root.mainloop()


def main() -> None:
    try:
        _run()
    except Exception as e:
        root = tk.Tk(); root.withdraw()
        messagebox.showerror("Ошибка запуска",
                             f"{e}\n\n{traceback.format_exc()}")
        root.destroy()
        raise


if __name__ == "__main__":
    main()