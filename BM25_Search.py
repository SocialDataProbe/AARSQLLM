import sqlite3
import os
from typing import Optional, List, Annotated

# Paths to the pre-built FTS5 index databases (created by build_fts_index.py)
DB_PATHS = {
    "Aus": r"Data/financials_Aus_fts.db",
    "NZ": r"Data/financials_NZ_fts.db"
}

def BM25_Search(
    country: Annotated[str, "The country database to search. MUST be exactly 'Aus' or 'NZ'."],
    keywords: Annotated[str, "Space-separated search keywords for FTS5 full-text search (e.g. 'revenue growth operating'). Supports FTS5 query syntax: use OR between terms for alternatives, double-quote phrases for exact matches (e.g. '\"net profit\" OR revenue')."],
    top_k: Annotated[int, "Number of top results to return, ranked by BM25 relevance score."] = 10,
    year: Annotated[Optional[str], "Optional year filter ('2023' or '2024'). If omitted, searches all years."] = None,
    section_name: Annotated[Optional[str], "Optional section filter (e.g. 'Financial Statements', 'Auditor\\'s Report'). If omitted, searches all sections."] = None,
) -> str:
    
    # Verify Country Input
    if country not in DB_PATHS:
        return f"INPUT ERROR: Invalid country '{country}'. You must specify 'Aus' or 'NZ'."
    
    db_path = DB_PATHS[country]

    # Check that the specific FTS index exists
    if not os.path.exists(db_path):
        return (
            f"FTS INDEX NOT FOUND: The pre-built FTS5 index database for {country} does not exist.\n"
            f"Expected path: {db_path}\n"
            "Ensure the database files have been created and placed in the correct directory."
        )

    try:
        # Connect to the pre-built FTS index (read-only)
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
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
                f"in the {total_rows} rows searched within the {country} database.\n"
                f"Filters applied — year: {year or 'all'}, section: {section_name or 'all'}\n"
                f"TIP: Try broader or alternative keywords."
            )

        # Format the output
        output_lines = []
        output_lines.append(f"BM25 SEARCH RESULTS — Top {len(results)} of {total_rows} rows searched in the {country} database")
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
            output_lines.append(f"    Company:  {cname} ({country})")
            output_lines.append(f"    Year:     {yr}")
            output_lines.append(f"    Section:  {sec}")
            output_lines.append("-" * 80)

        return "\n".join(output_lines)

    except Exception as e:
        return f"BM25_SEARCH ERROR: {str(e)}"