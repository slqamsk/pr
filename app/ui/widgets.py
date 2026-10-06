"""Переиспользуемые виджеты: календарь-попап, таблица, диалог сохранения."""
import calendar
import json
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import date

from db import db


def ask_unsaved_changes(parent=None) -> str:
    """Возвращает 'save' | 'discard' | 'cancel'."""
    ans = messagebox.askyesnocancel(
        "Несохранённые изменения",
        "В текущей записи есть несохранённые изменения.\n\n"
        "Сохранить их?\n\n"
        "Да — сохранить и продолжить\n"
        "Нет — не сохранять и продолжить\n"
        "Отмена — вернуться к редактированию",
        parent=parent,
    )
    if ans is None:
        return "cancel"
    return "save" if ans else "discard"


class CalendarPopup(tk.Toplevel):
    """Всплывающий календарь. При выборе даты вызывает on_pick(date)."""
    _active = None

    def __init__(self, master, initial=None, on_pick=None, position=None):
        super().__init__(master)
        if CalendarPopup._active is not None:
            try:
                CalendarPopup._active.destroy()
            except Exception:
                pass
        CalendarPopup._active = self

        self.on_pick = on_pick
        self._root = master.winfo_toplevel() if hasattr(master, "winfo_toplevel") else master
        self._click_installed = False

        self.withdraw()
        self.overrideredirect(True)

        d = initial or date.today()
        self.year, self.month = d.year, d.month

        outer = ttk.Frame(self, borderwidth=1, relief="solid", padding=4)
        outer.pack()
        self._outer = outer

        self._draw()
        self.bind("<Escape>", lambda e: self.destroy())

        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        if position:
            px, py = position
        else:
            px = self._root.winfo_pointerx()
            py = self._root.winfo_pointery()
        self.geometry(f"{w}x{h}+{px}+{py}")

        self.deiconify()
        self.lift()
        self.attributes("-topmost", True)
        self.after(10, self._grab_focus)
        self.after(60, self._install_click_away)

    def _grab_focus(self):
        try:
            self.focus_force()
        except tk.TclError:
            pass

    def _install_click_away(self):
        try:
            self._root.bind_all("<Button-1>", self._on_global_click, add="+")
            self._click_installed = True
        except tk.TclError:
            pass

    def _on_global_click(self, event):
        try:
            if not self.winfo_exists():
                return
            wx, wy = self.winfo_rootx(), self.winfo_rooty()
            ww, wh = self.winfo_width(), self.winfo_height()
        except tk.TclError:
            return
        x, y = event.x_root, event.y_root
        if wx <= x <= wx + ww and wy <= y <= wy + wh:
            return
        self.destroy()

    def destroy(self):
        if CalendarPopup._active is self:
            CalendarPopup._active = None
        if self._click_installed:
            try:
                self._root.unbind_all("<Button-1>")
            except Exception:
                pass
            self._click_installed = False
        try:
            super().destroy()
        except tk.TclError:
            pass

    def _draw(self):
        for w in self._outer.winfo_children():
            w.destroy()

        head = ttk.Frame(self._outer)
        head.pack(fill="x", pady=(0, 4))
        ttk.Button(head, text="<", width=3, command=self._prev).pack(side="left")
        ttk.Label(head, text=f"{calendar.month_name[self.month]} {self.year}",
                  anchor="center").pack(side="left", expand=True)
        ttk.Button(head, text=">", width=3, command=self._next).pack(side="right")

        dow = ttk.Frame(self._outer)
        dow.pack()
        for i, name in enumerate(("Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс")):
            ttk.Label(dow, text=name, width=4, anchor="center").grid(row=0, column=i)

        body = ttk.Frame(self._outer)
        body.pack()
        cal = calendar.Calendar(firstweekday=0)
        for r, week in enumerate(cal.monthdayscalendar(self.year, self.month), start=1):
            for c, day in enumerate(week):
                if day == 0:
                    ttk.Label(body, text="", width=4).grid(row=r, column=c)
                else:
                    ttk.Button(body, text=str(day), width=4,
                               command=lambda d=day: self._pick(d)).grid(row=r, column=c)

    def _prev(self):
        self.year, self.month = ((self.year - 1, 12) if self.month == 1
                                 else (self.year, self.month - 1))
        self._redraw_and_resize()

    def _next(self):
        self.year, self.month = ((self.year + 1, 1) if self.month == 12
                                 else (self.year, self.month + 1))
        self._redraw_and_resize()

    def _redraw_and_resize(self):
        self._draw()
        self.update_idletasks()
        w = self.winfo_reqwidth()
        h = self.winfo_reqheight()
        self.geometry(f"{w}x{h}+{self.winfo_rootx()}+{self.winfo_rooty()}")

    def _pick(self, day):
        try:
            d = date(self.year, self.month, day)
        except ValueError:
            return
        cb = self.on_pick
        self.destroy()
        if cb:
            cb(d)


