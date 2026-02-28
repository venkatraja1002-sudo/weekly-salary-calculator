import json
from datetime import date, datetime, timedelta
from uuid import uuid4

import streamlit as st

from db import init_db, list_workers, add_worker, delete_worker, upsert_week, list_weeks
from calc import calc_weekly_salary, DAY_KEYS
from llm import fallback_parse_attendance, llm_parse_attendance, retrieve_policy_context

st.set_page_config(page_title="Weekly Salary Calculator", layout="wide")
init_db()

def monday_of_week(d: date) -> date:
    return d - timedelta(days=(d.weekday()))  # Monday=0

def default_days():
    return {k: "A" for k in DAY_KEYS}

# --- Sidebar ---
st.sidebar.title("Weekly Salary App")
page = st.sidebar.radio("Go to", ["Workers", "Week Entry", "Policy Q&A"])

# --- Load workers ---
workers = list_workers()
worker_map = {w["name"]: w for w in workers}

# ========== WORKERS PAGE ==========
if page == "Workers":
    st.title("Workers")

    with st.form("add_worker_form", clear_on_submit=True):
        c1, c2, c3, c4 = st.columns([3,3,2,2])
        name = c1.text_input("Name")
        phone = c2.text_input("Phone (optional)")
        daily_rate = c3.number_input("Daily Rate (₹)", min_value=1.0, value=700.0, step=10.0)
        submitted = c4.form_submit_button("Add Worker")

        if submitted:
            if not name.strip():
                st.error("Name is required")
            else:
                wid = f"w_{uuid4().hex[:12]}"
                add_worker(wid, name.strip(), phone.strip(), float(daily_rate))
                st.success("Worker added. Refreshing...")
                st.rerun()

    st.subheader("Worker List")
    if not workers:
        st.info("No workers yet.")
    else:
        for w in workers:
            col1, col2, col3, col4 = st.columns([3,2,2,1])
            col1.write(f"**{w['name']}**  \n₹{w['dailyRate']}/day")
            col2.write(w["phone"] if w["phone"] else "—")
            col3.code(w["id"], language="text")
            if col4.button("Delete", key=f"del_{w['id']}"):
                delete_worker(w["id"])
                st.warning("Worker deleted. Refreshing...")
                st.rerun()

