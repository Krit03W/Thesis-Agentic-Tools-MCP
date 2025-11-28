from __future__ import annotations

import json
import os
import re
import sqlite3
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Tuple

import google.generativeai as genai
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from read_db import get_connection


# Load environment variables from .env early so globals pick them up.
load_dotenv()

DB_PATH = Path(os.getenv("CRM_DB_PATH", Path("database") / "crmarena_data.db"))
MODEL_NAME = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
MAX_ROWS = int(os.getenv("AGENT_MAX_ROWS", "50"))


def configure_gemini() -> None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Missing GEMINI_API_KEY. Set an API key before starting the server."
        )
    genai.configure(api_key=api_key)


def describe_schema() -> Dict[str, List[str]]:
    """Return a mapping of table -> column names for prompt grounding."""
    schema: Dict[str, List[str]] = {}
    with get_connection(DB_PATH) as conn:
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        for (table_name,) in cursor.fetchall():
            columns = [
                row[1] for row in conn.execute(f'PRAGMA table_info("{table_name}")')
            ]
            schema[table_name] = columns
    return schema


def enforce_select_only(sql: str) -> None:
    if not sql.strip().lower().startswith("select"):
        raise HTTPException(status_code=400, detail="Only SELECT statements are allowed.")


def ensure_limit(sql: str, limit: int) -> str:
    lowered = sql.lower()
    if "limit" in lowered:
        return sql
    # SQLite accepts LIMIT at the end of the query.
    return f"{sql.rstrip().rstrip(';')} LIMIT {limit}"


def quote_reserved_tables(sql: str, tables: Dict[str, List[str]]) -> str:
    """
    Ensure reserved-word table names are double-quoted (e.g., Case, Order).
    """
    reserved = {"case", "order"}
    for table in tables:
        if table.lower() not in reserved:
            continue
        pattern = rf'(?<!")\b{re.escape(table)}\b(?!")'
        sql = re.sub(pattern, f'"{table}"', sql)
    return sql

class QueryRequest(BaseModel):
    question: str
    session_id: str | None = None


class QueryResponse(BaseModel):
    sql: str
    rows: List[Dict[str, Any]]
    columns: List[str]
    reasoning: str | None = None


class GeminiSQLAgent:
    def __init__(self) -> None:
        configure_gemini()
        self.model = genai.GenerativeModel(MODEL_NAME)
        self.schema = describe_schema()

    def _prompt(self, question: str) -> str:
        table_docs = "\n".join(
            f'- {table}: {", ".join(cols)}' for table, cols in self.schema.items()
        )
        instructions = f"""
You are a concise SQLite expert. Given a natural language question, produce a JSON object:
{{
  "sql": "<SELECT statement limited to {MAX_ROWS} rows>",
  "reasoning": "<short rationale>"
}}
Rules:
- Only generate safe, read-only SELECT statements.
- Use the provided schema. Available tables/columns:
{table_docs}
- Prefer explicit LIMIT {MAX_ROWS} if no limit is present.
- If a table name matches a reserved word (e.g., Case, Order) wrap it in double quotes: "Case".
- Return JSON only; do not include explanations outside the JSON.
User question: {question}
"""
        return instructions.strip()

    def build_sql(self, question: str) -> Tuple[str, str | None]:
        prompt = self._prompt(question)
        response = self.model.generate_content(
            prompt, generation_config={"response_mime_type": "application/json"}
        )
        try:
            payload = json.loads(response.text)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Gemini returned non-JSON content: {response.text}",
            ) from exc

        sql = payload.get("sql")
        if not sql:
            raise HTTPException(status_code=502, detail="Gemini did not return SQL.")
        reasoning = payload.get("reasoning")
        sql = ensure_limit(sql, MAX_ROWS)
        sql = quote_reserved_tables(sql, self.schema)
        enforce_select_only(sql)
        return sql, reasoning

    def run_sql(self, sql: str) -> Tuple[List[str], List[Dict[str, Any]]]:
        try:
            with get_connection(DB_PATH) as conn:
                cursor = conn.execute(sql)
                columns = [desc[0] for desc in cursor.description]
                rows = [dict(zip(columns, row)) for row in cursor.fetchall()]
                return columns, rows
        except sqlite3.Error as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    def answer(self, question: str) -> QueryResponse:
        sql, reasoning = self.build_sql(question)
        columns, rows = self.run_sql(sql)
        return QueryResponse(sql=sql, columns=columns, rows=rows, reasoning=reasoning)


@lru_cache(maxsize=1)
def get_agent() -> GeminiSQLAgent:
    """Lazy singleton so module import does not require GEMINI_API_KEY."""
    return GeminiSQLAgent()

app = FastAPI(title="Gemini DB Agent", version="0.1.0")


@app.post("/query", response_model=QueryResponse)
def query_db(request: QueryRequest) -> QueryResponse:
    """
    Endpoint for the LLM agent to turn natural language into SQL and execute it.
    """
    return get_agent().answer(request.question)


@app.get("/schema")
def get_schema() -> Dict[str, List[str]]:
    """
    Lightweight endpoint to inspect available tables/columns.
    """
    return get_agent().schema


# Convenience for `python agent_api.py`
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "8000")))
