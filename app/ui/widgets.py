"""Переиспользуемые виджеты: календарь-попап, таблица, диалог сохранения, SQL-фильтр."""
import calendar
import json
import tkinter as tk
from tkinter import ttk, messagebox
import tkinter.font as tkfont
from datetime import date

from db import db


def ask_unsaved_changes(parent=None) -> str:
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


def bind_mousewheel_recursive(widget, canvas):
    """Рекурсивно привязывает колёсико мыши на виджет и всех его детей."""
    def _on_wheel(event):
        try:
            step = -1 * int(event.delta / 120) or (-1 if event.delta > 0 else 1)
        except (ValueError, AttributeError):
            step = -1 if event.delta > 0 else 1
        canvas.yview_scroll(step * 3, "units")
        return "break"

    def _bind(w):
        try:
            w.bind("<MouseWheel>", _on_wheel)
        except tk.TclError:
            return
        for child in w.winfo_children():
            _bind(child)

    _bind(widget)


def setup_vertical_paned(parent, sash_key):
    """
    Создаёт вертикальный PanedWindow. Возвращает (paned, save_ui_state).
    Панели добавляются вызывающим кодом — как дочерние виджеты paned.
    Позиция sash хранится в settings по ключу sash_key.
    """
    paned = ttk.PanedWindow(parent, orient="vertical")
    paned.pack(fill="both", expand=True)

    def _save_sash(_e=None):
        try:
            pos = paned.sashpos(0)
            if pos > 0:
                db.set_setting(sash_key, str(pos))
        except Exception:
            pass

    def save_ui_state():
        _save_sash()

    def _apply_saved():
        raw = db.get_setting(sash_key)
        if not raw:
            return
        try:
            pos = int(raw)
        except (ValueError, TypeError):
            return
        try:
            h = paned.winfo_height()
            if h > 200:
                pos = max(100, min(pos, h - 150))
                paned.sashpos(0, pos)
        except tk.TclError:
            pass

    parent.after(200, _apply_saved)
    paned.bind("<ButtonRelease-1>", _save_sash)

    return paned, save_ui_state


# ============== CalendarPopup ==============

class CalendarPopup(tk.Toplevel):
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


# ============== ScrollableTable ==============