# ========== WEEK ENTRY PAGE ==========
elif page == "Week Entry":
    st.title("Week Entry")

    if not workers:
        st.warning("Add at least one worker first.")
        st.stop()

    # Select worker
    worker_name = st.selectbox("Select Worker", list(worker_map.keys()))
    worker = worker_map[worker_name]
    daily_rate = float(worker["dailyRate"])

    # Week start
    week_start = st.date_input("Week Start (Monday)", value=monday_of_week(date.today()))
    week_start_str = week_start.isoformat()

    # Session state init
    if "days" not in st.session_state:
        st.session_state.days = default_days()
    if "otHours" not in st.session_state:
        st.session_state.otHours = 0.0
    if "otRate" not in st.session_state:
        st.session_state.otRate = None
    if "bonus" not in st.session_state:
        st.session_state.bonus = 0.0
    if "deduction" not in st.session_state:
        st.session_state.deduction = 0.0

    # --- LLM Assistant ---
    with st.expander("🤖 Payroll Assistant (optional Llama/Ollama)"):
        msg = st.text_area("Type attendance in English/Tamil",
                           placeholder="Mon–Sat present, Wed half day, OT 3 hours, advance 500, bonus 200")
        model = st.text_input("Ollama model", value="llama3.1")
        colA, colB = st.columns([1,2])

        if colA.button("Parse & Apply"):
            if not msg.strip():
                st.error("Type a message first")
            else:
                try:
                    parsed = llm_parse_attendance(msg.strip(), model=model.strip(), timeout_s=4)
                    st.success("Parsed using LLM")
                except Exception as e:
                    parsed = fallback_parse_attendance(msg.strip())
                    st.warning(f"Ollama not used (fallback). Reason: {e}")

                st.session_state.days = {**st.session_state.days, **parsed.get("days", {})}
                st.session_state.otHours = float(parsed.get("otHours", 0.0))
                st.session_state.otRate = parsed.get("otRate", None)
                st.session_state.bonus = float(parsed.get("bonus", 0.0))
                st.session_state.deduction = float(parsed.get("deduction", 0.0))
                st.rerun()

        colB.caption("Tip: If Ollama is not running, it will fallback quickly (4s timeout).")

    # --- Days entry ---
    st.subheader("Attendance (Mon–Sun)")
    day_labels = {
        "mon":"Mon", "tue":"Tue", "wed":"Wed", "thu":"Thu", "fri":"Fri", "sat":"Sat", "sun":"Sun"
    }
    cols = st.columns(7)
    for i, k in enumerate(DAY_KEYS):
        with cols[i]:
            st.session_state.days[k] = st.selectbox(
                day_labels[k],
                ["P", "H", "A"],
                index=["P","H","A"].index(st.session_state.days.get(k, "A")),
                key=f"day_{k}"
            )

    # --- Other fields ---
    c1, c2, c3, c4 = st.columns(4)
    st.session_state.otHours = c1.number_input("OT Hours", min_value=0.0, value=float(st.session_state.otHours), step=0.5)
    # OT Rate: allow blank for default
    ot_rate_input = c2.text_input("OT Rate (₹/hr) (blank = default)", value="" if st.session_state.otRate is None else str(st.session_state.otRate))
    st.session_state.otRate = None if ot_rate_input.strip() == "" else float(ot_rate_input)

    st.session_state.bonus = c3.number_input("Bonus (₹)", min_value=0.0, value=float(st.session_state.bonus), step=50.0)
    st.session_state.deduction = c4.number_input("Deduction/Advance (₹)", min_value=0.0, value=float(st.session_state.deduction), step=50.0)

    # --- Calc preview ---
    calc = calc_weekly_salary(
        daily_rate=daily_rate,
        days=st.session_state.days,
        ot_hours=st.session_state.otHours,
        ot_rate=st.session_state.otRate,
        bonus=st.session_state.bonus,
        deduction=st.session_state.deduction
    )

    st.subheader("Salary Preview")
    b1, b2, b3, b4, b5 = st.columns(5)
    b1.metric("Present Days", calc["presentDays"])
    b2.metric("Half Days", calc["halfDays"])
    b3.metric("Base Pay", f"₹{round(calc['base'])}")
    b4.metric("Overtime", f"₹{round(calc['overtime'])}")
    b5.metric("Total", f"₹{round(calc['total'])}")

    # --- Save ---
    if st.button("Save Week Record"):
        record = {
            "id": f"wk_{uuid4().hex[:12]}",
            "workerId": worker["id"],
            "weekStartDate": week_start_str,
            "daysJson": json.dumps(calc["days"]),
            "otHours": float(st.session_state.otHours),
            "otRate": float(calc["otRate"]),
            "bonus": float(st.session_state.bonus),
            "deduction": float(st.session_state.deduction),
            "totalSalary": float(calc["total"]),
            "breakdownJson": json.dumps(calc),
            "status": "UNPAID",
            "updatedAt": datetime.utcnow().isoformat(timespec="seconds") + "Z"
        }
        upsert_week(record)
        st.success("Saved ✅")

    # --- History ---
    st.subheader("History")
    weeks = list_weeks(worker["id"])
    if not weeks:
        st.info("No records yet.")
    else:
        for r in weeks:
            breakdown = json.loads(r["breakdownJson"])
            st.write(
                f"**{r['weekStartDate']}** — **₹{round(r['totalSalary'])}**  "
                f"(P:{breakdown.get('presentDays',0)} H:{breakdown.get('halfDays',0)} OT:{r['otHours']})"
            )

# ========== POLICY Q&A PAGE ==========
else:
    st.title("Policy Q&A (simple RAG)")

    q = st.text_input("Ask about payroll rules", placeholder="What is the OT rate rule?")
    if st.button("Search Policy"):
        ctx = retrieve_policy_context(q)
        if not ctx.strip():
            st.warning("No policy text found. Add rules in data/policies.txt")
        else:
            st.subheader("Relevant policy lines")
            st.code(ctx)

    st.caption("This is keyword-based retrieval. Later we can upgrade to embeddings (Chroma/FAISS).")