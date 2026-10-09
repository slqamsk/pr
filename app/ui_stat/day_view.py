"""Дневной обзор Actions — шкала времени с блоками."""
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date, datetime, timedelta

from db import db
from ui.widgets import CalendarPopup
from ui_stat.action_edit import ActionEditDialog


# Пастельные цвета ролей. Стабильный маппинг по имени.
_ROLE_COLORS = [
    "#ADD8E6",  # lightblue
    "#90EE90",  # lightgreen
    "#FFDAB9",  # peachpuff
    "#E6E6FA",  # lavender
    "#F5FFFA",  # mintcream
    "#FFFACD",  # lemonchiffon
    "#FFB6C1",  # lightpink
    "#B0C4DE",  # lightsteelblue
]
_ROLE_COLOR_DEFAULT = "#E0E0E0"

# Цвета статусов действий.
_STATUS_COLORS = {
    "В работе":         "#FFC107",
    "Начал задачу":     "#03A9F4",
    "Продолжил задачу": "#1565C0",
    "Завершил задачу":  "#43A047",
    "Без задачи":       "#9E9E9E",
}
_STATUS_COLOR_DEFAULT = "#9E9E9E"

_SCALE_WIDTH          = 70
_MIN_TRACK_WIDTH      = 220
_STATUS_STRIP_RATIO   = 0.10
_PX_PER_HOUR          = 60
_LINE_HEIGHT          = 14
_TOP_MARGIN           = 15
_NOW_LINE_COLOR       = "#0055FF"


def _parse_hhmm(s):
    if not s:
        return None
    try:
        h, m = s.strip().split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


class ActionBlock:
    """Разрешение времени действия для отрисовки."""
    __slots__ = ("action", "start_min", "end_min", "conflicts", "has_position")

    def __init__(self, action: dict):
        self.action = action
        self.start_min = None
        self.end_min = None
        self.conflicts = []
        self.has_position = False
        self._resolve()

    def _resolve(self):
        a = self.action
        s = _parse_hhmm(a.get("start_time"))
        e = _parse_hhmm(a.get("end_time"))
        try:
            d = int(a["duration"]) if a.get("duration") is not None else None
        except (ValueError, TypeError):
            d = None
        try:
            pp = float(a["pp"]) if a.get("pp") is not None else None
        except (ValueError, TypeError):
            pp = None
        pp_min = int(round(pp * 30)) if pp is not None else None

        if s is not None and e is not None:
            if e < s:
                e += 24 * 60
            self.start_min, self.end_min = s, e
            self.has_position = True
            real_dur = e - s
            if d is not None and abs(d - real_dur) > 5:
                self.conflicts.append(
                    f"Duration ({d} мин) не совпадает с Start/End ({real_dur} мин)"
                )
            if pp_min is not None and abs(pp_min - real_dur) > 5:
                self.conflicts.append(
                    f"PP ({pp:g}) → {pp_min} мин не совпадает с длительностью ({real_dur} мин)"
                )
            return

        if s is not None and d is not None:
            self.start_min, self.end_min = s, s + d
            self.has_position = True
            if pp_min is not None and abs(pp_min - d) > 5:
                self.conflicts.append(
                    f"PP ({pp:g}) → {pp_min} мин не совпадает с Duration ({d} мин)"
                )
            return

        if e is not None and d is not None:
            self.start_min, self.end_min = max(0, e - d), e
            self.has_position = True
            if pp_min is not None and abs(pp_min - d) > 5:
                self.conflicts.append(
                    f"PP ({pp:g}) → {pp_min} мин не совпадает с Duration ({d} мин)"
                )
            return

        if s is not None and pp_min is not None:
            self.start_min, self.end_min = s, s + pp_min
            self.has_position = True
            return

        if e is not None and pp_min is not None:
            self.start_min, self.end_min = max(0, e - pp_min), e
            self.has_position = True
            return

        if s is not None:
            self.start_min, self.end_min = s, s + 30
            self.has_position = True
            return

        if e is not None:
            self.start_min, self.end_min = max(0, e - 30), e
            self.has_position = True
            return

        if d is not None:
            self.end_min = d
        elif pp_min is not None:
            self.end_min = pp_min
        else:
            self.end_min = 30
        self.start_min = 0
        self.has_position = False


