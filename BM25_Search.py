import sqlite3
import os
from typing import Optional, List, Annotated

# Path to the pre-built FTS5 index database (created by build_fts_index.py)
FTS_DB_PATH = r"Data/financials_fts.db"

def BM25_Search(
    keywords: Annotated[str, "Space-separated search keywords for FTS5 full-text search (e.g. 'revenue growth operating'). Supports FTS5 query syntax: use OR between terms for alternatives, double-quote phrases for exact matches (e.g. '\"net profit\" OR revenue')."],
    top_k: Annotated[int, "Number of top results to return, ranked by BM25 relevance score."] = 10,
    year: Annotated[Optional[str], "Optional year filter ('2023' or '2024'). If omitted, searches all years."] = None,
    section_name: Annotated[Optional[str], "Optional section filter (e.g. 'Financial Statements', 'Auditor\\'s Report'). If omitted, searches all sections."] = None,
) -> str:
    # Check that the FTS index exists
    if not os.path.exists(FTS_DB_PATH):
        return (
            "FTS INDEX NOT FOUND: The pre-built FTS5 index database does not exist.\n"
            f"Expected path: {FTS_DB_PATH}\n"
            "Run 'python build_fts_index.py' first to create it."
        )

    try:
        # Connect to the pre-built FTS index (read-only)
        conn = sqlite3.connect(f"file:{FTS_DB_PATH}?mode=ro", uri=True)
        cursor = conn.cursor()

        # Build the query with optional filters
        # Filters are applied alongside MATCH in the WHERE clause
        conditions = ["fts_reports MATCH ?"]
        params = [keywords]

        if year:
            conditions.append("year = ?")
            params.append(year)
        if section_name:
            conditions.append("section_name = ?")
            params.append(section_name)

        where_clause = " AND ".join(conditions)
        params.append(top_k)

        search_query = """
          SELECT
                company_name,
                year,
                section_name,
                bm25(fts_reports) AS score
            FROM fts_reports
            WHERE {where_clause}
            ORDER BY score
            LIMIT ?
        """.format(where_clause=where_clause)

        cursor.execute(search_query, params)
        results = cursor.fetchall()

        # Get total row count for context
        count_conditions = []
        count_params = []
        if year:
            count_conditions.append("year = ?")
            count_params.append(year)
        if section_name:
            count_conditions.append("section_name = ?")
            count_params.append(section_name)

        if count_conditions:
            cursor.execute(
                f"SELECT COUNT(*) FROM fts_reports WHERE {' AND '.join(count_conditions)}",
                count_params
            )
        else:
            cursor.execute("SELECT COUNT(*) FROM fts_reports")
        total_rows = cursor.fetchone()[0]

        conn.close()

        if not results:
            return (
                f"NO MATCHES: The keywords '{keywords}' did not match any content "
                f"in the {total_rows} rows searched.\n"
                f"Filters applied — year: {year or 'all'}, section: {section_name or 'all'}\n"
                f"TIP: Try broader or alternative keywords."
            )

        # Format the output
        output_lines = []
        output_lines.append(f"BM25 SEARCH RESULTS — Top {len(results)} of {total_rows} rows searched")
        output_lines.append(f"Keywords: {keywords}")

        filter_parts = []
        if year:
            filter_parts.append(f"year={year}")
        if section_name:
            filter_parts.append(f"section={section_name}")
        if filter_parts:
            output_lines.append(f"Filters: {', '.join(filter_parts)}")
        output_lines.append("=" * 80)

        for i, (cname, yr, sec, score) in enumerate(results, 1):
            output_lines.append(f"\n[{i}] Score: {score:.4f}")
            output_lines.append(f"    Company:  {cname}")
            output_lines.append(f"    Year:     {yr}")
            output_lines.append(f"    Section:  {sec}")
            output_lines.append("-" * 80)

        return "\n".join(output_lines)

    except Exception as e:
        return f"BM25_SEARCH ERROR: {str(e)}"