import os
import json
import threading
import ctypes
from ctypes import Structure, windll, c_uint, sizeof, byref
import logging
from logging.handlers import RotatingFileHandler
from datetime import datetime, timedelta
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import winsound

import win32gui
import win32process
import psutil

# ---------- пути ----------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE_DIR, "activity.log")
CONFIG_FILE = os.path.join(BASE_DIR, "tracker_gui_config.json")
ICON_FILE = os.path.join(BASE_DIR, "icons", "main_icon.ico")

# ---------- AppUserModelID (отдельная группа на панели задач) ----------
APP_USER_MODEL_ID = "sslesarev.activitytracker.pomodoro.v1"

# ---------- конфиг ----------
DEFAULT_CONFIG = {
    "pomodoro_minutes": 25,
    "break_minutes": 5,
    "idle_threshold": 60,
    "activity_threshold": 5,
    "poll_interval": 5,
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2, ensure_ascii=False)
        except Exception:
            pass
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        cfg = dict(DEFAULT_CONFIG)
        for k, default_val in DEFAULT_CONFIG.items():
            if k in data:
                try:
                    cfg[k] = type(default_val)(data[k])
                except (TypeError, ValueError):
                    pass
        return cfg
    except Exception:
        return dict(DEFAULT_CONFIG)

CONFIG = load_config()
POMODORO_MINUTES   = CONFIG["pomodoro_minutes"]
BREAK_MINUTES      = CONFIG["break_minutes"]
IDLE_THRESHOLD     = CONFIG["idle_threshold"]
ACTIVITY_THRESHOLD = CONFIG["activity_threshold"]
POLL_INTERVAL      = CONFIG["poll_interval"]

# ---------- логгер ----------
logger = logging.getLogger("activity")
logger.setLevel(logging.INFO)
if not logger.handlers:
    handler = RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s | %(message)s", "%Y-%m-%d %H:%M:%S"))
    logger.addHandler(handler)

# ---------- звуки ----------
_sound_lock = threading.Lock()

def play_sound(kind: str):
    def _play():
        with _sound_lock:
            try:
                if kind == "pomodoro_start":
                    winsound.Beep(900, 200)
                elif kind == "pomodoro_end":
                    winsound.Beep(1200, 250)
                    winsound.Beep(1000, 250)
                    winsound.Beep(1200, 400)
                elif kind == "getup":
                    winsound.Beep(500, 200)
                    winsound.Beep(350, 200)
            except Exception:
                pass
    threading.Thread(target=_play, daemon=True).start()

