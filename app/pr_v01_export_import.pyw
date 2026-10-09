"""pr_v01_export_import — экспорт и импорт всей базы в/из JSON.
Работает только при закрытом pr_v01 и pr_v01_stat."""
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from db import db_lock
from db import export as db_export
from db import importer as db_importer


def _show_error_and_exit(title: str, message: str) -> None:
    root = tk.Tk(); root.withdraw()
    messagebox.showerror(title, message)
    root.destroy()


class ExportImportWindow:
    def __init__(self, root: tk.Tk):
        self.root = root
        root.title("pr_v01 — экспорт / импорт данных")
        root.geometry("560x280")
        root.minsize(520, 260)
        self._build_ui()

    def _build_ui(self):
        grp = ttk.LabelFrame(self.root, text="Экспорт / Импорт данных", padding=12)
        grp.pack(fill="both", expand=True, padx=12, pady=12)

        ttk.Label(
            grp,
            text="Экспорт — выгрузить все данные в JSON-файл.\n"
                 "Импорт — заменить все данные из JSON-файла.\n"
                 "Перед импортом автоматически создаётся бэкап текущей БД.",
            justify="left",
        ).pack(anchor="w", pady=(0, 12))

        btns = ttk.Frame(grp)
        btns.pack(anchor="w")
        ttk.Button(btns, text="Экспорт в JSON…",
                   command=self._on_export).pack(side="left")
        ttk.Button(btns, text="Импорт из JSON…",
                   command=self._on_import).pack(side="left", padx=(8, 0))

    # ---------- экспорт ----------
    def _on_export(self):
        parent = self.root
        path = filedialog.asksaveasfilename(
            parent=parent,
            title="Экспорт данных в JSON",
            initialdir=str(db_export.default_dir()),
            initialfile=db_export.default_filename(),
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("Все файлы", "*.*")],
        )
        if not path:
            return
        try:
            saved = db_export.export_to_json(path)
        except OSError as e:
            messagebox.showerror("Ошибка экспорта",
                                 f"Не удалось записать файл:\n{e}",
                                 parent=parent)
            return
        except Exception as e:
            messagebox.showerror("Ошибка экспорта",
                                 f"Непредвиденная ошибка:\n{e}",
                                 parent=parent)
            return
        messagebox.showinfo("Экспорт завершён",
                            f"Файл сохранён:\n{saved}",
                            parent=parent)

    # ---------- импорт ----------
    def _on_import(self):
        parent = self.root
        path = filedialog.askopenfilename(
            parent=parent,
            title="Импорт данных из JSON",
            initialdir=str(db_export.default_dir()),
            filetypes=[("JSON", "*.json"), ("Все файлы", "*.*")],
        )
        if not path:
            return

        # 1. Читаем и валидируем файл
        try:
            data = db_importer._load_payload(path)
            meta = data["meta"]
            tables = data["tables"]
            db_importer._validate_structure(tables)
            db_importer._validate_fk(tables)
        except db_importer.ImportValidationError as e:
            messagebox.showerror("Импорт отклонён", str(e), parent=parent)
            return

        # 2. Предупреждения
        warnings = []
        file_version = meta.get("schema_version")
        file_app = meta.get("app_name")
        if file_version != db_importer.EXPORT_SCHEMA_VERSION:
            warnings.append(
                f"• Версия схемы в файле: {file_version!r}, "
                f"текущая: {db_importer.EXPORT_SCHEMA_VERSION}.\n"
                f"  Импорт будет выполнен в гибком режиме."
            )
        if file_app is not None and file_app != db_importer.APP_NAME:
            warnings.append(
                f"• Файл помечен приложением {file_app!r} "
                f"(ожидается {db_importer.APP_NAME!r})."
            )

        # 3. Сводка из meta.table_counts
        counts_preview = meta.get("table_counts") or {}
        counts_text = "\n".join(
            f"    {t}: {n}" for t, n in counts_preview.items()
        ) if counts_preview else "    (нет данных)"

        # 4. Подтверждение
        message = (
            "ВСЕ текущие данные в базе будут УДАЛЕНЫ и заменены данными из файла.\n\n"
            f"Файл: {path}\n"
            f"Сделан: {meta.get('exported_at', '—')}\n"
            f"Схема: {file_version!r}\n\n"
            f"Будет вставлено (по данным файла):\n{counts_text}\n\n"
            f"Перед импортом автоматически создаётся бэкап текущей БД.\n"
        )
        if warnings:
            message += "\nПредупреждения:\n" + "\n".join(warnings) + "\n"
        message += "\nПродолжить?"

        if not messagebox.askyesno("Подтверждение импорта", message,
                                   parent=parent, icon="warning"):
            return

        # 5. Импорт
        try:
            result = db_importer.import_from_json(path)
        except db_importer.ImportPreflightError as e:
            messagebox.showerror("Импорт невозможен",
                                 f"{e}\n\nИмпорт не выполнен, данные не изменены.",
                                 parent=parent)
            return
        except db_importer.ImportValidationError as e:
            messagebox.showerror("Импорт отклонён",
                                 f"{e}\n\nТранзакция откачена.",
                                 parent=parent)
            return
        except Exception as e:
            messagebox.showerror("Ошибка импорта",
                                 f"{e}\n\nТранзакция откачена.",
                                 parent=parent)
            return

        # 6. Успех
        counts = result["counts"]
        counts_text = "\n".join(f"  {t}: {n}" for t, n in counts.items())
        messagebox.showinfo(
            "Импорт завершён",
            f"Данные успешно импортированы.\n\n"
            f"Бэкап текущей БД:\n  {result['backup_path']}\n\n"
            f"Вставлено строк:\n{counts_text}",
            parent=parent,
        )


def _run() -> None:
    export_lock = db_lock.Lock(db_lock.EXPORT_LOCK_PATH)
    if not export_lock.acquire():
        _show_error_and_exit(
            "pr_v01_export_import уже запущено",
            "Приложение pr_v01_export_import уже работает.\n"
            "Закройте его и попробуйте снова.",
        )
        return

    try:
        if not db_lock.is_free(db_lock.MAIN_LOCK_PATH):
            _show_error_and_exit(
                "Работает pr_v01",
                "Приложение pr_v01 запущено.\n"
                "Закройте его и попробуйте снова.",
            )
            return
        if not db_lock.is_free(db_lock.STAT_LOCK_PATH):
            _show_error_and_exit(
                "Работает pr_v01_stat",
                "Приложение pr_v01_stat запущено.\n"
                "Закройте его и попробуйте снова.",
            )
            return

        root = tk.Tk()
        ExportImportWindow(root)
        root.mainloop()
    finally:
        export_lock.release()


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