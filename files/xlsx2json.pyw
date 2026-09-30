# -*- coding: utf-8 -*-
"""
GUI-обёртка над xlsx2json.
Запуск: двойной клик по xlsx2json.pyw (или `pythonw xlsx2json.pyw`).
Пока окно открыто — работает слежение за папкой.
Закрытие окна полностью останавливает скрипт.

Служебные файлы рядом со скриптом:
  xlsx2json.config.json  — конфиг
  xlsx2json.state.json   — состояние (дата последнего полного отчёта + file_state)
  xlsx2json.log.md       — лог (дописывается между запусками)
"""
import sys
sys.dont_write_bytecode = True

import os
import json
import time
import queue
import threading
import traceback
import tkinter as tk
from tkinter import ttk, messagebox
from tkinter.scrolledtext import ScrolledText
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from xlsx2json import convert, save_json  # noqa

CONFIG_PATH = os.path.join(HERE, "xlsx2json.config.json")
STATE_PATH = os.path.join(HERE, "xlsx2json.state.json")
LOG_PATH = os.path.join(HERE, "xlsx2json.log.md")

DEFAULT_CONFIG = {
    "watch_folder": "",
    "poll_interval_sec": 2,
    "quiet_period_sec": 1,
    "min_export_interval_sec": 1,
    "scp_server": "slqamsk@193.37.70.210",
    # База для удалённой папки. Полный путь = <base> + "<YYYY-MM-DD>/".
    # Например: "~/Downloads/"  →  "~/Downloads/2026-09-29/"
    "scp_remote_base": "~/Downloads/",
}