class ScrollableTable(ttk.Frame):
    BG_NORM  = "#ffffff"
    BG_SEL   = "#cce6ff"
    BG_HEAD  = "#e6e6e6"
    GRID_CLR = "#000000"
    CELL_PAD_X = 6
    CELL_PAD_Y = 4
    BORDER    = 1
    HEADER_H  = 32

    def __init__(self, parent, columns, on_select=None, settings_key=None,
                 autofit=False, wrap_when_narrow=False):
        """
        wrap_when_narrow: если True, при сужении колонки текст переносится;
                          если False (по умолчанию), при сужении текст обрезается.
        """
        super().__init__(parent)
        self.columns = list(columns)
        self.widths = {c["key"]: int(c["width"]) for c in columns}
        self.on_select = on_select
        self.settings_key = settings_key
        self.autofit = autofit
        self.wrap_when_narrow = wrap_when_narrow
        self._rows = []
        self._selected = None
        self._drag = None
        self._handles = []
        self._header_labels = []
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

    def save_ui_state(self):
        self._save_widths()

    # ---------------- построение ----------------
    def _build(self):
        self.rowconfigure(1, weight=1)
        self.columnconfigure(0, weight=1)

        self.header_canvas = tk.Canvas(self, height=self.HEADER_H,
                                       highlightthickness=0, bg=self.BG_HEAD)
        self.header_canvas.grid(row=0, column=0, sticky="ew")
        self.header = tk.Frame(self.header_canvas, bg=self.BG_HEAD,
                               width=100, height=self.HEADER_H)
        self.header_canvas.create_window((0, 0), window=self.header, anchor="nw")

        self._header_spacer = tk.Frame(self, width=1, bg=self.BG_HEAD)
        self._header_spacer.grid(row=0, column=1, sticky="nsew")
        self._header_spacer.grid_propagate(False)

        self.body_canvas = tk.Canvas(self, highlightthickness=0, bg=self.BG_NORM)
        self.body_canvas.grid(row=1, column=0, sticky="nsew")

        self.vsb = ttk.Scrollbar(self, orient="vertical",
                                 command=self.body_canvas.yview)
        self.vsb.grid(row=1, column=1, sticky="ns")
        self.body_canvas.configure(yscrollcommand=self.vsb.set)

        self.hsb = ttk.Scrollbar(self, orient="horizontal",
                                 command=self._xview)
        self.hsb.grid(row=2, column=0, columnspan=2, sticky="ew")
        self.body_canvas.configure(xscrollcommand=self._on_xscroll)

        self.body = tk.Frame(self.body_canvas, bg=self.BG_NORM)
        self.body_canvas.create_window((0, 0), window=self.body, anchor="nw")

        self._build_header_labels()
        self.body.bind("<Configure>", self._update_scrollregion)

    def _build_header_labels(self):
        self._header_labels = []
        x = 0
        for col in self.columns:
            key = col["key"]
            w = self.widths[key]
            lbl = tk.Label(self.header, text=col["title"], anchor="w",
                           bg=self.BG_HEAD, padx=self.CELL_PAD_X,
                           pady=self.CELL_PAD_Y,
                           highlightthickness=self.BORDER,
                           highlightbackground=self.GRID_CLR,
                           highlightcolor=self.GRID_CLR)
            lbl.place(x=x, y=0, width=w, height=self.HEADER_H)
            self._header_labels.append(lbl)
            x += w
        self._build_handles()
        self._update_header_size()

    def _update_header_size(self):
        total_w = sum(self.widths[c["key"]] for c in self.columns)
        self.header.configure(width=total_w, height=self.HEADER_H)

    def _reposition_header_labels(self):
        x = 0
        for i, col in enumerate(self.columns):
            w = self.widths[col["key"]]
            self._header_labels[i].place_configure(x=x, width=w)
            x += w

    def _build_handles(self):
        for h in self._handles:
            h.destroy()
        self._handles = []
        x = 0
        for col in self.columns:
            key = col["key"]
            x += self.widths[key]
            h = tk.Frame(self.header, width=4, height=self.HEADER_H,
                         cursor="sb_h_double_arrow", bg="#b0b0b0")
            h.place(x=x - 2, y=0, width=4, height=self.HEADER_H)
            h.lift()
            h.bind("<ButtonPress-1>", lambda e, k=key: self._drag_start(e, k))
            h.bind("<B1-Motion>", self._drag_move)
            h.bind("<ButtonRelease-1>", self._drag_end)
            self._handles.append(h)

    def _reposition_handles(self):
        x = 0
        for i, col in enumerate(self.columns):
            x += self.widths[col["key"]]
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
        total_w = sum(self.widths[c["key"]] for c in self.columns)
        bbox = self.body_canvas.bbox("all")
        body_h = bbox[3] if bbox else 0
        self.body_canvas.configure(scrollregion=(0, 0, total_w, body_h))
        self.header_canvas.configure(scrollregion=(0, 0, total_w, self.HEADER_H))

    # ---------------- drag ----------------
    def _drag_start(self, event, key):
        self._drag = (key, event.x_root, self.widths[key])
        self.bind_all("<B1-Motion>", self._drag_move)
        self.bind_all("<ButtonRelease-1>", self._drag_end)

    def _drag_move(self, event):
        if not self._drag:
            return
        key, x0, w0 = self._drag
        delta = event.x_root - x0
        self.widths[key] = max(40, w0 + delta)
        self._apply_widths()

    def _drag_end(self, _event):
        if not self._drag:
            return
        self._drag = None
        self.unbind_all("<B1-Motion>")
        self.unbind_all("<ButtonRelease-1>")
        self._save_widths()

    def _apply_widths(self):
        total_w = 0
        for col in self.columns:
            total_w += self.widths[col["key"]]
        self._reposition_header_labels()
        for row in self._rows:
            row["frame"].configure(width=total_w)
            self._layout_row(row)
        self._reposition_handles()
        self._update_header_size()
        self.update_idletasks()
        self._update_scrollregion()

    # ---------------- autofit ----------------
    def _autofit_widths(self, rows_data):
        try:
            base = tkfont.nametofont("TkDefaultFont")
            f = tkfont.Font(font=base, size=8)
        except Exception:
            return
        padding = 2 * self.CELL_PAD_X + 2 * self.BORDER + 6

        for col in self.columns:
            key = col["key"]
            if col.get("wrap", True):
                continue
            max_w = f.measure(col["title"])
            for data in rows_data:
                text = data.get(key)
                if text is None:
                    continue
                text = str(text).split("\n")[0]
                if not text:
                    continue
                w = f.measure(text)
                if w > max_w:
                    max_w = w
            self.widths[key] = max(col["width"], max_w + padding)

    # ---------------- public API ----------------
    def set_rows(self, rows_data, iid_key="id"):
        if self.autofit:
            self._autofit_widths(rows_data)
        for row in self._rows:
            row["frame"].destroy()
        self._rows = []
        self._selected = None
        for data in rows_data:
            self._add_row(data, iid_key)
        if self.autofit:
            self._apply_widths()
        self.update_idletasks()
        self._update_scrollregion()
        bind_mousewheel_recursive(self.body, self.body_canvas)

    def clear_selection(self):
        self._paint_selected(None)

    def select_iid(self, iid):
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
        frame = row["frame"]
        cells = row["cells"]

        # Первичная раскладка: определяем wraplength для каждой ячейки.
        x = 0
        for col in self.columns:
            key = col["key"]
            w = self.widths[key]
            lbl = cells[key]
            wrap_len = max(20, w - 2 * self.CELL_PAD_X - 2 * self.BORDER)
            # Перенос разрешаем либо для колонок с wrap=True,
            # либо для всех колонок, если включён режим wrap_when_narrow.
            if self.wrap_when_narrow or col.get("wrap", True):
                lbl.configure(wraplength=wrap_len)
            else:
                lbl.configure(wraplength=0)
            lbl.place(x=x, y=0, width=w)
            x += w

        # Высота строки = максимум высот ячеек (после автопереноса).
        frame.update_idletasks()
        h = 1
        for col in self.columns:
            h = max(h, cells[col["key"]].winfo_reqheight())

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


