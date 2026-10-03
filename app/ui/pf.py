"""Расчёт Priority Factor (PF). Формула перенесена из Google Sheets."""
from datetime import date, datetime


_P1_MAP = {"A": 100, "B": 200, "C": 300, "D": 500, "E": 1000}

# статусы, при которых задача считается завершённой и получает PF = 999
_DONE_STATUSES = {"Passed", "Failed"}


def compute_pf(status_name: str | None,
               p1: str | None,
               p2: int | None,
               deadline_iso: str | None,
               pp: float | None,
               pomodoro_per_day: float = 8.0,
               today: date | None = None) -> float:
    """
    Возвращает PF. Меньше — важнее.
      * Passed/Failed → 999
      * P1=A + близкий дедлайн может дать отрицательные значения
      * P1=пусто → −1000 (задача всплывает наверх, чтобы её приоритизировали)
    """
    if status_name in _DONE_STATUSES:
        return 999.0

    # --- P1 ---
    if p1 is None or p1 == "":
        base = -1000.0
    else:
        base = float(_P1_MAP.get(p1, -1000))

    # --- дедлайн и трудоёмкость ---
    if not deadline_iso:
        dl_adj = 20.0
    else:
        try:
            d = datetime.strptime(deadline_iso, "%Y-%m-%d").date()
        except ValueError:
            dl_adj = 20.0
        else:
            t = today or date.today()
            diff_days = (d - t).days
            pp_val = float(pp) if pp is not None else 0.0
            denom = pomodoro_per_day if pomodoro_per_day > 0 else 8.0
            remaining = diff_days - (pp_val / denom)
            if remaining < 0:
                dl_adj = -200.0
            elif remaining == 0:
                dl_adj = -100.0
            elif remaining <= 2:
                dl_adj = -50.0
            elif remaining <= 7:
                dl_adj = -25.0
            else:
                dl_adj = 0.0

    # --- P2 ---
    if p2 is None:
        p2_adj = 0.0
    else:
        try:
            p2_val = int(p2)
        except (ValueError, TypeError):
            p2_adj = 0.0
        else:
            p2_adj = -1000.0 / p2_val if p2_val > 0 else 0.0

    return round(base + dl_adj + p2_adj, 2)