"""pr_v01 — точка входа. Запускать через pythonw.exe (двойной клик)."""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tkinter as tk
from tkinter import ttk, messagebox

from db import db, db_init, db_lock
from ui.macro_sprints import MacroSprintsTab
from ui.sprints import SprintsTab
from ui.epics import EpicsTab
from ui.tasks import TasksTab
from ui.actions import ActionsTab
from ui.settings import SettingsTab

_GEOMETRY_KEY = "ui.main_window.geometry"


def _load_geometry(root) -> str | None:
    """Возвращает сохранённую геометрию, если она влезает в текущий экран."""
    raw = db.get_setting(_GEOMETRY_KEY)
    if not raw:
        return None
    try:
        import re
        m = re.match(r"^(\d+)x(\d+)([+-]\d+)([+-]\d+)$", raw.strip())
        if not m:
            return None
        w, h, x, y = (int(m.group(1)), int(m.group(2)),
                      int(m.group(3)), int(m.group(4)))
        scr_w = root.winfo_screenwidth()
        scr_h = root.winfo_screenheight()
        if x < 0 or y < 0 or x > scr_w - 200 or y > scr_h - 100:
            return f"{w}x{h}"
        if w > scr_w - 40 or h > scr_h - 80:
            return None
        return raw.strip()
    except Exception:
        return None


def _save_geometry(root) -> None:
    try:
        db.set_setting(_GEOMETRY_KEY, root.geometry())
    except Exception:
        pass


def _show_error_and_exit(title: str, message: str) -> None:
    root = tk.Tk(); root.withdraw()
    messagebox.showerror(title, message)
    root.destroy()


def _run() -> None:
    main_lock = db_lock.Lock(db_lock.MAIN_LOCK_PATH)
    if not main_lock.acquire():
        _show_error_and_exit(
            "pr_v01 уже запущено",
            "Приложение pr_v01 уже работает.\n"
            "Закройте его и попробуйте снова.",
        )
        return

    try:
        if not db_lock.is_free(db_lock.EXPORT_LOCK_PATH):
            _show_error_and_exit(
                "Работает pr_v01_export_import",
                "Приложение pr_v01_export_import запущено.\n"
                "Закройте его и попробуйте снова.",
            )
            return

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
        root.minsize(1000, 650)

        saved = _load_geometry(root)
        if saved:
            root.geometry(saved)
        else:
            scr_w = root.winfo_screenwidth()
            scr_h = root.winfo_screenheight()
            width  = max(1000, min(1400, scr_w - 40))
            height = max(650,  min(900,  scr_h - 80))
            root.geometry(f"{width}x{height}")

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True)

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
            for tab in all_tabs:
                if hasattr(tab, "save_ui_state"):
                    tab.save_ui_state()
            _save_geometry(root)
            root.destroy()

        root.protocol("WM_DELETE_WINDOW", on_close)
        root.mainloop()
    finally:
        main_lock.release()


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