# ============== EditableCriteriaList ==============

class EditableCriteriaList(ttk.Frame):
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

    def set_items(self, items):
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
        bind_mousewheel_recursive(self.rows_frame, self.canvas)

    def get_items(self):
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
        bind_mousewheel_recursive(self.rows_frame, self.canvas)
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

    def _add_row_internal(self, n, text, status_name, comment):
        row = {}
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


# ============== SqlFilterDialog ==============

_FORBIDDEN_IN_WHERE = ("ORDER", "GROUP", "HAVING", "UNION", "LIMIT", "OFFSET")
_FORBIDDEN_IN_ORDER = ("WHERE", "GROUP", "HAVING", "UNION", "LIMIT", "OFFSET")


def validate_where_clause(text: str) -> str | None:
    text = (text or "").strip()
    if not text:
        return None
    if ";" in text:
        return "WHERE не должен содержать ';'"
    tokens = text.split()
    if not tokens or tokens[0].upper() != "WHERE":
        return "WHERE должен начинаться со слова WHERE"
    for tok in tokens[1:]:
        if tok.upper() in _FORBIDDEN_IN_WHERE:
            return f"WHERE не должен содержать '{tok}'"
    return None


def validate_order_by_clause(text: str) -> str | None:
    text = (text or "").strip()
    if not text:
        return None
    if ";" in text:
        return "ORDER BY не должен содержать ';'"
    tokens = text.split()
    if len(tokens) < 2:
        return "ORDER BY должен начинаться со слов 'ORDER BY'"
    if tokens[0].upper() != "ORDER" or tokens[1].upper() != "BY":
        return "ORDER BY должен начинаться со слов 'ORDER BY'"
    for tok in tokens[2:]:
        if tok.upper() in _FORBIDDEN_IN_ORDER:
            return f"ORDER BY не должен содержать '{tok}'"
    return None


