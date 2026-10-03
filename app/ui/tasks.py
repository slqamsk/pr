"""Вкладка работы с задачами."""
import tkinter as tk
from tkinter import ttk, messagebox
import sqlite3
from datetime import datetime

from db import db
from ui.widgets import CalendarPopup, ScrollableTable, ask_unsaved_changes
from ui.pf import compute_pf

COLUMNS = [
    {"key": "pf",           "title": "PF",         "width": 70,  "wrap": False},
    {"key": "name",         "title": "Task Name",  "width": 260, "wrap": True},
    {"key": "epic_name",    "title": "Epic",       "width": 160, "wrap": True},
    {"key": "role_name",    "title": "Роль",       "width": 150, "wrap": True},
    {"key": "subrole_name", "title": "Подроль",    "width": 150, "wrap": True},
    {"key": "deadline",     "title": "Дедлайн",    "width": 100, "wrap": False},
    {"key": "p1",           "title": "P1",         "width": 50,  "wrap": False},
    {"key": "p2",           "title": "P2",         "width": 50,  "wrap": False},
    {"key": "pp",           "title": "PP",         "width": 50,  "wrap": False},
    {"key": "status_name",  "title": "Статус",     "width": 90,  "wrap": False},
    {"key": "macro_code",   "title": "Macro",      "width": 90,  "wrap": False},
    {"key": "sprint_code",  "title": "Sprint",     "width": 90,  "wrap": False},
    {"key": "comment",      "title": "Комментарий","width": 220, "wrap": True},
]


def _to_iso(s: str) -> str:
    return datetime.strptime(s.strip(), "%d.%m.%Y").strftime("%Y-%m-%d")


def _to_ru(iso: str) -> str:
    return datetime.strptime(iso, "%Y-%m-%d").strftime("%d.%m.%Y")


def _role_display(rid: int, name: str) -> str:
    return f"{rid}. {name}"


