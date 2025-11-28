from __future__ import annotations

import asyncio
import json
import os
import time
import traceback

from dotenv import load_dotenv
import streamlit as st

from agent_api import GeminiSQLAgent
from mcp_server import ask as mcp_ask

# Load environment variables for API key, DB path, etc.
load_dotenv()


@st.cache_resource
def load_agent() -> GeminiSQLAgent:
    # Cache the agent so we only initialize Gemini/config once.
    return GeminiSQLAgent()


def render_table(sql: str, reasoning: str | None, rows: list[dict]) -> None:
    st.subheader("SQL ที่ได้")
    st.code(sql, language="sql")

    if reasoning:
        st.write("เหตุผลจากโมเดล:")
        st.info(reasoning)

    st.subheader("ผลลัพธ์")
    if rows:
        st.dataframe(rows)
    else:
        st.write("ไม่มีแถวผลลัพธ์")


def run_via_api(question: str) -> None:
    start = time.perf_counter()
    try:
        agent = load_agent()
        resp = agent.answer(question)
        render_table(resp.sql, resp.reasoning, resp.rows)
        duration = time.perf_counter() - start
        log_run("API", duration, param_ok=True, misuse=False, success=True)
    except Exception as exc:  # pylint: disable=broad-except
        st.error(f"เรียกผ่าน API ล้มเหลว: {exc}")
        with st.expander("รายละเอียดข้อผิดพลาด"):
            st.code("".join(traceback.format_exc()))
        duration = time.perf_counter() - start
        log_run("API", duration, param_ok=False, misuse=True, success=False)


def run_via_mcp(question: str) -> None:
    start = time.perf_counter()
    try:
        # Call MCP tool in-process; it returns a JSON string.
        raw = asyncio.run(mcp_ask(question))
        payload = json.loads(raw)
        render_table(payload["sql"], payload.get("reasoning"), payload.get("rows", []))
        duration = time.perf_counter() - start
        log_run("MCP", duration, param_ok=True, misuse=False, success=True)
    except Exception as exc:  # pylint: disable=broad-except
        st.error(f"เรียกผ่าน MCP ล้มเหลว: {exc}")
        with st.expander("รายละเอียดข้อผิดพลาด"):
            st.code("".join(traceback.format_exc()))
        duration = time.perf_counter() - start
        log_run("MCP", duration, param_ok=False, misuse=True, success=False)


def init_metrics_state() -> None:
    if "eval_runs" not in st.session_state:
        st.session_state["eval_runs"] = []  # list of dicts: backend, time, param_ok, misuse, success


def log_run(
    backend: str,
    duration: float,
    param_ok: bool,
    misuse: bool,
    success: bool,
) -> None:
    # Append a run for evaluation metrics.
    init_metrics_state()
    st.session_state["eval_runs"].append(
        {
            "backend": backend,
            "duration": duration,
            "param_ok": param_ok,
            "misuse": misuse,
            "success": success,
        }
    )


def manual_log_form() -> None:
    st.markdown("### บันทึกผลการรันทดสอบด้วยตนเอง")
    with st.form("manual_log"):
        backend = st.selectbox("Backend", ["API", "MCP"])
        duration = st.number_input("เวลาที่ใช้ (วินาที)", min_value=0.0, value=1.0, step=0.1)
        param_ok = st.checkbox("พารามิเตอร์ถูกต้อง", value=True)
        misuse = st.checkbox("Tool misuse (เช่น query ผิด/เกินขอบเขต)", value=False)
        success = st.checkbox("สำเร็จ", value=True)
        submitted = st.form_submit_button("เพิ่มข้อมูล")
        if submitted:
            log_run(backend, duration, param_ok, misuse, success)
            st.success("บันทึกเรียบร้อย")


