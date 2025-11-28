from __future__ import annotations

import asyncio
import json
import os
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
    try:
        agent = load_agent()
        resp = agent.answer(question)
        render_table(resp.sql, resp.reasoning, resp.rows)
    except Exception as exc:  # pylint: disable=broad-except
        st.error(f"เรียกผ่าน API ล้มเหลว: {exc}")
        with st.expander("รายละเอียดข้อผิดพลาด"):
            st.code("".join(traceback.format_exc()))


def run_via_mcp(question: str) -> None:
    try:
        # Call MCP tool in-process; it returns a JSON string.
        raw = asyncio.run(mcp_ask(question))
        payload = json.loads(raw)
        render_table(payload["sql"], payload.get("reasoning"), payload.get("rows", []))
    except Exception as exc:  # pylint: disable=broad-except
        st.error(f"เรียกผ่าน MCP ล้มเหลว: {exc}")
        with st.expander("รายละเอียดข้อผิดพลาด"):
            st.code("".join(traceback.format_exc()))


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


if __name__ == "__main__":
    main()