class SqlFilterDialog(tk.Toplevel):
    def __init__(self, parent, base_sql: str, where_text: str, order_by_text: str,
                 default_order_by: str, validate_sql, on_apply):
        super().__init__(parent)
        self.title("SQL-фильтр")
        self.transient(parent)
        self.grab_set()
        self.resizable(True, True)

        self._base_sql        = base_sql
        self._default_order   = default_order_by or ""
        self._validate_sql    = validate_sql
        self._on_apply_cb     = on_apply

        self._last_checked_where = None
        self._last_checked_order = None

        self._build_ui(where_text or "", order_by_text or "")

        self.update_idletasks()
        w = 900
        h = 720
        self.geometry(f"{w}x{h}")
        px = parent.winfo_rootx() + (parent.winfo_width()  - w) // 2
        py = parent.winfo_rooty() + (parent.winfo_height() - h) // 2
        self.geometry(f"+{max(0, px)}+{max(0, py)}")

        self.protocol("WM_DELETE_WINDOW", self.destroy)

    def _build_ui(self, where_text, order_by_text):
        pad = {"padx": 10, "pady": 4}

        ttk.Label(self, text="Базовый запрос (только для чтения):")\
            .pack(anchor="w", **pad)

        base_wrap = ttk.Frame(self)
        base_wrap.pack(fill="x", padx=10)
        n_lines = self._base_sql.count("\n") + 2
        self.txt_base = tk.Text(base_wrap,
                                height=min(max(n_lines, 4), 20),
                                wrap="word",
                                font=("Consolas", 9), bg="#f5f5f5")
        base_sb = ttk.Scrollbar(base_wrap, orient="vertical",
                                command=self.txt_base.yview)
        self.txt_base.configure(yscrollcommand=base_sb.set)
        self.txt_base.pack(side="left", fill="both", expand=True)
        base_sb.pack(side="right", fill="y")
        self.txt_base.insert("1.0", self._base_sql)
        self.txt_base.configure(state="disabled")

        ttk.Label(self, text="WHERE (необязательно). Оставьте пустым — без WHERE:")\
            .pack(anchor="w", **pad)
        self.txt_where = tk.Text(self, height=14, wrap="word",
                                 font=("Consolas", 9), undo=True)
        self.txt_where.pack(fill="both", expand=True, padx=10)
        if where_text:
            self.txt_where.insert("1.0", where_text)

        ttk.Separator(self, orient="horizontal").pack(fill="x", padx=10, pady=6)

        ttk.Label(self, text="ORDER BY (необязательно). Оставьте пустым — без ORDER BY:")\
            .pack(anchor="w", **pad)
        self.txt_order = tk.Text(self, height=4, wrap="word",
                                 font=("Consolas", 9), undo=True)
        self.txt_order.pack(fill="x", padx=10)
        if order_by_text:
            self.txt_order.insert("1.0", order_by_text)

        self.var_status = tk.StringVar(value="")
        self.lbl_status = tk.Label(self, textvariable=self.var_status,
                                   anchor="w", padx=10, pady=4)
        self.lbl_status.pack(fill="x", padx=10, pady=(6, 0))

        btns = ttk.Frame(self, padding=(10, 8))
        btns.pack(fill="x")
        ttk.Button(btns, text="Проверить", command=self._on_check).pack(side="left")
        self.btn_apply = ttk.Button(btns, text="Применить", command=self._on_apply,
                                    state="disabled")
        self.btn_apply.pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="Очистить", command=self._on_clear).pack(side="left", padx=(8, 0))
        ttk.Button(btns, text="Отмена", command=self.destroy).pack(side="right")

        self.txt_where.bind("<KeyRelease>", self._on_field_change)
        self.txt_order.bind("<KeyRelease>", self._on_field_change)

    @staticmethod
    def _get_text(widget: tk.Text) -> str:
        return widget.get("1.0", "end-1c")

    @staticmethod
    def _set_text(widget: tk.Text, text: str):
        widget.delete("1.0", "end")
        if text:
            widget.insert("1.0", text)

    def _set_status(self, text: str, error: bool = False):
        self.var_status.set(text)
        self.lbl_status.configure(fg=("#a00000" if error else "#404040"))

    def _disable_apply(self):
        self.btn_apply.configure(state="disabled")

    def _enable_apply(self):
        self.btn_apply.configure(state="normal")

    def _build_sql(self, where_text: str, order_text: str) -> str:
        parts = [self._base_sql.rstrip()]
        if where_text:
            parts.append(where_text)
        if order_text:
            parts.append(order_text)
        return "\n".join(parts)

    def _on_field_change(self, _e=None):
        self._disable_apply()
        self._set_status("")

    def _on_check(self):
        where_text = self._get_text(self.txt_where).strip()
        order_text = self._get_text(self.txt_order).strip()

        err = validate_where_clause(where_text)
        if err:
            self._set_status(err, error=True)
            self._disable_apply()
            return

        err = validate_order_by_clause(order_text)
        if err:
            self._set_status(err, error=True)
            self._disable_apply()
            return

        sql = self._build_sql(where_text, order_text)

        try:
            n = self._validate_sql(sql)
        except Exception as e:
            self._set_status(f"Ошибка SQL: {e}", error=True)
            self._disable_apply()
            return

        self._set_status(f"Записей найдено: {n}")
        self._enable_apply()
        self._last_checked_where = where_text
        self._last_checked_order = order_text

    def _on_apply(self):
        where = self._get_text(self.txt_where).strip()
        order = self._get_text(self.txt_order).strip()
        if (where, order) != (self._last_checked_where, self._last_checked_order):
            return
        try:
            self._on_apply_cb(where, order)
        finally:
            self.destroy()

    def _on_clear(self):
        self._set_text(self.txt_where, "")
        self._set_text(self.txt_order, self._default_order)
        self._last_checked_where = None
        self._last_checked_order = None
        self._disable_apply()
        self._set_status("")