class TasksTab(ttk.Frame):
    def __init__(self, parent, on_make_action=None):
        super().__init__(parent, padding=8)
        self.current_id: int | None = None
        self._raw_by_id: dict[int, dict] = {}
        self._snapshot: dict | None = None
        self.on_make_action = on_make_action

        self._statuses: list[dict] = []
        self._status_by_name: dict[str, int] = {}
        self._p1_levels: list[str] = []

        self._roles_by_display: dict[str, int] = {}
        self._subrole_display_to_id: dict[str, int] = {}

        self._epics_by_name: dict[str, dict] = {}
        self._macros_by_code: dict[str, int] = {}
        self._sprints_by_code: dict[str, dict] = {}

        self._pf_pomodoro = 8.0

        self._build_ui()
        self.refresh()
        self._set_snapshot()

    # ---------- UI ----------
    def _build_ui(self):
        self._statuses = db.list_statuses()
        self._status_by_name = {s["name"]: s["id"] for s in self._statuses}
        self._p1_levels = [p["name"] for p in db.list_p1_levels()]

        # ---- Нижний ряд кнопок (создаём, но упакуем в конце) ----
        btns = ttk.Frame(self, padding=(0, 8, 0, 0))
        ttk.Button(btns, text="Новая",     command=self._new).pack(side="left")
        ttk.Button(btns, text="Сохранить", command=self._on_save_clicked).pack(side="left", padx=6)
        ttk.Button(btns, text="Удалить",   command=self._delete).pack(side="left")
        ttk.Button(btns, text="Обновить",  command=self._on_refresh_clicked).pack(side="right")

        # ---- Основная форма (2 колонки × 2 ряда) ----
        body = ttk.Frame(self)
        body.columnconfigure(0, weight=1, uniform="f")
        body.columnconfigure(1, weight=1, uniform="f")

        # --- Основное ---
        grp_main = ttk.LabelFrame(body, text="Основное", padding=6)
        grp_main.grid(row=0, column=0, sticky="nsew", padx=(0, 4), pady=(0, 4))
        grp_main.columnconfigure(1, weight=1)

        self.var_name = tk.StringVar()
        ttk.Label(grp_main, text="Name").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(grp_main, textvariable=self.var_name)\
            .grid(row=0, column=1, sticky="ew", pady=2)

        ttk.Label(grp_main, text="Description").grid(row=1, column=0, sticky="nw",
                                                     padx=(0, 8), pady=2)
        desc_wrap = ttk.Frame(grp_main)
        desc_wrap.grid(row=1, column=1, sticky="ew", pady=2)
        desc_wrap.columnconfigure(0, weight=1)
        self.txt_desc = tk.Text(desc_wrap, height=2, wrap="word",
                                font=("TkDefaultFont", 9), undo=True)
        self.txt_desc.grid(row=0, column=0, sticky="ew")
        dsb = ttk.Scrollbar(desc_wrap, orient="vertical", command=self.txt_desc.yview)
        self.txt_desc.configure(yscrollcommand=dsb.set)
        dsb.grid(row=0, column=1, sticky="ns")

        # --- Сроки и вес ---
        grp_time = ttk.LabelFrame(body, text="Сроки и вес", padding=6)
        grp_time.grid(row=0, column=1, sticky="nsew", padx=(4, 0), pady=(0, 4))
        grp_time.columnconfigure(1, weight=1)

        self.var_deadline = tk.StringVar()
        ttk.Label(grp_time, text="Дедлайн").grid(row=0, column=0, sticky="w",
                                                 padx=(0, 8), pady=2)
        f_dl = ttk.Frame(grp_time)
        f_dl.grid(row=0, column=1, sticky="w", pady=2)
        ttk.Entry(f_dl, textvariable=self.var_deadline, width=14).pack(side="left")
        ttk.Button(f_dl, text="📅", width=3,
                   command=lambda: self._open_cal(self.var_deadline)).pack(side="left", padx=(4, 0))
        ttk.Button(f_dl, text="✕", width=3,
                   command=lambda: self.var_deadline.set("")).pack(side="left", padx=(4, 0))

        self.var_pp = tk.StringVar()
        ttk.Label(grp_time, text="PP").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(grp_time, textvariable=self.var_pp, width=10)\
            .grid(row=1, column=1, sticky="w", pady=2)

        self.var_p1 = tk.StringVar()
        ttk.Label(grp_time, text="P1").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=2)
        self.cmb_p1 = ttk.Combobox(grp_time, textvariable=self.var_p1,
                                   values=[""] + self._p1_levels,
                                   state="readonly", width=8)
        self.cmb_p1.grid(row=2, column=1, sticky="w", pady=2)

        self.var_p2 = tk.StringVar()
        ttk.Label(grp_time, text="P2").grid(row=3, column=0, sticky="w", padx=(0, 8), pady=2)
        ttk.Entry(grp_time, textvariable=self.var_p2, width=10)\
            .grid(row=3, column=1, sticky="w", pady=2)

        self.var_pf_display = tk.StringVar()
        ttk.Label(grp_time, text="PF").grid(row=4, column=0, sticky="w", padx=(0, 8), pady=2)
        pf_lbl = ttk.Label(grp_time, textvariable=self.var_pf_display,
                           foreground="#004080", font=("TkDefaultFont", 10, "bold"))
        pf_lbl.grid(row=4, column=1, sticky="w", pady=2)

        # Кнопка «Делать» — справа по центру группы
        ttk.Button(grp_time, text="Делать", command=self._on_do_clicked)\
            .grid(row=0, column=2, rowspan=5, sticky="e", padx=(12, 0), pady=2)

        # --- Привязки ---
        grp_links = ttk.LabelFrame(body, text="Привязки", padding=6)
        grp_links.grid(row=1, column=0, sticky="nsew", padx=(0, 4), pady=(4, 0))
        grp_links.columnconfigure(1, weight=1)

        self.var_epic   = tk.StringVar()
        self.var_role   = tk.StringVar()
        self.var_subrole = tk.StringVar()
        self.var_macro  = tk.StringVar()
        self.var_sprint = tk.StringVar()

        ttk.Label(grp_links, text="Эпик").grid(row=0, column=0, sticky="w",
                                               padx=(0, 8), pady=2)
        self.cmb_epic = ttk.Combobox(grp_links, textvariable=self.var_epic,
                                     values=[""], state="readonly", width=32)
        self.cmb_epic.grid(row=0, column=1, sticky="w", pady=2)
        self.cmb_epic.bind("<<ComboboxSelected>>", self._on_epic_changed)

        ttk.Label(grp_links, text="Роль").grid(row=1, column=0, sticky="w",
                                               padx=(0, 8), pady=2)
        self.cmb_role = ttk.Combobox(grp_links, textvariable=self.var_role,
                                     values=[], state="readonly", width=32)
        self.cmb_role.grid(row=1, column=1, sticky="w", pady=2)
        self.cmb_role.bind("<<ComboboxSelected>>", self._on_role_selected)

        ttk.Label(grp_links, text="Подроль").grid(row=2, column=0, sticky="w",
                                                  padx=(0, 8), pady=2)
        self.cmb_subrole = ttk.Combobox(grp_links, textvariable=self.var_subrole,
                                        values=[], state="disabled", width=32)
        self.cmb_subrole.grid(row=2, column=1, sticky="w", pady=2)

        ttk.Label(grp_links, text="Macro").grid(row=3, column=0, sticky="w",
                                                padx=(0, 8), pady=2)
        self.cmb_macro = ttk.Combobox(grp_links, textvariable=self.var_macro,
                                      values=[""], state="readonly", width=32)
        self.cmb_macro.grid(row=3, column=1, sticky="w", pady=2)
        self.cmb_macro.bind("<<ComboboxSelected>>", self._on_macro_changed)

        ttk.Label(grp_links, text="Sprint").grid(row=4, column=0, sticky="w",
                                                 padx=(0, 8), pady=2)
        self.cmb_sprint = ttk.Combobox(grp_links, textvariable=self.var_sprint,
                                       values=[""], state="disabled", width=32)
        self.cmb_sprint.grid(row=4, column=1, sticky="w", pady=2)

        # --- Прочее ---
        grp_other = ttk.LabelFrame(body, text="Прочее", padding=6)
        grp_other.grid(row=1, column=1, sticky="nsew", padx=(4, 0), pady=(4, 0))
        grp_other.columnconfigure(1, weight=1)

        self.var_status = tk.StringVar()
        ttk.Label(grp_other, text="Статус").grid(row=0, column=0, sticky="w",
                                                 padx=(0, 8), pady=2)
        self.cmb_status = ttk.Combobox(grp_other, textvariable=self.var_status,
                                       values=[s["name"] for s in self._statuses],
                                       state="readonly", width=12)
        self.cmb_status.grid(row=0, column=1, sticky="w", pady=2)

        ttk.Label(grp_other, text="Комментарий").grid(row=1, column=0, sticky="nw",
                                                      padx=(0, 8), pady=2)
        cmt_wrap = ttk.Frame(grp_other)
        cmt_wrap.grid(row=1, column=1, sticky="ew", pady=2)
        cmt_wrap.columnconfigure(0, weight=1)
        self.txt_comment = tk.Text(cmt_wrap, height=2, wrap="word",
                                   font=("TkDefaultFont", 9), undo=True)
        self.txt_comment.grid(row=0, column=0, sticky="ew")
        csb = ttk.Scrollbar(cmt_wrap, orient="vertical", command=self.txt_comment.yview)
        self.txt_comment.configure(yscrollcommand=csb.set)
        csb.grid(row=0, column=1, sticky="ns")

        # ---- Таблица ----
        self.table = ScrollableTable(self, COLUMNS, on_select=self._on_table_select,
                                     settings_key="ui.columns.tasks")

        # ---- Упаковка: снизу вверх ----
        btns.pack(side="bottom", fill="x")
        body.pack(side="bottom", fill="x", pady=(8, 0))
        self.table.pack(side="top", fill="both", expand=True)

        # ---- Пересчёт PF на лету ----
        for v in (self.var_p1, self.var_p2, self.var_deadline,
                  self.var_pp, self.var_status):
            v.trace_add("write", lambda *_: self._recompute_pf())

    # ---------- PF ----------
    def _recompute_pf(self):
        p1 = self.var_p1.get().strip() or None
        p2_text = self.var_p2.get().strip()
        p2 = None
        if p2_text:
            try:
                p2 = int(p2_text)
            except ValueError:
                p2 = None
        deadline_text = self.var_deadline.get().strip()
        deadline_iso = None
        if deadline_text:
            try:
                deadline_iso = _to_iso(deadline_text)
            except ValueError:
                deadline_iso = None
        pp_text = self.var_pp.get().strip()
        pp = None
        if pp_text:
            try:
                pp = float(pp_text.replace(",", "."))
            except ValueError:
                pp = None
        status = self.var_status.get().strip() or None

        pf = compute_pf(status, p1, p2, deadline_iso, pp,
                        pomodoro_per_day=self._pf_pomodoro)
        self.var_pf_display.set(f"{pf:.2f}")

    # ---------- комбобоксы ----------
    def _refresh_role_combo(self):
        roles = db.list_roles()
        self._roles_by_display = {_role_display(r["id"], r["name"]): r["id"] for r in roles}
        self.cmb_role.configure(values=[""] + list(self._roles_by_display.keys()))

    def _refresh_epic_combo(self):
        brief = db.list_epics_brief()
        self._epics_by_name = {e["name"]: e for e in brief}
        self.cmb_epic.configure(values=[""] + list(self._epics_by_name.keys()))

    def _refresh_macro_combo(self):
        brief = db.list_macro_sprints_brief()
        self._macros_by_code = {m["code"]: m["id"] for m in brief}
        self.cmb_macro.configure(values=[""] + list(self._macros_by_code.keys()))

    def _refresh_sprint_combo(self, macro_id: int | None):
        brief = db.list_sprints_brief()
        if macro_id is None:
            sprints = brief
        else:
            sprints = [s for s in brief if s["macro_sprint_id"] == macro_id]
        self._sprints_by_code = {s["code"]: s for s in sprints}
        self.cmb_sprint.configure(values=[""] + list(self._sprints_by_code.keys()))

    def _refresh_subrole_combo(self, role_id: int | None, keep_value: bool = False):
        if role_id is None:
            self._subrole_display_to_id = {}
            self.cmb_subrole.configure(values=[], state="disabled")
            if not keep_value:
                self.var_subrole.set("")
            return
        subs = db.list_subroles_by_role(role_id)
        self._subrole_display_to_id = {s["name"]: s["id"] for s in subs}
        self.cmb_subrole.configure(values=[""] + list(self._subrole_display_to_id.keys()),
                                   state="readonly")
        if not keep_value:
            self.var_subrole.set("")

    # ---------- обработчики комбобоксов ----------
    def _on_epic_changed(self, _e=None):
        epic_name = self.var_epic.get().strip()
        if not epic_name:
            self.cmb_role.configure(state="readonly")
            self.cmb_subrole.configure(state="readonly" if self.var_role.get() else "disabled")
            self.cmb_macro.configure(state="readonly")
            self._refresh_sprint_combo(self._macros_by_code.get(self.var_macro.get().strip()))
            self.cmb_sprint.configure(state="readonly" if self.var_macro.get().strip() else "disabled")
            self._recompute_pf()
            return

        epic = self._epics_by_name.get(epic_name)
        if not epic:
            return

        if epic["role_id"] is not None:
            role_id = epic["role_id"]
            disp = None
            for d, rid in self._roles_by_display.items():
                if rid == role_id:
                    disp = d
                    break
            self.var_role.set(disp or "")
        else:
            self.var_role.set("")

        if epic["subrole_id"] is not None:
            subs = db.list_subroles_by_role(epic["role_id"]) if epic["role_id"] is not None else []
            name = next((s["name"] for s in subs if s["id"] == epic["subrole_id"]), "")
            self._subrole_display_to_id = {s["name"]: s["id"] for s in subs}
            self.cmb_subrole.configure(values=[""] + list(self._subrole_display_to_id.keys()),
                                       state="readonly")
            self.var_subrole.set(name)
        else:
            self.var_subrole.set("")
            self._refresh_subrole_combo(epic["role_id"], keep_value=True)

        if epic["macro_sprint_id"] is not None:
            code = None
            for c, mid in self._macros_by_code.items():
                if mid == epic["macro_sprint_id"]:
                    code = c
                    break
            self.var_macro.set(code or "")
            self._refresh_sprint_combo(epic["macro_sprint_id"])
        else:
            self.var_macro.set("")
            self._refresh_sprint_combo(None)

        self.cmb_role.configure(state="disabled")
        self.cmb_subrole.configure(state="disabled")
        self.cmb_macro.configure(state="disabled")
        self.var_sprint.set("")
        if epic["macro_sprint_id"] is not None:
            self.cmb_sprint.configure(state="readonly")
        else:
            self.cmb_sprint.configure(state="disabled")

        self._recompute_pf()

    def _on_role_selected(self, _e=None):
        if self.var_epic.get().strip():
            return
        role_display = self.var_role.get().strip()
        role_id = self._roles_by_display.get(role_display) if role_display else None
        self._refresh_subrole_combo(role_id, keep_value=False)

    def _on_macro_changed(self, _e=None):
        if self.var_epic.get().strip():
            return
        macro_code = self.var_macro.get().strip()
        if not macro_code:
            self._refresh_sprint_combo(None)
            self.cmb_sprint.configure(state="disabled")
            self.var_sprint.set("")
            self._recompute_pf()
            return
        macro_id = self._macros_by_code.get(macro_code)
        self._refresh_sprint_combo(macro_id)
        self.cmb_sprint.configure(state="readonly")
        self.var_sprint.set("")
        self._recompute_pf()

    # ---------- снимок ----------
    def _form_state(self) -> dict:
        return {
            "name":        self.var_name.get().strip(),
            "description": self._get_desc(),
            "epic":        self.var_epic.get().strip(),
            "role":        self.var_role.get().strip(),
            "subrole":     self.var_subrole.get().strip(),
            "macro":       self.var_macro.get().strip(),
            "sprint":      self.var_sprint.get().strip(),
            "deadline":    self.var_deadline.get().strip(),
            "pp":          self.var_pp.get().strip(),
            "p1":          self.var_p1.get().strip(),
            "p2":          self.var_p2.get().strip(),
            "status":      self.var_status.get(),
            "comment":     self._get_comment(),
        }

    def _set_snapshot(self):
        self._snapshot = self._form_state()

    def _is_dirty(self) -> bool:
        if self._snapshot is None:
            return False
        return self._form_state() != self._snapshot

    def has_unsaved(self) -> bool:
        return self._is_dirty()

    def confirm_leave(self) -> bool:
        if not self._is_dirty():
            return True
        action = ask_unsaved_changes(parent=self.winfo_toplevel())
        if action == "cancel":
            return False
        if action == "save":
            return self._save()
        return True

    # ---------- данные ----------
    def refresh(self):
        self._pf_pomodoro = db.get_pomodoro_per_day()
        self._refresh_role_combo()
        self._refresh_epic_combo()
        self._refresh_macro_combo()

        raw = db.list_tasks()
        self._raw_by_id = {r["id"]: r for r in raw}

        display = []
        for r in raw:
            pf = compute_pf(
                r["status_name"], r["p1"], r["p2"], r["deadline"], r["pp"],
                pomodoro_per_day=self._pf_pomodoro,
            )
            display.append({
                "id":           r["id"],
                "pf":           f"{pf:.2f}",
                "_pf":          pf,
                "name":         r["name"],
                "epic_name":    r["epic_name"] or "",
                "role_name":    (_role_display(r["role_id"], r["role_name"])
                                 if r["role_id"] else ""),
                "subrole_name": r["subrole_name"] or "",
                "deadline":     _to_ru(r["deadline"]) if r["deadline"] else "",
                "p1":           r["p1"] or "",
                "p2":           "" if r["p2"] is None else r["p2"],
                "pp":           "" if r["pp"] is None else f"{r['pp']:.1f}",
                "status_name":  r["status_name"],
                "macro_code":   r["macro_code"] or "",
                "sprint_code":  r["sprint_code"] or "",
                "comment":      r["comment"] or "",
            })
        display.sort(key=lambda d: (d["_pf"], d["name"]))
        self.table.set_rows(display, iid_key="id")
        if self.current_id is not None:
            self.table.select_iid(str(self.current_id))

    def _load_into_form(self, tid: int):
        self.current_id = tid
        src = self._raw_by_id.get(tid)
        if not src:
            return

        self.var_name.set(src["name"])
        self._set_desc(src["description"] or "")
        self._set_comment(src["comment"] or "")

        self.var_epic.set(src["epic_name"] or "")

        if src["role_id"] is not None and src["role_name"]:
            self.var_role.set(_role_display(src["role_id"], src["role_name"]))
        else:
            self.var_role.set("")
        if src["role_id"] is not None:
            subs = db.list_subroles_by_role(src["role_id"])
            self._subrole_display_to_id = {s["name"]: s["id"] for s in subs}
            self.cmb_subrole.configure(values=[""] + list(self._subrole_display_to_id.keys()),
                                       state="readonly")
        else:
            self._subrole_display_to_id = {}
            self.cmb_subrole.configure(values=[], state="disabled")
        self.var_subrole.set(src["subrole_name"] or "")

        self.var_macro.set(src["macro_code"] or "")
        if src["macro_sprint_id"] is not None:
            brief = db.list_sprints_brief()
            sprints = [s for s in brief if s["macro_sprint_id"] == src["macro_sprint_id"]]
            self._sprints_by_code = {s["code"]: s for s in sprints}
            self.cmb_sprint.configure(values=[""] + list(self._sprints_by_code.keys()),
                                      state="readonly")
        else:
            self._sprints_by_code = {}
            self.cmb_sprint.configure(values=[""], state="disabled")
        self.var_sprint.set(src["sprint_code"] or "")

        self.var_deadline.set(_to_ru(src["deadline"]) if src["deadline"] else "")
        self.var_pp.set("" if src["pp"] is None else f"{src['pp']:.1f}")
        self.var_p1.set(src["p1"] or "")
        self.var_p2.set("" if src["p2"] is None else str(src["p2"]))
        self.var_status.set(src["status_name"])

        if src["epic_id"] is not None:
            self.cmb_role.configure(state="disabled")
            self.cmb_subrole.configure(state="disabled")
            self.cmb_macro.configure(state="disabled")
            self.cmb_sprint.configure(state="readonly" if src["macro_sprint_id"] is not None
                                      else "disabled")
        else:
            self.cmb_role.configure(state="readonly")
            self.cmb_subrole.configure(state="readonly" if src["role_id"] is not None
                                       else "disabled")
            self.cmb_macro.configure(state="readonly")
            self.cmb_sprint.configure(state="readonly" if src["macro_sprint_id"] is not None
                                      else "disabled")

        self._recompute_pf()
        self._set_snapshot()
        self.table.select_iid(str(tid))

    def _set_desc(self, text):
        self.txt_desc.delete("1.0", "end")
        self.txt_desc.insert("1.0", text or "")

    def _get_desc(self):
        return self.txt_desc.get("1.0", "end-1c")

    def _set_comment(self, text):
        self.txt_comment.delete("1.0", "end")
        self.txt_comment.insert("1.0", text or "")

    def _get_comment(self):
        return self.txt_comment.get("1.0", "end-1c")

    def _clear_form(self):
        self.current_id = None
        self.var_name.set("")
        self._set_desc("")
        self.var_epic.set("")
        self.var_role.set("")
        self._subrole_display_to_id = {}
        self.cmb_subrole.configure(values=[], state="disabled")
        self.var_subrole.set("")
        self.var_macro.set("")
        self._sprints_by_code = {}
        self.cmb_sprint.configure(values=[""], state="disabled")
        self.var_sprint.set("")
        self.var_deadline.set("")
        self.var_pp.set("")
        self.var_p1.set("")
        self.var_p2.set("")
        self.var_status.set(self._statuses[0]["name"] if self._statuses else "")
        self._set_comment("")

        self.cmb_role.configure(state="readonly")
        self.cmb_macro.configure(state="readonly")

        self.table.clear_selection()
        self._recompute_pf()
        self._set_snapshot()

    # ---------- выбор в таблице ----------
    def _on_table_select(self, data):
        new_id = data["id"]
        if new_id == self.current_id:
            return
        if self._is_dirty():
            action = ask_unsaved_changes(parent=self.winfo_toplevel())
            if action == "cancel":
                self._restore_selection()
                return
            if action == "save":
                if not self._save():
                    self._restore_selection()
                    return
        self._load_into_form(new_id)

    def _restore_selection(self):
        if self.current_id is None:
            self.table.clear_selection()
        else:
            self.table.select_iid(str(self.current_id))

    # ---------- кнопки ----------
    def _new(self):
        if self._is_dirty():
            action = ask_unsaved_changes(parent=self.winfo_toplevel())
            if action == "cancel":
                return
            if action == "save":
                if not self._save():
                    return
        self._clear_form()

    def _on_save_clicked(self):
        self._save()

    def _save(self) -> bool:
        name = self.var_name.get().strip()
        if not name:
            messagebox.showwarning("Валидация", "Task Name не может быть пустым.",
                                   parent=self.winfo_toplevel())
            return False

        epic_name = self.var_epic.get().strip()
        epic_id = None
        epic_row = None
        if epic_name:
            epic_row = self._epics_by_name.get(epic_name)
            if epic_row is None:
                messagebox.showwarning("Валидация",
                                       f"Эпик '{epic_name}' не найден.",
                                       parent=self.winfo_toplevel())
                return False
            epic_id = epic_row["id"]

        if epic_row is not None:
            role_id    = epic_row["role_id"]
            subrole_id = epic_row["subrole_id"]
            macro_id   = epic_row["macro_sprint_id"]
        else:
            role_display = self.var_role.get().strip()
            role_id = self._roles_by_display.get(role_display) if role_display else None
            if role_display and role_id is None:
                messagebox.showwarning("Валидация",
                                       f"Роль '{role_display}' не найдена.",
                                       parent=self.winfo_toplevel())
                return False

            subrole_display = self.var_subrole.get().strip()
            subrole_id = None
            if subrole_display:
                if role_id is None:
                    messagebox.showwarning("Валидация",
                                           "Нельзя выбрать подроль без роли.",
                                           parent=self.winfo_toplevel())
                    return False
                subrole_id = self._subrole_display_to_id.get(subrole_display)
                if subrole_id is None:
                    messagebox.showwarning("Валидация",
                                           f"Подроль '{subrole_display}' не найдена.",
                                           parent=self.winfo_toplevel())
                    return False

            macro_code = self.var_macro.get().strip()
            macro_id = None
            if macro_code:
                macro_id = self._macros_by_code.get(macro_code)
                if macro_id is None:
                    messagebox.showwarning("Валидация",
                                           f"Макро-спринт '{macro_code}' не найден.",
                                           parent=self.winfo_toplevel())
                    return False

        sprint_code = self.var_sprint.get().strip()
        sprint_id = None
        if sprint_code:
            if macro_id is None:
                messagebox.showwarning("Валидация",
                                       "Нельзя выбрать спринт без макро-спринта.",
                                       parent=self.winfo_toplevel())
                return False
            sp = self._sprints_by_code.get(sprint_code)
            if sp is None:
                messagebox.showwarning("Валидация",
                                       f"Спринт '{sprint_code}' не найден.",
                                       parent=self.winfo_toplevel())
                return False
            if sp["macro_sprint_id"] != macro_id:
                messagebox.showwarning("Валидация",
                                       "Спринт не относится к выбранному макро-спринту.",
                                       parent=self.winfo_toplevel())
                return False
            sprint_id = sp["id"]

        dl_text = self.var_deadline.get().strip()
        if dl_text:
            try:
                deadline = _to_iso(dl_text)
            except ValueError:
                messagebox.showwarning("Валидация",
                                       "Дедлайн должен быть в формате ДД.ММ.ГГГГ.",
                                       parent=self.winfo_toplevel())
                return False
        else:
            deadline = None

        pp_text = self.var_pp.get().strip().replace(",", ".")
        if pp_text:
            try:
                pp = float(pp_text)
            except ValueError:
                messagebox.showwarning("Валидация", "PP должен быть числом.",
                                       parent=self.winfo_toplevel())
                return False
        else:
            pp = None

        p1 = self.var_p1.get().strip() or None
        if p1 is not None and p1 not in self._p1_levels:
            messagebox.showwarning("Валидация", f"P1 '{p1}' не из справочника.",
                                   parent=self.winfo_toplevel())
            return False

        p2_text = self.var_p2.get().strip()
        if p2_text:
            try:
                p2 = int(p2_text)
            except ValueError:
                messagebox.showwarning("Валидация", "P2 должен быть целым числом.",
                                       parent=self.winfo_toplevel())
                return False
            if p2 <= 0:
                messagebox.showwarning("Валидация",
                                       "P2 должен быть положительным числом.",
                                       parent=self.winfo_toplevel())
                return False
        else:
            p2 = None

        status_id = self._status_by_name.get(self.var_status.get())
        if status_id is None:
            messagebox.showwarning("Валидация", "Выберите статус.",
                                   parent=self.winfo_toplevel())
            return False

        description = self._get_desc() or None
        comment = self._get_comment() or None

        try:
            if self.current_id is None:
                new_id = db.insert_task(
                    name, description, epic_id, role_id, subrole_id,
                    p1, p2, deadline, pp, status_id,
                    macro_id, sprint_id, comment,
                )
                self.current_id = new_id
            else:
                db.update_task(
                    self.current_id, name, description, epic_id, role_id, subrole_id,
                    p1, p2, deadline, pp, status_id,
                    macro_id, sprint_id, comment,
                )
        except sqlite3.IntegrityError as e:
            msg = str(e)
            if "tasks.name" in msg or "UNIQUE" in msg.upper():
                messagebox.showwarning("Валидация",
                                       f"Task Name «{name}» уже используется.",
                                       parent=self.winfo_toplevel())
            else:
                messagebox.showwarning("Валидация", msg,
                                       parent=self.winfo_toplevel())
            return False

        self._set_snapshot()
        self.refresh()
        if self.current_id is not None:
            self.table.select_iid(str(self.current_id))
        return True

    def _delete(self):
        if self.current_id is None:
            messagebox.showinfo("Удаление", "Выбери запись из списка.",
                                parent=self.winfo_toplevel())
            return
        name = self.var_name.get().strip()

        n_actions = db.count_actions_using_task(self.current_id)
        if n_actions > 0:
            messagebox.showwarning(
                "Удаление запрещено",
                f"Задача «{name}» используется в {n_actions} действиях.\n\n"
                "Сначала отвяжите или удалите эти действия на вкладке «Действия».",
                parent=self.winfo_toplevel(),
            )
            return

        if not messagebox.askyesno("Удаление", f"Удалить задачу «{name}»?",
                                   parent=self.winfo_toplevel()):
            return
        db.delete_task(self.current_id)
        self._clear_form()
        self.refresh()

    def _on_refresh_clicked(self):
        if self._is_dirty():
            action = ask_unsaved_changes(parent=self.winfo_toplevel())
            if action == "cancel":
                return
            if action == "save":
                if not self._save():
                    return
        self.refresh()

    # ---------- workflow: Делать ----------
    def _on_do_clicked(self):
        if self.current_id is None:
            messagebox.showinfo("Делать",
                                "Выбери задачу из списка.",
                                parent=self.winfo_toplevel())
            return
        if self._is_dirty():
            action = ask_unsaved_changes(parent=self.winfo_toplevel())
            if action == "cancel":
                return
            if action == "save":
                if not self._save():
                    return
        task = self._raw_by_id.get(self.current_id)
        if task is None:
            return
        if self.on_make_action is None:
            return
        self.on_make_action(task)

    # ---------- календарь ----------
    def _open_cal(self, var: tk.StringVar):
        initial = None
        try:
            initial = datetime.strptime(var.get().strip(), "%d.%m.%Y").date()
        except (ValueError, AttributeError):
            pass
        popup = CalendarPopup(
            self,
            initial=initial,
            on_pick=lambda d: var.set(d.strftime("%d.%m.%Y")),
        )
        popup.geometry(f"+{self.winfo_pointerx()}+{self.winfo_pointery()}")