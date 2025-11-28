from __future__ import annotations

import json
from typing import Any, Dict

from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

from agent_api import QueryResponse, get_agent

# Load environment variables so GEMINI_API_KEY/CRM_DB_PATH/etc. are available.
load_dotenv()

server = FastMCP("gemini-db-agent")

def response_to_dict(resp: QueryResponse) -> Dict[str, Any]:
    return {
        "sql": resp.sql,
        "reasoning": resp.reasoning,
        "columns": resp.columns,
        "rows": resp.rows,
    }

@server.tool()
async def ask(question: str) -> str:
    """
    Ask a natural-language question; returns JSON with sql/columns/rows/reasoning.
    """
    agent = get_agent()
    result = agent.answer(question)
    return json.dumps(response_to_dict(result), ensure_ascii=False)


@server.tool()
async def schema() -> Dict[str, Any]:
    """
    Return available tables and columns for grounding.
    """
    agent = get_agent()
    return agent.schema


if __name__ == "__main__":
    print("Starting MCP server 'gemini-db-agent' (stdio transport).")
    print("Tools: ask(question: str), schema()")
    server.run()