def compute_metrics():
    init_metrics_state()
    runs = st.session_state["eval_runs"]
    grouped = {"API": [], "MCP": []}
    for r in runs:
        grouped[r["backend"]].append(r)

    def agg(items):
        if not items:
            return None
        avg_time = sum(r["duration"] for r in items) / len(items)
        param_acc = 100 * sum(1 for r in items if r["param_ok"]) / len(items)
        misuse_rate = 100 * sum(1 for r in items if r["misuse"]) / len(items)
        success_rate = 100 * sum(1 for r in items if r["success"]) / len(items)
        return {
            "Average Task Time (sec)": avg_time,
            "Parameter Accuracy (%)": param_acc,
            "Tool Misuse Rate (%)": misuse_rate,
            "Success Rate (%)": success_rate,
            "N": len(items),
        }

    return {backend: agg(items) for backend, items in grouped.items()}


def main() -> None:
    st.set_page_config(page_title="Gemini DB Agent", page_icon="🤖", layout="wide")
    st.title("Gemini DB Agent")
    st.caption("ถามด้วยภาษาธรรมชาติให้ Gemini สร้าง SQL และดึงข้อมูลจากฐาน CRM")

    st.sidebar.header("การตั้งค่า")
    backend = st.sidebar.radio("เลือกโหมดตอบคำถาม", ["API (ตรง)", "MCP (ผ่านเครื่องมือ)"])
    example = st.sidebar.selectbox(
        "ตัวอย่างคำถาม",
        [
            "",
            "สรุปจำนวนเคสแยกตามสถานะ",
            "แสดง 5 order ล่าสุดของ account ที่ชื่อ John Doe",
            "ดึง email และชื่อของ contact ที่อยู่ใน Bangkok",
        ],
    )
    st.sidebar.write(
        "ค่าเริ่มต้นอ่านจาก environment variables (.env):\n"
        "- GEMINI_API_KEY (จำเป็น)\n"
        "- CRM_DB_PATH (เช่น database/crmarena_data.db)\n"
        "- GEMINI_MODEL (เช่น gemini-2.5-flash)\n"
        "- AGENT_MAX_ROWS"
    )

    tab_run, tab_eval = st.tabs(["ถาม-ตอบ", "Evaluation"])

    with tab_run:
        st.write("กรอกคำถามที่ต้องการให้ระบบช่วยแปลงเป็น SQL และดึงข้อมูลออกมา")
        question = st.text_area("คำถาม", value=example, height=120)

        if st.button("รันคำถาม", type="primary", use_container_width=True):
            if not question.strip():
                st.warning("กรุณากรอกคำถามก่อน")
            else:
                if backend.startswith("API"):
                    run_via_api(question.strip())
                else:
                    run_via_mcp(question.strip())

        st.divider()
        st.write(
            "หมายเหตุ: ระบบจำกัดให้ใช้เฉพาะคำสั่ง SELECT และจะเพิ่ม LIMIT "
            f"{os.getenv('AGENT_MAX_ROWS', '50')} อัตโนมัติหากไม่ได้ระบุ"
        )

    with tab_eval:
        st.subheader("เปรียบเทียบ API vs MCP")
        metrics = compute_metrics()
        cols = st.columns(2)
        for idx, backend_name in enumerate(["API", "MCP"]):
            with cols[idx]:
                st.markdown(f"#### {backend_name}")
                data = metrics.get(backend_name)
                if not data:
                    st.info("ยังไม่มีข้อมูล")
                else:
                    st.metric("Average Task Time (sec)", f"{data['Average Task Time (sec)']:.2f}")
                    st.metric("Parameter Accuracy (%)", f"{data['Parameter Accuracy (%)']:.1f}%")
                    st.metric("Tool Misuse Rate (%)", f"{data['Tool Misuse Rate (%)']:.1f}%")
                    st.metric("Success Rate (%)", f"{data['Success Rate (%)']:.1f}%")
                    st.caption(f"Runs: {data['N']}")

        st.markdown("#### แนะนำเมทริกเพิ่มเติม")
        st.write(
            "- Success Rate (%): อัตราการตอบสำเร็จไม่ error\n"
            "- Latency p95 (sec): เวลาเสี้ยงบน 95% เพื่อดู worst-case\n"
            "- Safety violations: จำนวนครั้งที่มีการสร้าง query ผิด policy"
        )

        manual_log_form()


if __name__ == "__main__":
    main()