class ScrollableTable(ttk.Frame):
    """
    Таблица с фиксированной шириной колонок:
      * ширина колонки одинакова для всех строк,
      * длинный текст переносится (word wrap),
      * все ячейки строки растягиваются до высоты самой высокой ячейки,
      * ресайз колонок мышью (остальные не двигаются),
      * ширины колонок сохраняются между запусками (settings_key),
      * вертикальный и горизонтальный скролл,
      * чёрные границы между всеми ячейками,
      * подсветка выбранной строки.
    """
    BG_NORM  = "#ffffff"
    BG_SEL   = "#cce6ff"
    BG_HEAD  = "#e6e6e6"
    GRID_CLR = "#000000"
    CELL_PAD_X = 6
    CELL_PAD_Y = 4
    BORDER    = 1

    def __init__(self, parent, columns, on_select=None, settings_key=None):
        super().__init__(parent)
        self.columns = list(columns)
        self.widths = {c["key"]: int(c["width"]) for c in columns}
        self.on_select = on_select
        self.settings_key = settings_key
        self._rows = []
        self._selected = None
        self._drag = None
        self._handles = []
        self._load_widths()
        self._build()

    # ---------------- сохранение ширин ----------------
    def _load_widths(self):
        if not self.settings_key:
            return
        raw = db.get_setting(self.settings_key)
        if not raw:
            return
        try:
            saved = json.loads(raw)
        except (ValueError, TypeError):
            return
        if not isinstance(saved, dict):
            return
        for col in self.columns:
            k = col["key"]
            if k in saved:
                try:
                    self.widths[k] = max(40, int(saved[k]))
                except (ValueError, TypeError):
                    pass

    def _save_widths(self):
        if not self.settings_key:
            return
        try:
            db.set_setting(self.settings_key, json.dumps(self.widths))
        except Exception:
            pass

    # ---------------- построение ----------------
    def _build(self):
        self.header_canvas = tk.Canvas(self, height=32, highlightthickness=0,
                                       bg=self.BG_HEAD)
        self.header_canvas.pack(fill="x", side="top")
        self.header = tk.Frame(self.header_canvas, bg=self.BG_HEAD)
        self.header_canvas.create_window((0, 0), window=self.header, anchor="nw")

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True)
        wrap.rowconfigure(0, weight=1)
        wrap.columnconfigure(0, weight=1)

        self.vsb = ttk.Scrollbar(wrap, orient="vertical")
        self.hsb = ttk.Scrollbar(wrap, orient="horizontal")
        self.body_canvas = tk.Canvas(wrap, highlightthickness=0, bg=self.BG_NORM,
                                     yscrollcommand=self.vsb.set,
                                     xscrollcommand=self._on_xscroll)
        self.vsb.configure(command=self.body_canvas.yview)
        self.hsb.configure(command=self._xview)
        self.body_canvas.grid(row=0, column=0, sticky="nsew")
        self.vsb.grid(row=0, column=1, sticky="ns")
        self.hsb.grid(row=1, column=0, sticky="ew")

        self.body = tk.Frame(self.body_canvas, bg=self.BG_NORM)
        self.body_canvas.create_window((0, 0), window=self.body, anchor="nw")

        self._build_header_labels()
        self.body.bind("<Configure>", self._update_scrollregion)

    def _build_header_labels(self):
        for i, col in enumerate(self.columns):
            self.header.columnconfigure(i, minsize=self.widths[col["key"]])
            lbl = tk.Label(self.header, text=col["title"], anchor="w",
                           bg=self.BG_HEAD, padx=self.CELL_PAD_X,
                           pady=self.CELL_PAD_Y,
                           highlightthickness=self.BORDER,
                           highlightbackground=self.GRID_CLR,
                           highlightcolor=self.GRID_CLR)
            lbl.grid(row=0, column=i, sticky="nsew")
        self._build_handles()

    def _build_handles(self):
        for h in self._handles:
            h.destroy()
        self._handles = []
        for i in range(len(self.columns) - 1):
            key = self.columns[i]["key"]
            h = tk.Frame(self.header, width=4, height=32,
                         cursor="sb_h_double_arrow", bg="#b0b0b0")
            h.place(x=0, y=0, width=4, height=32)
            h.lift()
            h.bind("<ButtonPress-1>", lambda e, k=key: self._drag_start(e, k))
            h.bind("<B1-Motion>", self._drag_move)
            h.bind("<ButtonRelease-1>", self._drag_end)
            self._handles.append(h)
        self._reposition_handles()

    def _reposition_handles(self):
        x = 0
        for i, col in enumerate(self.columns):
            x += self.widths[col["key"]]
            if i < len(self._handles):
                self._handles[i].place_configure(x=x - 2)

    # ---------------- скролл ----------------
    def _on_xscroll(self, first, last):
        self.hsb.set(first, last)
        try:
            self.header_canvas.xview_moveto(float(first))
        except (ValueError, TypeError):
            pass

    def _xview(self, *args):
        self.body_canvas.xview(*args)
        self.header_canvas.xview(*args)

    def _update_scrollregion(self, _e=None):
        self.update_idletasks()
        bbox = self.body_canvas.bbox("all")
        if bbox:
            self.body_canvas.configure(scrollregion=bbox)
            self.header_canvas.configure(scrollregion=(bbox[0], 0, bbox[2], 32))

    # ---------------- drag ----------------
    def _drag_start(self, event, key):
        self._drag = (key, event.x_root, self.widths[key])

    def _drag_move(self, event):
        if not self._drag:
            return
        key, x0, w0 = self._drag
        delta = event.x_root - x0
        self.widths[key] = max(40, w0 + delta)
        self._apply_widths()

    def _drag_end(self, _event):
        self._drag = None
        self._save_widths()

    def _apply_widths(self):
        total_w = 0
        for i, col in enumerate(self.columns):
            w = self.widths[col["key"]]
            self.header.columnconfigure(i, minsize=w)
            total_w += w
        for row in self._rows:
            row["frame"].configure(width=total_w)
            self._layout_row(row)
        self._reposition_handles()
        self.update_idletasks()
        self._update_scrollregion()

    # ---------------- public API ----------------
    def set_rows(self, rows_data, iid_key="id"):
        for row in self._rows:
            row["frame"].destroy()
        self._rows = []
        self._selected = None
        for data in rows_data:
            self._add_row(data, iid_key)
        self.update_idletasks()
        self._update_scrollregion()

    def clear_selection(self):
        self._paint_selected(None)

    def select_iid(self, iid):
        """Программно подсветить строку. on_select НЕ вызывается."""
        if iid is None:
            self._paint_selected(None)
            return
        iid = str(iid)
        for row in self._rows:
            if row["iid"] == iid:
                self._paint_selected(iid)
                return
        self._paint_selected(None)

    # ---------------- rows ----------------
    def _add_row(self, data, iid_key):
        iid = str(data[iid_key])
        total_w = sum(self.widths[c["key"]] for c in self.columns)

        frame = tk.Frame(self.body, bg=self.BG_NORM, width=total_w, height=1)
        frame.pack(fill="x", side="top")
        frame.pack_propagate(False)

        cells = {}
        for col in self.columns:
            key = col["key"]
            text = "" if data.get(key) is None else str(data.get(key, ""))
            lbl = tk.Label(frame, text=text, anchor="nw", justify="left",
                           bg=self.BG_NORM,
                           padx=self.CELL_PAD_X, pady=self.CELL_PAD_Y,
                           highlightthickness=self.BORDER,
                           highlightbackground=self.GRID_CLR,
                           highlightcolor=self.GRID_CLR)
            lbl.bind("<Button-1>", lambda e, d=data: self._select(d, iid_key))
            cells[key] = lbl
        frame.bind("<Button-1>", lambda e, d=data: self._select(d, iid_key))

        row = {"iid": iid, "data": data, "frame": frame, "cells": cells}
        self._rows.append(row)
        self._layout_row(row)

    def _layout_row(self, row):
        """Раскладывает ячейки по фиксированным X/ширинам и выравнивает их высоту."""
        frame = row["frame"]
        cells = row["cells"]

        # 1. Первичная раскладка: только X и ширина. Высота — натуральная.
        x = 0
        for col in self.columns:
            key = col["key"]
            w = self.widths[key]
            lbl = cells[key]
            wrap_len = max(20, w - 2 * self.CELL_PAD_X - 2 * self.BORDER)
            lbl.configure(wraplength=wrap_len)
            lbl.place(x=x, y=0, width=w)
            x += w

        # 2. Натуральные высоты после переноса текста.
        frame.update_idletasks()
        h = 1
        for col in self.columns:
            h = max(h, cells[col["key"]].winfo_reqheight())

        # 3. Выравниваем все ячейки строки по максимальной высоте.
        x = 0
        for col in self.columns:
            key = col["key"]
            w = self.widths[key]
            cells[key].place_configure(x=x, y=0, width=w, height=h)
            x += w

        frame.configure(height=h)

    def _select(self, data, iid_key):
        iid = str(data[iid_key])
        self._paint_selected(iid)
        if self.on_select:
            self.on_select(data)

    def _paint_selected(self, iid):
        for row in self._rows:
            color = self.BG_SEL if row["iid"] == iid else self.BG_NORM
            row["frame"].configure(bg=color)
            for lbl in row["cells"].values():
                lbl.configure(bg=color)
        self._selected = iid