def load_config():
    if not os.path.isfile(CONFIG_PATH):
        cfg = dict(DEFAULT_CONFIG)
        cfg["watch_folder"] = HERE
        save_config(cfg)
        return cfg
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception:
        cfg = dict(DEFAULT_CONFIG)
        cfg["watch_folder"] = HERE
    # Миграция: старый ключ scp_remote_folder содержал полный путь с датой.
    # Убираем его — итоговый путь теперь вычисляется автоматически.
    cfg.pop("scp_remote_folder", None)
    for k, v in DEFAULT_CONFIG.items():
        cfg.setdefault(k, v)
    return cfg


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def load_state():
    if not os.path.isfile(STATE_PATH):
        return {}
    try:
        with open(STATE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_state(state):
    try:
        with open(STATE_PATH, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("xlsx2json")
        self.geometry("950x680")

        self.cfg = load_config()
        self.state = load_state()
        self.watching = False
        self.stop_event = threading.Event()
        self.log_queue = queue.Queue()
        # file_state хранится в state и переживает перезапуск.
        # Подгружаем с диска и делаем ссылку self.state["file_state"]
        # на тот же объект, чтобы сохранение было в одно место.
        self.file_state = self._normalize_file_state(
            self.state.get("file_state", {})
        )
        self.state["file_state"] = self.file_state
        self.log_lock = threading.Lock()

        self.log_file = open(LOG_PATH, "a", encoding="utf-8")
        self.log_file.write("\n" + "=" * 60 + "\n")
        self.log_file.write(
            f"Сессия запущена: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n"
        )
        self.log_file.flush()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

        self.worker = threading.Thread(target=self._watch_loop, daemon=True)
        self.worker.start()

        self.after(100, self._drain_log)
        self.after(150, self._check_folder)

        self._log(f"Лог-файл: {LOG_PATH}")

    # ---------- UI ----------
    def _build_ui(self):
        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill="both", expand=True, padx=6, pady=6)

        self.tab_convert = tk.Frame(self.notebook)
        self.tab_scp = tk.Frame(self.notebook)
        self.notebook.add(self.tab_convert, text="Конвертация")
        self.notebook.add(self.tab_scp, text="Копирование на сервер")

        self._build_tab_convert()
        self._build_tab_scp()

        self.notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)

        # Включаем Ctrl+C/V/X/A во всех текстовых полях, включая русскую раскладку
        for w in (self.log_box, self.scp_files_box, self.scp_cmd_box,
                  self.scp_server_entry, self.scp_remote_display):
            self._enable_clipboard_any_layout(w)

    def _build_tab_convert(self):
        parent = self.tab_convert

        top = tk.Frame(parent)
        top.pack(fill="x", padx=10, pady=(10, 4))
        tk.Label(top, text="Папка наблюдения:").pack(side="left")
        self.folder_label = tk.Label(top, text=self.cfg["watch_folder"],
                                     fg="#333", anchor="w")
        self.folder_label.pack(side="left", padx=(6, 0), fill="x", expand=True)

        status = tk.Frame(parent)
        status.pack(fill="x", padx=10, pady=(0, 6))

        self.status_dot = tk.Label(status, text="●", fg="#999", font=("Arial", 14))
        self.status_dot.pack(side="left")
        self.status_text = tk.Label(status, text="Слежение остановлено")
        self.status_text.pack(side="left", padx=(4, 16))

        self.btn_start = tk.Button(status, text="Включить слежение",
                                   command=self._start_watching)
        self.btn_start.pack(side="left", padx=2)
        self.btn_stop = tk.Button(status, text="Выключить слежение",
                                  command=self._stop_watching, state="disabled")
        self.btn_stop.pack(side="left", padx=2)

        actions = tk.Frame(parent)
        actions.pack(fill="x", padx=10, pady=(0, 6))
        tk.Button(actions, text="Сконвертировать сейчас",
                  command=self._manual_convert).pack(side="left")
        tk.Button(actions, text="Перечитать конфиг",
                  command=self._reload_config).pack(side="left", padx=6)

        tk.Label(parent, text="Лог (дублируется в xlsx2json.log.md):").pack(
            anchor="w", padx=10)
        self.log_box = ScrolledText(parent, height=22, state="disabled",
                                    wrap="word", font=("Consolas", 9))
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 10))

    def _build_tab_scp(self):
        parent = self.tab_scp

        form = tk.Frame(parent)
        form.pack(fill="x", padx=10, pady=(10, 4))

        tk.Label(form, text="Сервер:").grid(row=0, column=0, sticky="w", pady=2)
        self.scp_server_var = tk.StringVar(value=self.cfg.get("scp_server", ""))
        self.scp_server_entry = tk.Entry(form, textvariable=self.scp_server_var,
                                         width=50)
        self.scp_server_entry.grid(row=0, column=1, sticky="we",
                                   padx=(6, 0), pady=2)

        tk.Label(form, text="Папка на сервере:").grid(row=1, column=0,
                                                      sticky="w", pady=2)
        # Read-only поле: путь вычисляется как <база> + <сегодняшняя дата>/
        self.scp_remote_display = tk.Entry(form, width=50, state="readonly",
                                           readonlybackground="#f3f3f3")
        self.scp_remote_display.grid(row=1, column=1, sticky="we",
                                     padx=(6, 0), pady=2)

        tk.Label(form, text="(база из конфига + сегодняшняя дата)",
                 fg="#888", font=("Arial", 8)).grid(
            row=2, column=1, sticky="w", padx=(6, 0))

        self.scp_remote_base_label = tk.Label(form, text="", fg="#888",
                                              font=("Arial", 8))
        self.scp_remote_base_label.grid(row=3, column=1, sticky="w",
                                        padx=(6, 0))

        tk.Button(form, text="Обновить список файлов",
                  command=self._scp_refresh).grid(
            row=4, column=1, sticky="w", padx=(6, 0), pady=(8, 2))

        form.columnconfigure(1, weight=1)

        tk.Label(parent, text="Файлы для копирования (.xlsx.json):").pack(
            anchor="w", padx=10, pady=(8, 2))
        self.scp_files_box = ScrolledText(parent, height=8, state="disabled",
                                          wrap="none", font=("Consolas", 9))
        self.scp_files_box.pack(fill="x", padx=10)

        tk.Label(parent, text="Команда:").pack(anchor="w", padx=10, pady=(8, 2))
        self.scp_cmd_box = ScrolledText(parent, height=8, state="disabled",
                                        wrap="word", font=("Consolas", 10))
        self.scp_cmd_box.pack(fill="both", expand=True, padx=10)

        btns = tk.Frame(parent)
        btns.pack(fill="x", padx=10, pady=(6, 10))
        tk.Button(btns, text="Скопировать команду",
                  command=self._scp_copy).pack(side="left")

        self._scp_refresh()

    # ---------- логирование ----------
    def _log(self, msg):
        stamp = datetime.now().strftime("%H:%M:%S")
        line = f"[{stamp}] {msg}"
        self.log_queue.put(line)
        try:
            with self.log_lock:
                self.log_file.write(line + "\n")
                self.log_file.flush()
        except Exception:
            pass

    def _log_raw(self, msg):
        self.log_queue.put(msg)
        try:
            with self.log_lock:
                self.log_file.write(msg + "\n")
                self.log_file.flush()
        except Exception:
            pass

    def _normalize_file_state(self, fs):
        """При загрузке из JSON кортеж (mtime, size) становится списком.
        Возвращаем его в tuple — иначе сравнение с текущим os.stat не сработает."""
        result = {}
        for path, rec in fs.items():
            k = rec.get("key")
            if isinstance(k, list):
                rec["key"] = tuple(k)
            result[path] = rec
        return result

    def _persist_file_state(self):
        """Сохраняет текущий file_state на диск (через общий state)."""
        try:
            save_state(self.state)
        except Exception:
            pass

    def _drain_log(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", msg + "\n")
                self.log_box.see("end")
                self.log_box.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(100, self._drain_log)

    # ---------- буфер обмена в любой раскладке ----------
    def _enable_clipboard_any_layout(self, widget):
        """Ctrl+C/V/X/A должны работать и в русской раскладке.

        В Tk на Windows при переключении раскладки меняется keysym:
        физическая клавиша C даёт keysym 'Cyrillic_es' вместо 'c',
        и стандартные биндинги на латиницу не срабатывают.
        Биндимся сразу на три варианта: латиница, кириллический символ
        и X11-имя keysym. 'break' в первом обработчике не даёт сработать
        остальным — двойного копирования не будет."""
        def make_handler(virtual_event):
            def handler(event):
                try:
                    widget.event_generate(virtual_event, when="now")
                except Exception:
                    pass
                return "break"
            return handler

        groups = [
            (("c", "с", "Cyrillic_es"), "<<Copy>>"),
            (("v", "м", "Cyrillic_em"), "<<Paste>>"),
            (("x", "ч", "Cyrillic_che"), "<<Cut>>"),
            (("a", "ф", "Cyrillic_ef"), "<<SelectAll>>"),
        ]
        for keys, virtual in groups:
            h = make_handler(virtual)
            for k in keys:
                try:
                    widget.bind(f"<Control-Key-{k}>", h)
                except tk.TclError:
                    pass

    # ---------- папка ----------
    def _check_folder(self):
        cfg_folder = os.path.abspath(self.cfg["watch_folder"] or "")
        run_folder = os.path.abspath(HERE)

        if not cfg_folder or cfg_folder == run_folder:
            if not self.cfg["watch_folder"]:
                self.cfg["watch_folder"] = run_folder
                save_config(self.cfg)
            self.folder_label.configure(text=self.cfg["watch_folder"])
            self._start_watching()
            return

        ans = messagebox.askyesnocancel(
            title="Папка наблюдения",
            message=(
                "В конфиге указана папка:\n"
                f"{cfg_folder}\n\n"
                "Скрипт запущен из папки:\n"
                f"{run_folder}\n\n"
                "Да — работать в текущей папке, перезаписать конфиг.\n"
                "Нет — использовать папку, которая указана в конфиге.\n"
                "Отмена — оставить слежение выключенным."
            ),
            yes="Да, работать в текущей папке, перезаписать конфиг",
            no="Нет, использовать папку, которая указана в конфиге",
        )
        if ans is True:
            self.cfg["watch_folder"] = run_folder
            save_config(self.cfg)
            self.folder_label.configure(text=self.cfg["watch_folder"])
            self._start_watching()
        elif ans is False:
            self.folder_label.configure(text=self.cfg["watch_folder"])
            self._start_watching()
        else:
            self._log("Слежение не запущено (пользователь отменил выбор папки).")

    def _reload_config(self):
        self.cfg = load_config()
        self.folder_label.configure(text=self.cfg["watch_folder"])
        self._log(f"Конфиг перечитан. Папка: {self.cfg['watch_folder']}")
        self._scp_refresh()

    # ---------- слежение ----------
    def _start_watching(self):
        self.watching = True
        self.status_dot.configure(fg="#2e7d32")
        self.status_text.configure(text="Слежение работает")
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self._log(f"Слежение включено: {self.cfg['watch_folder']}")

    def _stop_watching(self):
        self.watching = False
        self.status_dot.configure(fg="#999")
        self.status_text.configure(text="Слежение остановлено")
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self._log("Слежение выключено.")

    def _manual_convert(self):
        folder = self.cfg["watch_folder"]
        if not os.path.isdir(folder):
            self._log(f"Папка не существует: {folder}")
            return
        found = [n for n in os.listdir(folder)
                 if n.lower().endswith(".xlsx") and not n.startswith("~$")]
        if not found:
            self._log("В папке нет .xlsx файлов.")
            return
        self._log("Ручная конвертация всех .xlsx в папке.")
        for name in found:
            self._do_convert(os.path.join(folder, name), manual=True)
        self._scp_refresh()

    def _watch_loop(self):
        while not self.stop_event.is_set():
            try:
                if not self.watching:
                    time.sleep(0.5)
                    continue
                folder = self.cfg.get("watch_folder") or ""
                if not os.path.isdir(folder):
                    time.sleep(1)
                    continue

                poll = float(self.cfg["poll_interval_sec"])
                quiet = float(self.cfg["quiet_period_sec"])
                min_int = float(self.cfg["min_export_interval_sec"])
                now = time.time()

                for name in os.listdir(folder):
                    if not name.lower().endswith(".xlsx"):
                        continue
                    if name.startswith("~$"):
                        continue
                    path = os.path.join(folder, name)
                    try:
                        st = os.stat(path)
                    except OSError:
                        continue
                    key = (st.st_mtime, st.st_size)
                    rec = self.file_state.get(path)
                    if rec is None:
                        self.file_state[path] = {
                            "key": key,
                            "last_change_ts": now,
                            "last_export_ts": 0.0,
                            "pending": True,
                        }
                        self._log(f"Обнаружен: {name}")
                    elif rec["key"] != key:
                        rec["key"] = key
                        rec["last_change_ts"] = now
                        rec["pending"] = True
                        self._log(f"Изменён: {name}")

                for path, rec in list(self.file_state.items()):
                    if not rec["pending"]:
                        continue
                    if not os.path.isfile(path):
                        del self.file_state[path]
                        continue
                    if now - rec["last_change_ts"] < quiet:
                        continue
                    if now - rec["last_export_ts"] < min_int:
                        continue
                    self._do_convert(path, manual=False)
                    rec["pending"] = False
                    rec["last_export_ts"] = time.time()
                    self._persist_file_state()

                time.sleep(poll)
            except Exception as e:
                self._log(f"Ошибка watcher: {e}")
                time.sleep(1)

    # ---------- конвертация ----------
    def _is_first_report_today(self):
        today = datetime.now().strftime("%Y-%m-%d")
        return self.state.get("last_full_report_date") != today

    def _mark_full_report_today(self):
        self.state["last_full_report_date"] = datetime.now().strftime("%Y-%m-%d")
        save_state(self.state)

    def _do_convert(self, path, manual):
        try:
            want_report = manual or self._is_first_report_today()
            result, errors, report = convert(path, want_report=want_report)
            json_path = save_json(result, path, errors_count=len(errors))
            short = ", ".join(f"{k}: {len(v)}" for k, v in result.items())
            self._log(f"Конвертация выполнена: {os.path.basename(path)} → "
                      f"{os.path.basename(json_path)} ({short})")
            if want_report:
                self._log_raw(report)
                self._mark_full_report_today()
            if errors:
                self._log_raw("Замечания:")
                for e in errors:
                    self._log_raw("  - " + e)
        except Exception as e:
            self._log(f"Ошибка конвертации {path}: {e}")
            self._log_raw(traceback.format_exc())

    # ---------- вкладка «Копирование на сервер» ----------
    def _on_tab_changed(self, event):
        try:
            current = self.notebook.index(self.notebook.select())
            if current == 1:
                self._scp_refresh()
        except Exception:
            pass

    def _scp_remote_folder_full(self):
        """Полный путь на сервере: база из конфига + сегодняшняя дата."""
        base = (self.cfg.get("scp_remote_base") or "~/Downloads/").strip()
        if not base.endswith("/"):
            base += "/"
        return base + datetime.now().strftime("%Y-%m-%d") + "/"

    def _scp_collect_files(self):
        folder = self.cfg.get("watch_folder") or ""
        if not os.path.isdir(folder):
            return []
        return sorted(
            os.path.join(folder, n)
            for n in os.listdir(folder)
            if n.lower().endswith(".xlsx.json")
        )

    def _scp_build_command(self, paths):
        server = self.scp_server_var.get().strip()
        remote = self._scp_remote_folder_full()
        if not server:
            return ""
        if not paths:
            return ""
        # ssh "mkdir -p ..." && scp "file1" "file2" server:remote
        mkdir_cmd = f'ssh {server} "mkdir -p {remote}"'
        srcs = " ".join(f'"{p}"' for p in paths)
        scp_cmd = f"scp {srcs} {server}:{remote}"
        return f"{mkdir_cmd} && {scp_cmd}"

    def _scp_refresh(self):
        # Обновляем вычисленный путь (read-only поле)
        try:
            self.scp_remote_display.configure(state="normal")
            self.scp_remote_display.delete(0, "end")
            self.scp_remote_display.insert(0, self._scp_remote_folder_full())
            self.scp_remote_display.configure(state="readonly")
        except Exception:
            pass

        try:
            self.scp_remote_base_label.configure(
                text=f"База (из конфига): {self.cfg.get('scp_remote_base', '')}"
            )
        except Exception:
            pass

        paths = self._scp_collect_files()

        self.scp_files_box.configure(state="normal")
        self.scp_files_box.delete("1.0", "end")
        if not paths:
            self.scp_files_box.insert("end", "(в папке нет .xlsx.json файлов)\n")
        else:
            for p in paths:
                self.scp_files_box.insert("end", p + "\n")
        self.scp_files_box.configure(state="disabled")

        cmd = self._scp_build_command(paths)

        self.scp_cmd_box.configure(state="normal")
        self.scp_cmd_box.delete("1.0", "end")
        if cmd:
            self.scp_cmd_box.insert("end", cmd)
        else:
            self.scp_cmd_box.insert(
                "end",
                "(команда появится здесь, когда в папке будут .xlsx.json файлы)"
            )
        self.scp_cmd_box.configure(state="disabled")

    def _scp_copy(self):
        self._scp_refresh()
        cmd = self.scp_cmd_box.get("1.0", "end").strip()
        if not cmd or cmd.startswith("("):
            self._log("Нечего копировать: команда не сформирована.")
            return
        self.clipboard_clear()
        self.clipboard_append(cmd)
        self.update()
        self._log("Команда скопирована в буфер обмена.")

    # ---------- завершение ----------
    def _on_close(self):
        self.stop_event.set()
        try:
            if self.worker.is_alive():
                self.worker.join(timeout=2)
        except Exception:
            pass
        try:
            self._persist_file_state()
        except Exception:
            pass
        # Сохраняем текущее значение «Сервер» в конфиг
        try:
            self.cfg["scp_server"] = self.scp_server_var.get().strip()
            save_config(self.cfg)
        except Exception:
            pass
        try:
            self._log("Завершение работы.")
            with self.log_lock:
                self.log_file.close()
        except Exception:
            pass
        self.destroy()


if __name__ == "__main__":
    app = App()
    app.mainloop()