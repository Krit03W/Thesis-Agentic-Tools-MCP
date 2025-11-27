from __future__ import annotations

import argparse
import sqlite3
from pathlib import Path
from typing import Iterable, List, Sequence, Tuple


def get_connection(db_path: Path) -> sqlite3.Connection:
    return sqlite3.connect(db_path)


def list_tables(conn: sqlite3.Connection) -> List[str]:
    cursor = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    return [row[0] for row in cursor.fetchall()]


def fetch_rows(
    conn: sqlite3.Connection, table: str, limit: int
) -> Tuple[Sequence[str], Iterable[Tuple]]:
    available = list_tables(conn)
    if table not in available:
        raise ValueError(f"table '{table}' not found; available: {', '.join(available)}")

    # Double quotes let us safely query tables with reserved names like Case.
    cursor = conn.execute(f'SELECT * FROM "{table}" LIMIT ?', (limit,))
    columns = [description[0] for description in cursor.description]
    return columns, cursor.fetchall()


def main() -> None:
    parser = argparse.ArgumentParser(description="Read data from the CRM Arena SQLite database.")
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("database") / "crmarena_data.db",
        help="Path to the SQLite database file.",
    )
    parser.add_argument(
        "--table",
        help="Table name to preview. If omitted, all available tables are listed.",
    )
    parser.add_argument(
        "--account",
        action="store_true",
        help="Shortcut to preview the Account table (same as --table Account).",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help="Number of rows to fetch from the selected table.",
    )
    args = parser.parse_args()

    # Convenience flag: --account behaves the same as --table Account.
    if args.account:
        args.table = "Account"

    conn = get_connection(args.db)
    try:
        if not args.table:
            for name in list_tables(conn):
                print(name)
            return

        columns, rows = fetch_rows(conn, args.table, args.limit)
        print(f"Table: {args.table}")
        print("Columns:", ", ".join(columns))
        for row in rows:
            print(row)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