class EditableCriteriaList(ttk.Frame):
    """
    Редактируемый список критериев достижения.
    Строки: N | Текст | Статус | Комментарий | ✕
    """
    def __init__(self, parent, statuses, on_change=None, height=120):
        super().__init__(parent)
        self._statuses = list(statuses)
        self._on_change = on_change
        self._rows: list[dict] = []
        self._loading = False
        self._enabled = True
        self._height = height
        self._build()

    def _build(self):
        head = ttk.Frame(self)
        head.pack(fill="x")
        ttk.Label(head, text="N",           width=5,  anchor="w").pack(side="left")
        ttk.Label(head, text="Текст",       width=40, anchor="w").pack(side="left")
        ttk.Label(head, text="Статус",      width=18, anchor="w").pack(side="left")
        ttk.Label(head, text="Комментарий", width=25, anchor="w")\
            .pack(side="left", fill="x", expand=True)
        ttk.Label(head, text="", width=3).pack(side="left")

        wrap = ttk.Frame(self)
        wrap.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(wrap, highlightthickness=0, height=self._height)
        self.canvas.pack(side="left", fill="both", expand=True)
        vsb = ttk.Scrollbar(wrap, orient="vertical", command=self.canvas.yview)
        vsb.pack(side="right", fill="y")
        self.canvas.configure(yscrollcommand=vsb.set)

        self.rows_frame = ttk.Frame(self.canvas)
        self._window = self.canvas.create_window((0, 0), window=self.rows_frame,
                                                 anchor="nw")
        self.rows_frame.bind("<Configure>",
                             lambda e: self.canvas.configure(
                                 scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>",
                         lambda e: self.canvas.itemconfigure(self._window,
                                                             width=e.width))

    # ---------- public API ----------
    def set_items(self, items: list[dict]):
        """Программно устанавливает список. Не считается изменением."""
        self._loading = True
        try:
            for r in self._rows:
                r["frame"].destroy()
            self._rows.clear()
            for it in items:
                self._add_row_internal(
                    n=it.get("n"),
                    text=it.get("text", "") or "",
                    status_name=it.get("status_name") or "",
                    comment=it.get("comment") or "",
                )
        finally:
            self._loading = False

    def get_items(self) -> list[dict]:
        """Возвращает список критериев, отсортированный по (n, порядок ввода)."""
        result = []
        for i, r in enumerate(self._rows):
            n_text = r["n_var"].get().strip()
            try:
                n_val = int(n_text)
                if n_val < 1:
                    n_val = None
            except ValueError:
                n_val = None
            text = r["text_var"].get().strip()
            status = r["status_var"].get().strip()
            comment = r["comment_var"].get().strip()
            result.append({
                "_id":         i,
                "n":           n_val,
                "text":        text,
                "status_name": status or None,
                "comment":     comment or None,
            })
        result.sort(key=lambda x: (x["n"] if x["n"] is not None else 10**9, x["_id"]))
        return result

    def add_item(self):
        current = []
        for r in self._rows:
            try:
                current.append(int(r["n_var"].get().strip()))
            except ValueError:
                pass
        n = (max(current) + 1) if current else 1
        self._add_row_internal(n=n, text="", status_name="", comment="")
        self._notify_change()

    def clear(self):
        self.set_items([])

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        state = "normal" if enabled else "disabled"
        for r in self._rows:
            r["n_entry"].configure(state=state)
            r["text_entry"].configure(state=state)
            r["status_cmb"].configure(state="readonly" if enabled else "disabled")
            r["comment_entry"].configure(state=state)
            r["del_btn"].configure(state=state)

    # ---------- internals ----------
    def _add_row_internal(self, n, text, status_name, comment):
        row: dict = {}
        frame = ttk.Frame(self.rows_frame)
        frame.pack(fill="x", pady=1)

        row["n_var"]       = tk.StringVar(value=("" if n is None else str(n)))
        row["text_var"]    = tk.StringVar(value=text)
        row["status_var"]  = tk.StringVar(value=status_name)
        row["comment_var"] = tk.StringVar(value=comment)

        n_entry = ttk.Entry(frame, textvariable=row["n_var"], width=5)
        n_entry.pack(side="left")
        text_entry = ttk.Entry(frame, textvariable=row["text_var"])
        text_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
        status_cmb = ttk.Combobox(frame, textvariable=row["status_var"],
                                  values=[""] + self._statuses,
                                  state="readonly", width=18)
        status_cmb.pack(side="left", padx=(4, 0))
        comment_entry = ttk.Entry(frame, textvariable=row["comment_var"])
        comment_entry.pack(side="left", fill="x", expand=True, padx=(4, 0))
        del_btn = ttk.Button(frame, text="✕", width=3)
        del_btn.pack(side="left", padx=(4, 0))

        row["frame"]         = frame
        row["n_entry"]       = n_entry
        row["text_entry"]    = text_entry
        row["status_cmb"]    = status_cmb
        row["comment_entry"] = comment_entry
        row["del_btn"]       = del_btn
        self._rows.append(row)

        del_btn.configure(command=lambda rr=row: self._delete_row(rr))

        for var in (row["n_var"], row["text_var"],
                    row["status_var"], row["comment_var"]):
            var.trace_add("write", lambda *_: self._notify_change())

        n_entry.bind("<FocusOut>", lambda e: self._resort())

        if not self._enabled:
            n_entry.configure(state="disabled")
            text_entry.configure(state="disabled")
            status_cmb.configure(state="disabled")
            comment_entry.configure(state="disabled")
            del_btn.configure(state="disabled")

    def _delete_row(self, row):
        if row not in self._rows:
            return
        row["frame"].destroy()
        self._rows.remove(row)
        self._notify_change()

    def _resort(self):
        """Пересортировывает строки по N (стабильно, при равенстве — по порядку ввода)."""
        if self._loading:
            return
        def key_func(r):
            try:
                return int(r["n_var"].get().strip())
            except ValueError:
                return 10**9
        indexed = list(enumerate(self._rows))
        indexed.sort(key=lambda pair: (key_func(pair[1]), pair[0]))
        self._rows = [r for _, r in indexed]
        for r in self._rows:
            r["frame"].pack_forget()
        for r in self._rows:
            r["frame"].pack(fill="x", pady=1)

    def _notify_change(self):
        if self._loading:
            return
        if self._on_change:
            self._on_change()