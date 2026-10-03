"""Вкладка «Общие»: настройки приложения."""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from db import db, db_init
from db import export as db_export
from db import importer as db_importer


class GeneralSettingsTab(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=8)
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        # ---------- Приоритизация задач ----------
        grp_prio = ttk.LabelFrame(self, text="Приоритизация задач", padding=8)
        grp_prio.pack(fill="x", anchor="nw", pady=(0, 8))

        self.var_pomodoro = tk.StringVar()
        ttk.Label(grp_prio, text="Базовая трудоёмкость в Pomodoro (в день):")\
            .grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(grp_prio, textvariable=self.var_pomodoro, width=10)\
            .grid(row=0, column=1, sticky="w", pady=2)

        ttk.Button(grp_prio, text="Сохранить", command=self._save_pomodoro)\
            .grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        # ---------- Экспорт / Импорт данных ----------
        grp_data = ttk.LabelFrame(self, text="Экспорт / Импорт данных", padding=8)
        grp_data.pack(fill="x", anchor="nw")

        ttk.Label(grp_data,
                  text="Экспорт — выгрузить все данные в JSON-файл.\n"
                       "Импорт — заменить все данные из JSON-файла.\n"
                       "Перед импортом автоматически создаётся бэкап текущей БД.")\
            .pack(anchor="w", pady=(0, 8))

        btns = ttk.Frame(grp_data)
        btns.pack(anchor="w")
        ttk.Button(btns, text="Экспорт в JSON…",
                   command=self._on_export_clicked).pack(side="left")
        ttk.Button(btns, text="Импорт из JSON…",
                   command=self._on_import_clicked).pack(side="left", padx=(8, 0))

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

    # ---------- экспорт ----------
    def _on_export_clicked(self):
        parent = self.winfo_toplevel()
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
    def _on_import_clicked(self):
        parent = self.winfo_toplevel()
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

        # 2. Готовим предупреждения
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

        # 4. Итоговое подтверждение
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

        # 5. Сам импорт
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

        # 6. Успех — показать счётчики
        counts = result["counts"]
        counts_text = "\n".join(f"  {t}: {n}" for t, n in counts.items())
        messagebox.showinfo(
            "Импорт завершён",
            f"Данные успешно импортированы.\n\n"
            f"Бэкап текущей БД:\n  {result['backup_path']}\n\n"
            f"Вставлено строк:\n{counts_text}",
            parent=parent,
        )

    # ---------- совместимость с внешним API ----------
    def has_unsaved(self) -> bool:
        return False

    def confirm_leave(self) -> bool:
        return True