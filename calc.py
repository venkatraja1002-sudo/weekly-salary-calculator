from typing import Dict, Literal, Optional, TypedDict

DayVal = Literal["P", "A", "H"]

class CalcResult(TypedDict):
    days: Dict[str, DayVal]
    presentDays: int
    halfDays: int
    base: float
    overtime: float
    otRate: float
    bonus: float
    deduction: float
    total: float

DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

def normalize_days(days: Dict[str, str] | None) -> Dict[str, DayVal]:
    days = days or {}
    out: Dict[str, DayVal] = {}
    for k in DAY_KEYS:
        v = str(days.get(k, "A")).upper().strip()
        out[k] = v if v in ("P", "A", "H") else "A"
    return out

def calc_weekly_salary(
    daily_rate: float,
    days: Dict[str, str] | None,
    ot_hours: float = 0.0,
    ot_rate: Optional[float] = None,
    bonus: float = 0.0,
    deduction: float = 0.0
) -> CalcResult:
    rate = float(daily_rate or 0.0)
    d = normalize_days(days)

    present = sum(1 for v in d.values() if v == "P")
    half = sum(1 for v in d.values() if v == "H")

    ot_h = float(ot_hours or 0.0)
    b = float(bonus or 0.0)
    ded = float(deduction or 0.0)

    effective_ot_rate = float(ot_rate) if ot_rate not in (None, "") else (rate / 8.0 if rate else 0.0)

    base = (present * rate) + (half * 0.5 * rate)
    overtime = ot_h * effective_ot_rate
    total = max(0.0, base + overtime + b - ded)

    return {
        "days": d,
        "presentDays": present,
        "halfDays": half,
        "base": base,
        "overtime": overtime,
        "otRate": effective_ot_rate,
        "bonus": b,
        "deduction": ded,
        "total": total
    }