class DayView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=8)
        self.current_date = date.today()
        self.var_date_label = tk.StringVar()
        self.var_stats = tk.StringVar(value="")
        self.blocks: list[ActionBlock] = []
        self.selected_block: ActionBlock | None = None
        self._block_by_item: dict[int, ActionBlock] = {}
        self._drag_start = None
        self._build_ui()
        self.reload()
        self._schedule_time_refresh()

    # ---------- UI ----------
    def _build_ui(self):
        top = ttk.Frame(self, padding=(0, 0, 0, 8))
        top.pack(fill="x")

        ttk.Button(top, text="◀", width=3,
                   command=self._prev_day).pack(side="left")
        ttk.Button(top, text="📅", width=3,
                   command=self._open_cal).pack(side="left", padx=2)
        ttk.Label(top, textvariable=self.var_date_label,
                  font=("TkDefaultFont", 11, "bold"),
                  width=14, anchor="center").pack(side="left", padx=6)
        ttk.Button(top, text="▶", width=3,
                   command=self._next_day).pack(side="left")

        ttk.Label(top, textvariable=self.var_stats, padding=(20, 0))\
            .pack(side="left")

        ttk.Button(top, text="Обновить",
                   command=self.reload).pack(side="right")

        body = ttk.PanedWindow(self, orient="horizontal")
        body.pack(fill="both", expand=True)

        left = ttk.Frame(body)
        # Сетка, чтобы горизонтальный скроллбар встал под canvas,
        # а не в правом нижнем углу.
        left.rowconfigure(0, weight=1)
        left.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(left, bg="#ffffff", highlightthickness=1,
                                highlightbackground="#a0a0a0")
        self.canvas.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(left, orient="vertical", command=self.canvas.yview)
        vsb.grid(row=0, column=1, sticky="ns")

        hsb = ttk.Scrollbar(left, orient="horizontal", command=self.canvas.xview)
        hsb.grid(row=1, column=0, sticky="ew")

        self.canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)

        right = ttk.Frame(body, padding=(8, 0))
        right.configure(width=360)
        right.pack_propagate(False)

        ttk.Label(right, text="Информация",
                  font=("TkDefaultFont", 10, "bold"))\
            .pack(anchor="w", pady=(0, 4))

        self.txt_info = tk.Text(right, wrap="word", height=20,
                                font=("TkDefaultFont", 9),
                                bg="#f5f5f5", state="disabled",
                                relief="solid", borderwidth=1)
        self.txt_info.pack(fill="both", expand=True)

        self.btn_edit = ttk.Button(right, text="Редактировать",
                                   command=self._on_edit, state="disabled")
        self.btn_edit.pack(fill="x", pady=(6, 0))

        body.add(left, weight=3)
        body.add(right, weight=0)

        self.canvas.bind("<Configure>", lambda e: self.redraw())
        self.canvas.bind("<MouseWheel>", self._on_wheel)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)

    # ---------- прокрутка ----------
    def _on_wheel(self, event):
        delta = event.delta
        if delta == 0:
            return
        step = -1 if delta > 0 else 1
        self.canvas.yview_scroll(step, "units")

    def _on_press(self, event):
        cx = self.canvas.canvasx(event.x)
        cy = self.canvas.canvasy(event.y)
        items = self.canvas.find_overlapping(cx, cy, cx, cy)
        # Ищем верхний (последний в списке) элемент, который соответствует блоку
        for item in reversed(items):
            b = self._block_by_item.get(item)
            if b is not None:
                self._on_block_click(b)
                self._drag_start = None
                return
        self._drag_start = (event.x, event.y)
        self.canvas.scan_mark(event.x, event.y)

    def _on_drag(self, event):
        if self._drag_start is None:
            return
        self.canvas.scan_dragto(event.x, event.y, gain=1)

    def _on_release(self, _event):
        self._drag_start = None

    # ---------- автообновление времени ----------
    def _schedule_time_refresh(self):
        now = datetime.now()
        ms_to_next_minute = (60 - now.second) * 1000 - now.microsecond // 1000
        if ms_to_next_minute < 100:
            ms_to_next_minute += 60000
        self.after(ms_to_next_minute, self._on_time_tick)

    def _on_time_tick(self):
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        self.redraw()
        self._schedule_time_refresh()

    # ---------- данные ----------
    def reload(self):
        self.var_date_label.set(self.current_date.strftime("%d.%m.%Y"))

        raw = db.list_actions()
        iso = self.current_date.strftime("%Y-%m-%d")
        todays = [r for r in raw if r.get("date") == iso]

        self.blocks = [ActionBlock(a) for a in todays]
        self.selected_block = None
        self._update_stats()
        self._show_info(None)
        self.redraw()

    def _update_stats(self):
        n = len(self.blocks)
        total_min = sum(max(0, (b.end_min or 0) - (b.start_min or 0))
                        for b in self.blocks)
        h, m = divmod(total_min, 60)
        self.var_stats.set(f"Actions: {n} · Всего: {h} ч {m:02d} мин")

    def _prev_day(self):
        self.current_date -= timedelta(days=1)
        self.reload()

    def _next_day(self):
        self.current_date += timedelta(days=1)
        self.reload()

    def _open_cal(self):
        CalendarPopup(
            self,
            initial=self.current_date,
            on_pick=self._on_date_picked,
        )

    def _on_date_picked(self, d: date):
        self.current_date = d
        self.reload()

    # ---------- отрисовка ----------
    def redraw(self):
        c = self.canvas
        c.delete("all")
        self._block_by_item.clear()
        w = c.winfo_width()
        if w < 50:
            return

        with_pos = [b for b in self.blocks if b.has_position]
        without_pos = [b for b in self.blocks if not b.has_position]

        tracks_1 = self._layout_tracks(with_pos)
        tracks_2 = self._layout_tracks(without_pos)
        n1 = max(1, len(tracks_1))
        n2 = max(1, len(tracks_2))

        max_end = 24 * 60
        for b in self.blocks:
            if b.end_min and b.end_min > max_end:
                max_end = b.end_min
        max_end_h = (max_end + 59) // 60
        total_h = max_end_h * _PX_PER_HOUR + _TOP_MARGIN + 20

        avail = max(w - _SCALE_WIDTH - 30, _MIN_TRACK_WIDTH)
        if without_pos:
            half = avail // 2
            track_w_1 = max(_MIN_TRACK_WIDTH, half // n1)
            track_w_2 = max(_MIN_TRACK_WIDTH, half // n2)
        else:
            track_w_1 = max(_MIN_TRACK_WIDTH, avail // n1)
            track_w_2 = 0

        total_w = _SCALE_WIDTH + track_w_1 * n1 + track_w_2 * n2 + 30

        # Шкала
        for hh in range(max_end_h + 1):
            y = hh * _PX_PER_HOUR + _TOP_MARGIN
            c.create_text(_SCALE_WIDTH - 8, y, text=f"{hh:02d}:00", anchor="e",
                          font=("TkDefaultFont", 8))
            c.create_line(_SCALE_WIDTH - 6, y, total_w, y,
                          fill="#000000", width=2)
            for m10 in (10, 20, 30, 40, 50):
                y_sub = y + m10 * _PX_PER_HOUR // 60
                if m10 == 30:
                    c.create_line(_SCALE_WIDTH - 3, y_sub, _SCALE_WIDTH + 4, y_sub,
                                  fill="#404040", width=1)
                    c.create_line(_SCALE_WIDTH + 4, y_sub, total_w, y_sub,
                                  fill="#c0c0c0", width=1)
                else:
                    c.create_line(_SCALE_WIDTH - 2, y_sub, _SCALE_WIDTH + 2, y_sub,
                                  fill="#808080", width=1)

        # Блоки с временем
        for ti, track in enumerate(tracks_1):
            x0 = _SCALE_WIDTH + ti * track_w_1
            for b in track:
                self._draw_block(b, x0, track_w_1, no_position=False)

        # Блоки без времени
        if without_pos:
            x_base = _SCALE_WIDTH + n1 * track_w_1 + 10
            for ti, track in enumerate(tracks_2):
                x0 = x_base + ti * track_w_2
                for b in track:
                    self._draw_block(b, x0, track_w_2, no_position=True)

        # Линия текущего времени (только для сегодняшней даты).
        # Рисуется последней — поверх блоков.
        if self.current_date == date.today():
            now = datetime.now()
            now_min = now.hour * 60 + now.minute
            y_now = now_min * _PX_PER_HOUR / 60 + _TOP_MARGIN
            c.create_line(0, y_now, total_w, y_now,
                          fill=_NOW_LINE_COLOR, width=2)

        c.configure(scrollregion=(0, 0, total_w, total_h))

    def _layout_tracks(self, blocks):
        sorted_blocks = sorted(blocks,
                               key=lambda b: (b.start_min or 0, b.end_min or 0))
        tracks = []
        for b in sorted_blocks:
            placed = False
            for tr in tracks:
                if (b.start_min or 0) >= (tr[-1].end_min or 0):
                    tr.append(b)
                    placed = True
                    break
            if not placed:
                tracks.append([b])
        return tracks

    def _role_color(self, role_name):
        if not role_name:
            return _ROLE_COLOR_DEFAULT
        return _ROLE_COLORS[sum(ord(ch) for ch in role_name) % len(_ROLE_COLORS)]

    def _build_block_text(self, b, h):
        a = b.action
        lines = [a.get("name") or "(без имени)"]
        if a.get("task_name"):
            lines.append(f"Task: {a['task_name']}")
        if a.get("epic_name"):
            lines.append(f"Epic: {a['epic_name']}")
        max_lines = max(1, h // _LINE_HEIGHT)
        return "\n".join(lines[:max_lines])

    def _draw_block(self, b, x0, width, no_position=False):
        c = self.canvas
        a = b.action

        if no_position:
            y0 = _TOP_MARGIN
            h = max(20, (b.end_min or 30) * _PX_PER_HOUR // 60)
        else:
            y0 = (b.start_min or 0) * _PX_PER_HOUR // 60 + _TOP_MARGIN
            h = max(14, ((b.end_min or 0) - (b.start_min or 0)) * _PX_PER_HOUR // 60)

        fill = self._role_color(a.get("role_name"))

        is_selected = (b is self.selected_block)
        outline_color = "#0040C0" if is_selected else "#505050"
        outline_width = 3 if is_selected else 1

        item = c.create_rectangle(x0, y0, x0 + width, y0 + h,
                                  fill=fill, outline=outline_color,
                                  width=outline_width)
        self._block_by_item[item] = b

        strip_w = max(3, int(width * _STATUS_STRIP_RATIO))
        strip_color = _STATUS_COLORS.get(a.get("status_name"),
                                          _STATUS_COLOR_DEFAULT)

        item = c.create_rectangle(x0, y0, x0 + strip_w, y0 + h,
                                  fill=strip_color, outline="")
        self._block_by_item[item] = b

        item = c.create_rectangle(x0 + width - strip_w, y0, x0 + width, y0 + h,
                                  fill=strip_color, outline="")
        self._block_by_item[item] = b

        text = self._build_block_text(b, h)
        item = c.create_text(x0 + strip_w + 4, y0 + 2, text=text, anchor="nw",
                             font=("TkDefaultFont", 8),
                             width=max(20, int(width - 2 * strip_w - 8)))
        self._block_by_item[item] = b

    # ---------- взаимодействие ----------
    def _on_block_click(self, b):
        self.selected_block = b
        self._show_info(b)
        self.redraw()

    def _show_info(self, b):
        w = self.txt_info
        w.configure(state="normal")
        w.delete("1.0", "end")

        if b is None:
            w.insert("1.0", "Выберите действие на шкале.")
            w.configure(state="disabled")
            self.btn_edit.configure(state="disabled")
            return

        a = b.action
        lines = [
            f"Название: {a.get('name') or '(без имени)'}",
        ]
        if a.get("description"):
            lines.append(f"Описание: {a['description']}")
        lines += [
            "",
            f"Дата: {a.get('date') or '—'}",
            f"Start: {a.get('start_time') or '—'}",
            f"End: {a.get('end_time') or '—'}",
            f"Duration: {a.get('duration') if a.get('duration') is not None else '—'}",
            f"PP: {a.get('pp') if a.get('pp') is not None else '—'}",
            "",
            f"Задача: {a.get('task_name') or '—'}",
            f"Эпик: {a.get('epic_name') or '—'}",
            f"Роль: {a.get('role_name') or '—'}",
            f"Подроль: {a.get('subrole_name') or '—'}",
            f"Статус: {a.get('status_name') or '—'}",
        ]
        if b.conflicts:
            lines.append("")
            lines.append("КОНФЛИКТЫ:")
            for cf in b.conflicts:
                lines.append(f"  • {cf}")

        w.insert("1.0", "\n".join(lines))

        if b.conflicts:
            txt = w.get("1.0", "end-1c")
            idx = txt.find("КОНФЛИКТЫ:")
            if idx >= 0:
                w.tag_add("conflict", f"1.0+{idx}c", "end")
                w.tag_config("conflict", foreground="#a00000")

        w.configure(state="disabled")
        self.btn_edit.configure(state="normal")

    def _on_edit(self):
        if self.selected_block is None:
            return
        action_id = self.selected_block.action.get("id")
        row = next((r for r in db.list_actions() if r["id"] == action_id), None)
        if row is None:
            messagebox.showwarning("Ошибка",
                                   "Действие не найдено в базе.",
                                   parent=self.winfo_toplevel())
            return

        dlg = ActionEditDialog(self.winfo_toplevel(), row)
        if dlg.result:
            self.reload()
            self._select_by_id(action_id)

    def _select_by_id(self, action_id):
        for b in self.blocks:
            if b.action.get("id") == action_id:
                self.selected_block = b
                self._show_info(b)
                self.redraw()
                return