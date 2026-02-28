import json
import re
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.request import Request, urlopen

POLICY_PATH = Path(__file__).parent / "data" / "policies.txt"
OLLAMA_URL = "http://localhost:11434/api/generate"
DAY_KEYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

def retrieve_policy_context(query: str, top_n: int = 6) -> str:
    if not POLICY_PATH.exists():
        return ""
    lines = [ln.strip() for ln in POLICY_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]
    q_words = {w for w in re.split(r"\W+", query.lower()) if len(w) > 2}

    scored = []
    for line in lines:
        words = {w for w in re.split(r"\W+", line.lower()) if len(w) > 2}
        score = sum(1 for w in q_words if w in words)
        scored.append((score, line))
    scored.sort(reverse=True)
    return "\n".join([line for score, line in scored[:top_n]])

def fallback_parse_attendance(message: str) -> Dict[str, Any]:
    msg = message.lower()
    days = {k: "A" for k in DAY_KEYS}

    # ranges
    if re.search(r"(mon|monday).*(to|-).*(sat|saturday).*(present|p)", msg):
        for k in ["mon","tue","wed","thu","fri","sat"]:
            days[k] = "P"
    if re.search(r"(mon|monday).*(to|-).*(sun|sunday).*(present|p)", msg):
        for k in DAY_KEYS:
            days[k] = "P"

    # per day keywords
    day_map = {
        "mon": ["mon","monday"], "tue": ["tue","tuesday"], "wed": ["wed","wednesday"],
        "thu": ["thu","thursday"], "fri": ["fri","friday"], "sat": ["sat","saturday"], "sun": ["sun","sunday"]
    }
    for key, tokens in day_map.items():
        for t in tokens:
            if re.search(rf"{t}.*half", msg): days[key] = "H"
            if re.search(rf"{t}.*absent", msg): days[key] = "A"
            if re.search(rf"{t}.*present", msg): days[key] = "P"

    ot_hours = float(re.search(r"ot\s*([0-9]+(\.[0-9]+)?)", msg).group(1)) if re.search(r"ot\s*([0-9]+(\.[0-9]+)?)", msg) else 0.0
    deduction = float(re.search(r"(advance|deduction|fine)\s*([0-9]+(\.[0-9]+)?)", msg).group(2)) if re.search(r"(advance|deduction|fine)\s*([0-9]+(\.[0-9]+)?)", msg) else 0.0
    bonus = float(re.search(r"bonus\s*([0-9]+(\.[0-9]+)?)", msg).group(1)) if re.search(r"bonus\s*([0-9]+(\.[0-9]+)?)", msg) else 0.0

    ot_rate: Optional[float] = None
    m = re.search(r"ot\s*rate\s*([0-9]+(\.[0-9]+)?)", msg)
    if m: ot_rate = float(m.group(1))

    return {"days": days, "otHours": ot_hours, "otRate": ot_rate, "bonus": bonus, "deduction": deduction}

def _ensure_schema(obj: Dict[str, Any]) -> Dict[str, Any]:
    days_in = obj.get("days") or {}
    days = {}
    for k in DAY_KEYS:
        v = str(days_in.get(k, "A")).upper().strip()
        days[k] = v if v in ("P", "A", "H") else "A"

    def num(x, default=0.0):
        try: return float(x)
        except Exception: return float(default)

    ot_rate = obj.get("otRate", None)
    if ot_rate in (None, "", "null"):
        ot_rate = None
    else:
        try: ot_rate = float(ot_rate)
        except Exception: ot_rate = None

    return {
        "days": days,
        "otHours": num(obj.get("otHours", 0.0)),
        "otRate": ot_rate,
        "bonus": num(obj.get("bonus", 0.0)),
        "deduction": num(obj.get("deduction", 0.0)),
    }

def llm_parse_attendance(message: str, model: str = "llama3.1", timeout_s: int = 4) -> Dict[str, Any]:
    context = retrieve_policy_context(message)

    system = (
        "You are a payroll assistant.\n"
        "Return ONLY valid JSON with keys:\n"
        'days: {mon,tue,wed,thu,fri,sat,sun} values must be "P" or "A" or "H"\n'
        "otHours: number\n"
        "otRate: number|null\n"
        "bonus: number\n"
        "deduction: number\n"
        'If not specified, keep absent days as "A", numbers as 0, otRate null.\n'
        "No extra keys. No markdown. No explanations."
    )

    prompt = f"Policy context:\n{context}\n\nUser message:\n{message}\n\nReturn JSON now."

    payload = json.dumps({
        "model": model,
        "prompt": prompt,
        "system": system,
        "stream": False,
        "options": {"temperature": 0}
    }).encode("utf-8")

    req = Request(OLLAMA_URL, data=payload, headers={"Content-Type": "application/json"}, method="POST")
    with urlopen(req, timeout=timeout_s) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    txt = (data.get("response") or "").strip()
    obj = json.loads(txt)
    return _ensure_schema(obj)