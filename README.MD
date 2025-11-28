# Gemini + SQLite Agent API

This project exposes a small FastAPI service that lets a Gemini model translate natural‑language requests into safe SQL queries against the bundled SQLite CRM database (`database/crmarena_data.db`).

## Setup
1) Install dependencies  
   ```
   pip install -r requirements.txt
   ```
2) ตั้งค่า environment variables (รองรับอ่านอัตโนมัติจาก `.env`)  
   - สร้างไฟล์ `.env` เช่น  
     ```
     GEMINI_API_KEY=your_key_here
     CRM_DB_PATH=database/crmarena_data.db
     GEMINI_MODEL=gemini-2.5-flash
     AGENT_MAX_ROWS=50
     ```
   - หรือ export ผ่าน shell: `$env:GEMINI_API_KEY="<your_api_key>"`
3) Run the API  
   ```
   uvicorn agent_api:app --reload --port 8000
   ```

## Usage
- Explore schema: `GET /schema`
- Ask a question: `POST /query` with body:
  ```json
  { "question": "แสดง 5 order ล่าสุดของ account ที่ชื่อ John Doe" }
  ```
The agent prompts Gemini to return a JSON payload with a SELECT statement (LIMIT enforced), executes it on SQLite, and returns `sql`, `columns`, `rows`, and an optional `reasoning` field.

## Streamlit UI
- Launch: `streamlit run streamlit_app.py`
- หน้า UI จะให้กรอกคำถามภาษาไทย/อังกฤษ แล้วแสดง SQL ที่โมเดลสร้างพร้อมผลลัพธ์จากฐาน `database/crmarena_data.db`.

## MCP Server
- รัน MCP server (stdin/stdout transport):  
  ```
  python mcp_server.py
  ```
- Tools:
  - `ask(question: str)` → ส่งคำถามภาษาธรรมชาติ กลับ JSON string `{sql, reasoning, columns, rows}`
  - `schema()` → ส่ง mapping ตาราง/คอลัมน์สำหรับ grounding
หมายเหตุ: โหลด environment variables จาก `.env` เช่น `GEMINI_API_KEY`, `CRM_DB_PATH`, `GEMINI_MODEL`, `AGENT_MAX_ROWS`.
