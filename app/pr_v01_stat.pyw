"""pr_v01_stat — статистика по Actions."""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tkinter as tk
from tkinter import messagebox

from db import db_lock
from ui_stat.day_view import DayView


def _show_error_and_exit(title: str, message: str) -> None:
    root = tk.Tk(); root.withdraw()
    messagebox.showerror(title, message)
    root.destroy()


def _run() -> None:
    stat_lock = db_lock.Lock(db_lock.STAT_LOCK_PATH)
    if not stat_lock.acquire():
        _show_error_and_exit(
            "pr_v01_stat уже запущено",
            "Приложение pr_v01_stat уже работает.\n"
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

        root = tk.Tk()
        root.title("pr_v01_stat")
        root.geometry("1400x900")
        root.minsize(800, 500)

        DayView(root).pack(fill="both", expand=True)

        root.mainloop()
    finally:
        stat_lock.release()


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