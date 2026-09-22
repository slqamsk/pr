#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
backup_tool.pyw — ручное резервное архивирование текстовых файлов
и подготовка scp-команды для выгрузки на сервер.

Конфиг создаётся автоматически при первом запуске.
"""

import os
import re
import json
import shutil
import difflib
import datetime
import tkinter as tk
from tkinter import ttk, messagebox


APP_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_PATH = os.path.join(APP_DIR, "backup_tool_config.json")

DEFAULT_CONFIG = {
    "folder": APP_DIR,
    "archive_subfolder": "archive",
    "archive_old_subfolder": "old",
    "tracked_extensions": [],
    "ignored_extensions": [],
    "tracked_files": [],
    "ignored_files": [],
    "threshold": 10,
    "force_archive_after_days": 7,
    "server_upload_log": {},
    "server": {
        "user": "slqamsk",
        "host": "193.37.70.210",
        "remote_base": "~/Downloads"
    }
}


# ------------------------------------------------------------------- конфиг

def load_config():
    """Если конфига нет — создаёт его с значениями по умолчанию."""
    if not os.path.exists(CONFIG_PATH):
        cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # глубокая копия
        save_config(cfg)
        return cfg
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


# ------------------------------------------------------- работа с текстовыми

def read_text_lines(path):
    """Открывает файл в текстовом режиме. Возвращает список строк или None."""
    for enc in ("utf-8", "cp1251"):
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read().splitlines()
        except UnicodeDecodeError:
            continue
        except OSError:
            return None
    return None


def normalized_lines(path):
    """Непустые строки без хвостовых пробелов и табуляций.
    Строки, состоящие только из пробелов/табуляций, отбрасываются."""
    lines = read_text_lines(path)
    if lines is None:
        return None
    return [ln.rstrip() for ln in lines if ln.strip()]


def count_changed_lines(old_lines, new_lines):
    """Число несовпавших непустых строк. Для каждого блока различий
    берётся max(удалённых, добавленных)."""
    sm = difflib.SequenceMatcher(a=old_lines, b=new_lines, autojunk=False)
    total = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        total += max(i2 - i1, j2 - j1)
    return total


def days_between(date_str, today=None):
    """Целое число дней между date_str (YYYY-MM-DD) и today (по умолчанию — сегодня)."""
    if today is None:
        today = datetime.date.today()
    return (today - datetime.date.fromisoformat(date_str)).days


# ------------------------------------------------------------------- архивы

def archive_dir(cfg):
    return os.path.join(cfg["folder"], cfg["archive_subfolder"])


def archive_old_dir(cfg):
    return os.path.join(archive_dir(cfg), cfg["archive_old_subfolder"])


def find_newest_archive(cfg, name):
    """(полный_путь, 'YYYY-MM-DD') самого свежего архива файла,
    или (None, None). Смотрит только имена в archive/."""
    base, ext = os.path.splitext(name)
    adir = archive_dir(cfg)
    if not os.path.isdir(adir):
        return None, None
    pat = re.compile(
        r"^" + re.escape(base) + r"-(\d{4}-\d{2}-\d{2})" + re.escape(ext) + r"$")
    best, best_date = None, None
    for fn in os.listdir(adir):
        if not os.path.isfile(os.path.join(adir, fn)):
            continue
        m = pat.match(fn)
        if not m:
            continue
        d = m.group(1)
        if best_date is None or d > best_date:
            best_date, best = d, os.path.join(adir, fn)
    return best, best_date


def cleanup_archives(cfg, log):
    """В archive/ оставляем только самый свежий архив каждого tracked-файла,
    остальные архивы целиком переносим в archive/old/."""
    adir = archive_dir(cfg)
    old = archive_old_dir(cfg)
    os.makedirs(old, exist_ok=True)
    moved = 0

    for name in cfg["tracked_files"]:
        base, ext = os.path.splitext(name)
        pat = re.compile(
            r"^" + re.escape(base) + r"-(\d{4}-\d{2}-\d{2})" + re.escape(ext) + r"$")

        items = []
        for fn in os.listdir(adir):
            if not os.path.isfile(os.path.join(adir, fn)):
                continue
            m = pat.match(fn)
            if m:
                items.append((m.group(1), fn))

        if len(items) <= 1:
            continue

        items.sort(key=lambda t: t[0], reverse=True)
        for _d, fn in items[1:]:
            src = os.path.join(adir, fn)
            dst = os.path.join(old, fn)
            if os.path.exists(dst):
                stem, suf = os.path.splitext(fn)
                i = 1
                while os.path.exists(
                        os.path.join(old, "{}__{}{}".format(stem, i, suf))):
                    i += 1
                dst = os.path.join(old, "{}__{}{}".format(stem, i, suf))
            try:
                shutil.move(src, dst)
                log("  -> old/{}".format(os.path.basename(dst)))
                moved += 1
            except Exception as e:
                log("  [ошибка] {}: {}".format(fn, e))
    return moved


# ------------------------------------------------------------------ утилиты

def list_all_extensions(folder):
    exts = set()
    for name in os.listdir(folder):
        p = os.path.join(folder, name)
        if os.path.isfile(p):
            ext = os.path.splitext(name)[1].lower()
            if ext:
                exts.add(ext)
    return exts


# --------------------------------------------------------------- DualList

class DualList(ttk.Frame):
    def __init__(self, parent, left_title, right_title, on_change=None):
        super().__init__(parent)
        self.on_change = on_change
        ttk.Label(self, text=left_title).grid(row=0, column=0, sticky="w", padx=5)
        ttk.Label(self, text=right_title).grid(row=0, column=2, sticky="w", padx=5)

        lf = ttk.Frame(self); lf.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        self.left = tk.Listbox(lf, selectmode="extended", exportselection=False)
        self.left.pack(side="left", fill="both", expand=True)
        lsb = ttk.Scrollbar(lf, orient="vertical", command=self.left.yview)
        lsb.pack(side="right", fill="y"); self.left.configure(yscrollcommand=lsb.set)

        btns = ttk.Frame(self); btns.grid(row=1, column=1, sticky="ns")
        ttk.Button(btns, text="\u2192", width=3, command=self.move_right).pack(pady=4)
        ttk.Button(btns, text="\u2190", width=3, command=self.move_left).pack(pady=4)

        rf = ttk.Frame(self); rf.grid(row=1, column=2, sticky="nsew", padx=5, pady=5)
        self.right = tk.Listbox(rf, selectmode="extended", exportselection=False)
        self.right.pack(side="left", fill="both", expand=True)
        rsb = ttk.Scrollbar(rf, orient="vertical", command=self.right.yview)
        rsb.pack(side="right", fill="y"); self.right.configure(yscrollcommand=rsb.set)

        self.columnconfigure(0, weight=1); self.columnconfigure(2, weight=1)
        self.rowconfigure(1, weight=1)

    def set_items(self, l, r):
        self.left.delete(0, tk.END); self.right.delete(0, tk.END)
        for x in l: self.left.insert(tk.END, x)
        for x in r: self.right.insert(tk.END, x)

    def _move(self, src, dst):
        sel = list(src.curselection())
        items = [src.get(i) for i in sel]
        for i in reversed(sel): src.delete(i)
        for x in items: dst.insert(tk.END, x)
        if self.on_change: self.on_change()

    def move_right(self): self._move(self.left, self.right)
    def move_left(self):  self._move(self.right, self.left)
    def get_left(self):   return list(self.left.get(0, tk.END))
    def get_right(self):  return list(self.right.get(0, tk.END))


# --------------------------------------------------------------- main App

class App:
    def __init__(self, root, cfg):
        self.root = root
        self.cfg = cfg
        self._pending_upload = []

        root.title("Backup Tool")
        root.geometry("980x760")

        nb = ttk.Notebook(root); nb.pack(fill="both", expand=True)
        self.tab_exts = ttk.Frame(nb)
        self.tab_files = ttk.Frame(nb)
        self.tab_settings = ttk.Frame(nb)
        self.tab_archive = ttk.Frame(nb)
        self.tab_upload = ttk.Frame(nb)
        nb.add(self.tab_exts, text="Типы файлов")
        nb.add(self.tab_files, text="Файлы")
        nb.add(self.tab_settings, text="Настройки")
        nb.add(self.tab_archive, text="Архивирование")
        nb.add(self.tab_upload, text="Выгрузка на сервер")

        self._build_exts_tab()
        self._build_files_tab()
        self._build_settings_tab()
        self._build_archive_tab()
        self._build_upload_tab()

        self.refresh_lists()
        self.root.after(150, self.startup_scan)

    # ---- Типы файлов

    def _build_exts_tab(self):
        top = ttk.Frame(self.tab_exts); top.pack(fill="x", padx=5, pady=5)
        ttk.Label(top, text="Расширения: слева — обрабатываемые, справа — игнорируемые."
                 ).pack(side="left")
        ttk.Button(top, text="Сканировать папку",
                   command=self.scan_extensions).pack(side="right")
        self.ext_lists = DualList(self.tab_exts,
            "Обрабатываемые", "Игнорируемые", on_change=self._on_exts_change)
        self.ext_lists.pack(fill="both", expand=True, padx=5, pady=5)

    def _on_exts_change(self):
        self.cfg["tracked_extensions"] = [e.lower() for e in self.ext_lists.get_left()]
        self.cfg["ignored_extensions"] = [e.lower() for e in self.ext_lists.get_right()]
        save_config(self.cfg)

    # ---- Файлы

    def _build_files_tab(self):
        top = ttk.Frame(self.tab_files); top.pack(fill="x", padx=5, pady=5)
        ttk.Label(top, text="Файлы: слева — обрабатываемые, справа — игнорируемые."
                 ).pack(side="left")
        ttk.Button(top, text="Сканировать папку",
                   command=self.scan_files).pack(side="right")
        self.file_lists = DualList(self.tab_files,
            "Обрабатываемые", "Игнорируемые", on_change=self._on_files_change)
        self.file_lists.pack(fill="both", expand=True, padx=5, pady=5)

    def _on_files_change(self):
        self.cfg["tracked_files"] = self.file_lists.get_left()
        self.cfg["ignored_files"] = self.file_lists.get_right()
        save_config(self.cfg)

    # ---- Настройки

    def _build_settings_tab(self):
        f = self.tab_settings; row = 0
        ttk.Label(f, text="Папка с файлами:").grid(
            row=row, column=0, sticky="w", padx=8, pady=6)
        self.folder_var = tk.StringVar(value=self.cfg["folder"])
        ttk.Entry(f, textvariable=self.folder_var, width=70).grid(
            row=row, column=1, columnspan=2, sticky="ew", padx=8); row += 1

        ttk.Label(f, text="Порог изменений (непустых строк):").grid(
            row=row, column=0, sticky="w", padx=8, pady=6)
        self.threshold_var = tk.StringVar(value=str(self.cfg["threshold"]))
        ttk.Entry(f, textvariable=self.threshold_var, width=10).grid(
            row=row, column=1, sticky="w", padx=8); row += 1

        ttk.Label(f, text="Принудительно архивировать после N дней "
                          "с последнего архива:").grid(
            row=row, column=0, sticky="w", padx=8, pady=6)
        self.force_days_var = tk.StringVar(
            value=str(self.cfg.get("force_archive_after_days", 7)))
        ttk.Entry(f, textvariable=self.force_days_var, width=10).grid(
            row=row, column=1, sticky="w", padx=8); row += 1

        ttk.Separator(f, orient="horizontal").grid(
            row=row, column=0, columnspan=3, sticky="ew", pady=12); row += 1

        ttk.Label(f, text="Сервер (только для scp-команды):").grid(
            row=row, column=0, columnspan=3, sticky="w", padx=8); row += 1

        ttk.Label(f, text="user:").grid(row=row, column=0, sticky="w",
                                        padx=8, pady=4)
        self.user_var = tk.StringVar(value=self.cfg["server"]["user"])
        ttk.Entry(f, textvariable=self.user_var, width=40).grid(
            row=row, column=1, sticky="w", padx=8); row += 1

        ttk.Label(f, text="host:").grid(row=row, column=0, sticky="w",
                                        padx=8, pady=4)
        self.host_var = tk.StringVar(value=self.cfg["server"]["host"])
        ttk.Entry(f, textvariable=self.host_var, width=40).grid(
            row=row, column=1, sticky="w", padx=8); row += 1

        ttk.Label(f, text="remote_base:").grid(row=row, column=0, sticky="w",
                                               padx=8, pady=4)
        self.remote_var = tk.StringVar(value=self.cfg["server"]["remote_base"])
        ttk.Entry(f, textvariable=self.remote_var, width=40).grid(
            row=row, column=1, sticky="w", padx=8); row += 1

        ttk.Button(f, text="Сохранить настройки",
                   command=self.save_settings).grid(
            row=row, column=0, columnspan=3, pady=20)
        f.columnconfigure(1, weight=1)

    def save_settings(self):
        try:
            th = int(self.threshold_var.get())
            if th < 0: raise ValueError
        except ValueError:
            messagebox.showerror("Ошибка", "Порог — целое неотрицательное число")
            return
        try:
            fd = int(self.force_days_var.get())
            if fd < 0: raise ValueError
        except ValueError:
            messagebox.showerror("Ошибка",
                "Порог дней — целое неотрицательное число")
            return
        self.cfg["folder"] = self.folder_var.get()
        self.cfg["threshold"] = th
        self.cfg["force_archive_after_days"] = fd
        self.cfg["server"]["user"] = self.user_var.get()
        self.cfg["server"]["host"] = self.host_var.get()
        self.cfg["server"]["remote_base"] = self.remote_var.get()
        save_config(self.cfg)
        messagebox.showinfo("Настройки", "Сохранено")
        self.refresh_lists()

    # ---- Архивирование

    def _build_archive_tab(self):
        f = self.tab_archive
        top = ttk.Frame(f); top.pack(fill="x", padx=8, pady=8)
        ttk.Button(top,
            text="Выполнить добавление в архив изменившихся файлов",
            command=self.do_archive).pack(side="left")
        ttk.Button(top,
            text="Архивировать все изменённые",
            command=lambda: self.do_archive(force_all=True)).pack(
            side="left", padx=8)
        ttk.Label(top,
            text="  («все изменённые» игнорирует пороги, но пропускает файлы "
                 "без изменений и уже заархивированные сегодня"
        ).pack(side="left")

        self.archive_text = tk.Text(f, wrap="none", height=24)
        self.archive_text.pack(fill="both", expand=True, padx=8, pady=8)
        sb = ttk.Scrollbar(self.archive_text, command=self.archive_text.yview)
        sb.pack(side="right", fill="y")
        self.archive_text.configure(yscrollcommand=sb.set)

    def do_archive(self, force_all=False):
        self.archive_text.delete("1.0", tk.END)
        def log(s=""):
            self.archive_text.insert(tk.END, s + "\n")
            self.archive_text.see(tk.END)
            self.root.update_idletasks()

        folder = self.cfg["folder"]
        adir = archive_dir(self.cfg)
        os.makedirs(adir, exist_ok=True)
        yesterday = (datetime.date.today() -
                     datetime.timedelta(days=1)).isoformat()
        threshold = self.cfg["threshold"]
        force_days = self.cfg.get("force_archive_after_days", 7)

        log("=== {} ===".format(
            "Архивировать все изменённые" if force_all else "Архивирование"))
        log("Папка:              {}".format(folder))
        log("Архив:              {}".format(adir))
        if force_all:
            log("Режим:              «все изменённые» (пороги игнорируются)")
        else:
            log("Порог изменений:    {} непустых строк".format(threshold))
            log("Порог дней:         {} (архивировать при любых изменениях, "
                "если прошло ≥ N дней)".format(force_days))
        log("Суффикс даты:       {}".format(yesterday))
        log("")

        archived = []   # (name, changes, target_name, reason)
        already = []    # (name, changes, target_name)
        below = []      # (name, changes, arch_date, days)
        unchanged = []  # (name, arch_date)
        missing = []    # (name,)
        errors = []     # (name, msg)

        for name in list(self.cfg["tracked_files"]):
            path = os.path.join(folder, name)
            if not os.path.isfile(path):
                missing.append(name); continue

            cur_lines = normalized_lines(path)
            if cur_lines is None:
                missing.append(name); continue

            arch_path, arch_date = find_newest_archive(self.cfg, name)

            if arch_path is None:
                changes = None
                days = None
                need = True
                reason = "архива нет (первичный бэкап)"
            else:
                old_lines = normalized_lines(arch_path)
                if old_lines is None:
                    errors.append((name, "архив не читается")); continue
                changes = count_changed_lines(old_lines, cur_lines)
                days = days_between(arch_date)

                if changes == 0:
                    unchanged.append((name, arch_date)); continue

                if force_all:
                    need = True
                    reason = "есть изменения (режим «все изменённые»)"
                elif changes >= threshold:
                    need = True
                    reason = "изменений {} ≥ порога {}".format(changes, threshold)
                elif days >= force_days:
                    need = True
                    reason = ("изменений {} (ниже порога {}), "
                              "но {} дн. с архива ≥ {}".format(
                                  changes, threshold, days, force_days))
                else:
                    need = False

            if not need:
                below.append((name, changes, arch_date, days))
                continue

            base, ext = os.path.splitext(name)
            target_name = "{}-{}{}".format(base, yesterday, ext)
            target = os.path.join(adir, target_name)
            if os.path.exists(target):
                already.append((name, changes, target_name))
                continue
            try:
                shutil.copy2(path, target)
                archived.append((name, changes, target_name, reason))
            except Exception as e:
                errors.append((name, str(e)))

        # ---- Отчёт ----

        log("=== [1] Заархивировано: {} ===".format(len(archived)))
        for name, changes, target_name, reason in archived:
            if changes is None:
                log("  [+] {}   ({})".format(target_name, reason))
            else:
                log("  [+] {}   (изменений {}, {})".format(
                    target_name, changes, reason))
        log()

        log("=== [2] Сильно изменены, но архив с датой {} уже есть — "
            "пропуск: {} ===".format(yesterday, len(already)))
        for name, changes, target_name in already:
            if changes is None:
                log("  [=] {}   (архив {} уже существует)".format(
                    name, target_name))
            else:
                log("  [=] {}   (изменений {}, архив {} уже существует)".format(
                    name, changes, target_name))
        log()

        log("=== [3] Изменения ниже порога — пропуск: {} ===".format(len(below)))
        for name, changes, arch_date, days in below:
            log("  [-] {}   (изменений {}, порог {}, "
                "дней с архива {} / порог дней {})".format(
                    name, changes, threshold,
                    days if days is not None else "—", force_days))
        log()

        log("=== [4] Без значимых изменений: {} ===".format(len(unchanged)))
        for name, arch_date in unchanged:
            log("  [.] {}   (только пустые строки / пробелы, "
                "свежий архив {})".format(name, arch_date))
        log()

        if missing:
            log("=== [5] Файлы отсутствуют или не читаются: {} ===".format(
                len(missing)))
            for name in missing:
                log("  [!] {}".format(name))
            log()

        if errors:
            log("=== [!] Ошибки: {} ===".format(len(errors)))
            for name, msg in errors:
                log("  [!] {}: {}".format(name, msg))
            log()

        log("--- Перенос старых архивов в old ---")
        moved = cleanup_archives(self.cfg, log)
        log("--- Готово. Перемещено в old: {} ---".format(moved))

    # ---- Выгрузка на сервер

    def _build_upload_tab(self):
        f = self.tab_upload
        top = ttk.Frame(f); top.pack(fill="x", padx=8, pady=8)
        ttk.Button(top, text="Сформировать команду выгрузки",
                   command=self.generate_upload).pack(side="left")
        ttk.Button(top, text="Скопировать команду",
                   command=self.copy_upload_cmd).pack(side="left", padx=8)
        ttk.Button(top, text="Отметить выгрузку выполненной",
                   command=self.mark_uploaded).pack(side="left", padx=8)
        ttk.Label(top,
            text="  (scp не вызывается; копируется только команда)"
        ).pack(side="left")

        ttk.Label(f, text="Команда для копирования:").pack(
            anchor="w", padx=8, pady=(6, 2))
        cmd_frame = ttk.Frame(f); cmd_frame.pack(fill="x", padx=8)
        self.upload_cmd_text = tk.Text(cmd_frame, wrap="word", height=6)
        self.upload_cmd_text.pack(side="left", fill="both", expand=True)
        csb = ttk.Scrollbar(cmd_frame, command=self.upload_cmd_text.yview)
        csb.pack(side="right", fill="y")
        self.upload_cmd_text.configure(yscrollcommand=csb.set)

        ttk.Label(f, text="Информация о файлах:").pack(
            anchor="w", padx=8, pady=(10, 2))
        info_frame = ttk.Frame(f); info_frame.pack(
            fill="both", expand=True, padx=8, pady=(0, 8))
        self.upload_info_text = tk.Text(info_frame, wrap="word", height=14)
        self.upload_info_text.pack(side="left", fill="both", expand=True)
        isb = ttk.Scrollbar(info_frame, command=self.upload_info_text.yview)
        isb.pack(side="right", fill="y")
        self.upload_info_text.configure(yscrollcommand=isb.set)

    def generate_upload(self):
        """Смотрим только даты архивов и server_upload_log."""
        self.upload_cmd_text.delete("1.0", tk.END)
        self.upload_info_text.delete("1.0", tk.END)
        folder = self.cfg["folder"]
        log_map = self.cfg.get("server_upload_log") or {}
        today = datetime.date.today().isoformat()

        to_upload = []
        for name in self.cfg["tracked_files"]:
            _arch_path, arch_date = find_newest_archive(self.cfg, name)
            if arch_date is None:
                continue
            last = log_map.get(name)
            if last is None or arch_date > last:
                to_upload.append((name, arch_date))

        if not to_upload:
            self.upload_cmd_text.insert(tk.END, "# Нет файлов для выгрузки.\n")
            self.upload_info_text.insert(tk.END, "# Нет файлов для выгрузки.\n")
            self._pending_upload = []
            return

        server = self.cfg["server"]
        remote_dir = server["remote_base"].rstrip("/") + "/" + today + "/"
        dst = "{}@{}:{}".format(server["user"], server["host"], remote_dir)

        parts = ["scp"]
        for name, _ in to_upload:
            full = os.path.join(folder, name)
            parts.append('"{}"'.format(full) if " " in full else full)
        parts.append(dst)
        cmd = " ".join(parts)

        self.upload_cmd_text.insert(tk.END, cmd + "\n")

        self.upload_info_text.insert(tk.END, "# Файлы для выгрузки:\n")
        for name, arch_date in to_upload:
            last = log_map.get(name, "—")
            self.upload_info_text.insert(tk.END,
                "#   {}   (свежий архив {}, выгружен {})\n".format(
                    name, arch_date, last))

        self._pending_upload = [n for n, _ in to_upload]

    def copy_upload_cmd(self):
        cmd = self.upload_cmd_text.get("1.0", tk.END).strip()
        if not cmd or cmd.startswith("#"):
            messagebox.showinfo("Выгрузка", "Сначала сформируйте команду.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(cmd)
        messagebox.showinfo("Выгрузка", "Команда скопирована в буфер обмена.")

    def mark_uploaded(self):
        if not self._pending_upload:
            messagebox.showinfo("Выгрузка", "Сначала сформируйте команду.")
            return
        today = datetime.date.today().isoformat()
        for name in self._pending_upload:
            self.cfg["server_upload_log"][name] = today
        save_config(self.cfg)
        messagebox.showinfo("Выгрузка",
            "Отмечено как выгруженное ({}): {} файл(ов).".format(
                today, len(self._pending_upload)))
        self._pending_upload = []

    # ---- скан

    def refresh_lists(self):
        self.ext_lists.set_items(
            self.cfg["tracked_extensions"], self.cfg["ignored_extensions"])
        self.file_lists.set_items(
            self.cfg["tracked_files"], self.cfg["ignored_files"])

    def startup_scan(self):
        self.scan_extensions(silent=True)
        self.scan_files(silent=True)

    def scan_extensions(self, silent=False):
        folder = self.cfg["folder"]
        if not os.path.isdir(folder):
            if not silent:
                messagebox.showerror("Скан", "Папка не найдена:\n{}".format(folder))
            return
        found_exts = list_all_extensions(folder)  # только те, что есть в папке

        self.cfg["tracked_extensions"] = [
            e for e in self.cfg["tracked_extensions"] if e in found_exts]
        self.cfg["ignored_extensions"] = [
            e for e in self.cfg["ignored_extensions"] if e in found_exts]

        known = set(self.cfg["tracked_extensions"]) | \
                set(self.cfg["ignored_extensions"])
        new_exts = sorted(found_exts - known)
        for ext in new_exts:
            ans = messagebox.askyesno("Новый тип файла",
                "Обнаружен новый тип файлов: {}\n\n"
                "Добавить его в обрабатываемые?".format(ext))
            if ans:
                self.cfg["tracked_extensions"].append(ext)
            else:
                self.cfg["ignored_extensions"].append(ext)

        save_config(self.cfg)
        self.refresh_lists()

    def scan_files(self, silent=False):
        folder = self.cfg["folder"]
        if not os.path.isdir(folder):
            if not silent:
                messagebox.showerror("Скан", "Папка не найдена:\n{}".format(folder))
            return
        tracked_ext = set(e.lower() for e in self.cfg["tracked_extensions"])
        known = set(self.cfg["tracked_files"]) | set(self.cfg["ignored_files"])
        new_files = []
        for name in os.listdir(folder):
            p = os.path.join(folder, name)
            if not os.path.isfile(p): continue
            ext = os.path.splitext(name)[1].lower()
            if ext in tracked_ext and name not in known:
                new_files.append(name)
        if not new_files:
            if not silent:
                messagebox.showinfo("Скан", "Новых файлов нет.")
            return
        for name in sorted(new_files):
            ans = messagebox.askyesno("Новый файл",
                "Обнаружен новый файл: {}\n\n"
                "Добавить его в обрабатываемые?".format(name))
            if ans:
                self.cfg["tracked_files"].append(name)
            else:
                self.cfg["ignored_files"].append(name)
        save_config(self.cfg); self.refresh_lists()


def main():
    cfg = load_config()
    root = tk.Tk()
    App(root, cfg)
    root.mainloop()


if __name__ == "__main__":
    main()