# ---------- утилиты ----------
def fmt_hms(seconds: float) -> str:
    seconds = int(max(0.0, seconds))
    h, r = divmod(seconds, 3600)
    m, s = divmod(r, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"

# ---------- WinAPI ----------
class LASTINPUTINFO(Structure):
    _fields_ = [("cbSize", c_uint), ("dwTime", c_uint)]

def get_idle_seconds() -> float:
    info = LASTINPUTINFO()
    info.cbSize = sizeof(info)
    if not windll.user32.GetLastInputInfo(byref(info)):
        return 0.0
    millis = windll.kernel32.GetTickCount() - info.dwTime
    return millis / 1000.0

def get_active_window():
    hwnd = win32gui.GetForegroundWindow()
    if not hwnd:
        return None, None
    title = win32gui.GetWindowText(hwnd)
    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
        proc = psutil.Process(pid).name()
    except Exception:
        proc = "?"
    return proc, title


class TrackerApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Activity Tracker")
        self.root.geometry("1040x620")
        self.root.minsize(820, 460)

        # иконка окна (и панели задач, благодаря AppUserModelID)
        if os.path.exists(ICON_FILE):
            try:
                self.root.iconbitmap(ICON_FILE)
            except Exception:
                pass

        self.running = False
        self.stop_event = threading.Event()
        self.thread = None
        self.current_state = "—"
        self.log_pos = 0

        # Pomodoro state
        self.pomo_lock = threading.RLock()
        self.pomodoro_state = "IDLE"    # IDLE / RUNNING / BREAK
        self.pomodoro_start = None
        self.pomodoro_end = None
        self.break_start = None
        self.prev_user_active = False

        self._build_ui()
        self._preload_log()
        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(1000, self._tick)

        self._start()   # автостарт мониторинга

    # ---------- UI ----------
    def _build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        self.btn = ttk.Button(top, text="Старт", width=10, command=self._toggle)
        self.btn.pack(side="left")

        self.status_var = tk.StringVar(value="Остановлено")
        ttk.Label(top, textvariable=self.status_var,
                  font=("Segoe UI", 10, "bold")).pack(side="left", padx=(12, 24))

        ttk.Label(top, text="Состояние:").pack(side="left")
        self.state_var = tk.StringVar(value="—")
        self.state_label = ttk.Label(top, textvariable=self.state_var,
                                     font=("Segoe UI", 10, "bold"))
        self.state_label.pack(side="left", padx=6)

        ttk.Button(top, text="Открыть лог", command=self._open_log).pack(side="right")
        ttk.Button(top, text="Открыть папку", command=self._open_folder).pack(side="right", padx=6)

        # ---------- полоска Pomodoro ----------
        pomo = ttk.LabelFrame(
            self.root,
            text=f"Pomodoro  ({POMODORO_MINUTES} мин работы / {BREAK_MINUTES} мин перерыв)",
            padding=8,
        )
        pomo.pack(fill="x", padx=10, pady=(0, 6))

        btns = ttk.Frame(pomo)
        btns.pack(fill="x")

        self.btn_work = ttk.Button(btns, text="Начать работу", width=16,
                                   command=self._on_btn_work)
        self.btn_work.pack(side="left")
        self.btn_break = ttk.Button(btns, text="Начать перерыв", width=16,
                                    command=self._on_btn_break)
        self.btn_break.pack(side="left", padx=6)

        row = ttk.Frame(pomo)
        row.pack(fill="x", pady=(8, 0))

        self.pomo_state_var = tk.StringVar(value="Ожидание активности")
        self.pomo_state_label = ttk.Label(row, textvariable=self.pomo_state_var,
                                          font=("Segoe UI", 11, "bold"), width=20)
        self.pomo_state_label.pack(side="left")

        def make_field(label_text, var):
            ttk.Label(row, text=label_text).pack(side="left", padx=(18, 4))
            ttk.Label(row, textvariable=var, font=("Consolas", 11)).pack(side="left")

        self.pomo_start_var = tk.StringVar(value="—")
        make_field("Начало:", self.pomo_start_var)

        self.pomo_elapsed_var = tk.StringVar(value="—")
        make_field("Прошло:", self.pomo_elapsed_var)

        self.pomo_remaining_var = tk.StringVar(value="—")
        make_field("Осталось:", self.pomo_remaining_var)

        self.pomo_end_var = tk.StringVar(value="—")
        make_field("Окончание:", self.pomo_end_var)

        # ---------- лог ----------
        frame = ttk.LabelFrame(self.root, text="activity.log", padding=6)
        frame.pack(fill="both", expand=True, padx=10, pady=(0, 10))

        self.log_view = scrolledtext.ScrolledText(frame, wrap="none", height=20,
                                                  font=("Consolas", 9), state="disabled")
        self.log_view.pack(fill="both", expand=True)

    # ---------- файл лога ----------
    def _preload_log(self):
        if not os.path.exists(LOG_FILE):
            return
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                data = f.read()
            self.log_pos = len(data.encode("utf-8"))
            self._append(data)
        except Exception:
            pass

    def _append(self, text: str):
        self.log_view.configure(state="normal")
        self.log_view.insert("end", text)
        self.log_view.see("end")
        self.log_view.configure(state="disabled")

    def _tail_log(self):
        try:
            if not os.path.exists(LOG_FILE):
                return
            size = os.path.getsize(LOG_FILE)
            if size < self.log_pos:
                self.log_view.configure(state="normal")
                self.log_view.delete("1.0", "end")
                self.log_view.configure(state="disabled")
                self.log_pos = 0
            if size > self.log_pos:
                with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                    f.seek(self.log_pos)
                    data = f.read()
                    self.log_pos = f.tell()
                self._append(data)
        except Exception:
            pass

    # ---------- управление мониторингом ----------
    def _toggle(self):
        self._stop() if self.running else self._start()

    def _start(self):
        if self.running:
            return
        self.running = True
        self.stop_event.clear()
        self.btn.configure(text="Стоп")
        self.status_var.set("Работает")
        self.thread = threading.Thread(target=self._worker, name="tracker", daemon=True)
        self.thread.start()

    def _stop(self):
        if not self.running:
            return
        self.running = False
        self.stop_event.set()
        self.btn.configure(text="Старт")
        self.status_var.set("Остановлено")
        self.current_state = "—"
        with self.pomo_lock:
            self.pomodoro_state = "IDLE"
            self.pomodoro_start = None
            self.pomodoro_end = None
            self.break_start = None
            self.prev_user_active = False

    def _on_close(self):
        self._stop()
        self.root.after(150, self.root.destroy)

    # ---------- рабочий поток ----------
    def _worker(self):
        logger.info("=== Мониторинг запущен (порог простоя %d сек) ===", IDLE_THRESHOLD)

        was_active = None
        last_window = None
        session_start = datetime.now()

        while not self.stop_event.is_set():
            now = datetime.now()
            idle = get_idle_seconds()
            is_active = idle < IDLE_THRESHOLD
            user_active = idle < ACTIVITY_THRESHOLD

            # ---- лог активности ----
            if was_active is None:
                was_active = is_active
                session_start = now
            elif is_active != was_active:
                duration = (now - session_start).total_seconds()
                state = "РАБОТА" if was_active else "ПРОСТОЙ"
                logger.info("КОНЕЦ %s (%d сек)", state, int(duration))
                logger.info("НАЧАЛО %s", "РАБОТА" if is_active else "ПРОСТОЙ")
                was_active = is_active
                session_start = now
                last_window = None

            if is_active:
                win = get_active_window()
                if win != last_window and win[0] is not None:
                    if last_window is not None:
                        logger.info("  окно: %s | %s", win[0], win[1][:100])
                    last_window = win

            self.current_state = "РАБОТА" if is_active else "ПРОСТОЙ"

            # ---- Pomodoro ----
            self._pomodoro_tick(now, user_active)

            self.stop_event.wait(POLL_INTERVAL)

        logger.info("=== Мониторинг остановлен ===")

    # ---------- pomodoro: логика ----------
    def _pomodoro_tick(self, now: datetime, user_active: bool):
        with self.pomo_lock:
            st = self.pomodoro_state

            if st == "IDLE":
                if user_active and not self.prev_user_active:
                    self._begin_work(now, manual=False)

            elif st == "RUNNING":
                if now >= self.pomodoro_end:
                    self._begin_break(now, manual=False)

            elif st == "BREAK":
                elapsed = (now - self.break_start).total_seconds()
                break_sec = BREAK_MINUTES * 60

                if elapsed >= break_sec:
                    if user_active:
                        self._begin_work(now, manual=False)
                else:
                    if user_active:
                        if not self.prev_user_active:
                            logger.info("POMODORO активность в перерыве — вставай!")
                        play_sound("getup")

            self.prev_user_active = user_active

    def _begin_work(self, now: datetime, manual: bool):
        if self.break_start is not None:
            brk_sec = (now - self.break_start).total_seconds()
            prefix = "вручную" if manual else "после перерыва"
            logger.info("POMODORO НАЧАЛО РАБОТА (%s) — перерыв длился %.1f мин",
                        prefix, brk_sec / 60.0)
            self.break_start = None
        else:
            suffix = " — вручную" if manual else ""
            logger.info("POMODORO НАЧАЛО РАБОТА%s", suffix)

        self.pomodoro_state = "RUNNING"
        self.pomodoro_start = now
        self.pomodoro_end = now + timedelta(minutes=POMODORO_MINUTES)

        if not manual:
            play_sound("pomodoro_start")

    def _begin_break(self, now: datetime, manual: bool):
        if self.pomodoro_start is not None:
            work_sec = (now - self.pomodoro_start).total_seconds()
            if manual:
                logger.info("POMODORO НАЧАЛО ПЕРЕРЫВ (вручную) — работа длилась %.1f мин",
                            work_sec / 60.0)
            else:
                logger.info("POMODORO КОНЕЦ РАБОТА (%.1f мин) — перерыв %d мин",
                            work_sec / 60.0, BREAK_MINUTES)
        else:
            logger.info("POMODORO НАЧАЛО ПЕРЕРЫВ (вручную)")

        self.pomodoro_state = "BREAK"
        self.break_start = now
        self.pomodoro_start = None
        self.pomodoro_end = None
        self.prev_user_active = False

        if not manual:
            play_sound("pomodoro_end")

    # ---------- кнопки Pomodoro ----------
    def _on_btn_work(self):
        if not self.running:
            return
        with self.pomo_lock:
            if self.pomodoro_state == "RUNNING":
                return
            self._begin_work(datetime.now(), manual=True)

    def _on_btn_break(self):
        if not self.running:
            return
        with self.pomo_lock:
            if self.pomodoro_state == "BREAK":
                return
            self._begin_break(datetime.now(), manual=True)

    # ---------- периодический тик GUI ----------
    def _tick(self):
        self._tail_log()

        self.state_var.set(self.current_state)
        if self.current_state == "РАБОТА":
            self.state_label.configure(foreground="#1a7f37")
        elif self.current_state == "ПРОСТОЙ":
            self.state_label.configure(foreground="#b35c00")
        else:
            self.state_label.configure(foreground="gray")

        with self.pomo_lock:
            st = self.pomodoro_state
            pstart = self.pomodoro_start
            pend = self.pomodoro_end
            bstart = self.break_start

        if not self.running:
            self.btn_work.configure(state="disabled")
            self.btn_break.configure(state="disabled")
        else:
            self.btn_work.configure(state="disabled" if st == "RUNNING" else "normal")
            self.btn_break.configure(state="disabled" if st == "BREAK" else "normal")

        now = datetime.now()
        if st == "IDLE":
            self.pomo_state_var.set("Ожидание активности")
            self.pomo_state_label.configure(foreground="gray")
            self.pomo_start_var.set("—")
            self.pomo_elapsed_var.set("—")
            self.pomo_remaining_var.set("—")
            self.pomo_end_var.set("—")

        elif st == "RUNNING" and pstart and pend:
            total = POMODORO_MINUTES * 60
            elapsed = (now - pstart).total_seconds()
            remaining = total - elapsed
            self.pomo_state_var.set("РАБОТА")
            self.pomo_state_label.configure(foreground="#1a7f37")
            self.pomo_start_var.set(pstart.strftime("%H:%M:%S"))
            self.pomo_elapsed_var.set(fmt_hms(elapsed))
            self.pomo_remaining_var.set(fmt_hms(remaining))
            self.pomo_end_var.set(pend.strftime("%H:%M:%S"))

        elif st == "BREAK" and bstart:
            total = BREAK_MINUTES * 60
            elapsed = (now - bstart).total_seconds()
            remaining = total - elapsed
            end = bstart + timedelta(minutes=BREAK_MINUTES)
            over = elapsed >= total
            self.pomo_state_var.set("ПЕРЕРЫВ (истёк)" if over else "ПЕРЕРЫВ")
            self.pomo_state_label.configure(foreground="#b35c00")
            self.pomo_start_var.set(bstart.strftime("%H:%M:%S"))
            self.pomo_elapsed_var.set(fmt_hms(elapsed))
            self.pomo_remaining_var.set(fmt_hms(remaining))
            self.pomo_end_var.set(end.strftime("%H:%M:%S"))

        self.root.after(1000, self._tick)

    # ---------- прочие кнопки ----------
    def _open_log(self):
        if os.path.exists(LOG_FILE):
            os.startfile(LOG_FILE)
        else:
            messagebox.showinfo("Activity Tracker", "Лог пока пуст.")

    def _open_folder(self):
        os.startfile(BASE_DIR)


def main():
    # DPI-awareness
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass

    # отдельная группа на панели задач (не смешивается с другими Python-приложениями)
    try:
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)
    except Exception:
        pass

    root = tk.Tk()
    app = TrackerApp(root)   # noqa: F841
    root.mainloop()


if __name__ == "__main__":
    main()