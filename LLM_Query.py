import sqlite3
import os
import json
from typing import Optional, Annotated
from google import genai
from google.genai import types

# Database paths
DB_PATHS = {
    "Aus": r"Data/financials_Aus_fts.db",
    "NZ": r"Data/financials_NZ_fts.db"
}

# Maximum allowed calls per session
MAX_CALLS = 30

# Counter file stored in temp directory (current working directory when agent code runs)
# This persists across code executions within the same Master2.py session
COUNTER_FILE = os.path.join(os.getcwd(), ".llm_query_counter.json")


class UsageLimitExceeded(Exception):
    """Raised when the LLM_Query usage limit is exceeded"""
    pass


def _load_counter():
    """Load counter from temp directory file"""
    if os.path.exists(COUNTER_FILE):
        try:
            with open(COUNTER_FILE, 'r') as f:
                data = json.load(f)
                return data.get('count', 0)
        except (json.JSONDecodeError, IOError):
            return 0
    return 0


def _save_counter(count):
    """Save counter to temp directory file"""
    try:
        with open(COUNTER_FILE, 'w') as f:
            json.dump({'count': count, 'max': MAX_CALLS}, f)
    except IOError:
        # If we can't write, continue with in-memory only (degraded mode)
        pass


def get_remaining_calls():
    """Get the number of remaining LLM_Query calls"""
    current = _load_counter()
    return max(0, MAX_CALLS - current)


def get_usage_stats():
    """Get detailed usage statistics"""
    current = _load_counter()
    return {
        'used': current,
        'max': MAX_CALLS,
        'remaining': max(0, MAX_CALLS - current)
    }


def LLM_Query(
    country: Annotated[str, "The country database to query. MUST be exactly 'Aus' or 'NZ'."],
    company_name: Annotated[str, "The exact company name as it appears in the database (e.g. 'WOOLWORTHS GROUP LTD')."],
    section_name: Annotated[str, "The report section to retrieve (e.g. 'Financial Statements', 'Directors Report')."],
    prompt: Annotated[str, "The analytical question to ask the LLM about the retrieved content."],
    year: Annotated[Optional[str], "Optional reporting year filter ('2023' or '2024'). If omitted, retrieves all years."] = None,
) -> str:
    """
    Retrieves content from the selected financials database for a given company and section,
    then sends it to the LLM along with the user's prompt to produce an answer.

    **USAGE LIMIT: This function can only be called 30 times per session.**
    Each call decrements the remaining count. Check remaining calls before using.

    This tool handles everything: database retrieval + LLM analysis in one call.

    Parameters:
        - country: 'Aus' for Australian companies or 'NZ' for New Zealand companies.
        - company_name: The exact company name as stored in the `fts_reports` table.
        - section_name: The section of the financial report to query.
        - prompt: The question or instruction for the LLM to answer using the content.
        - year: Optional year filter. If None, content from all available years is retrieved.

    Returns:
        A string containing the LLM's analysis of the retrieved content.
        The response includes remaining call count.

    Raises:
        UsageLimitExceeded: If the 30-call limit has been reached.
    """

    # --- Check usage limit BEFORE executing ---
    current_count = _load_counter()

    if current_count >= MAX_CALLS:
        raise UsageLimitExceeded(
            f"LLM_Query LIMIT REACHED: You have used all {MAX_CALLS} allowed calls. "
            f"No more LLM_Query calls are permitted. You must answer using only the information "
            f"you've already gathered."
        )

    # Increment and save counter
    current_count += 1
    _save_counter(current_count)
    remaining_after = MAX_CALLS - current_count

    # --- Verify Country Input ---
    if country not in DB_PATHS:
        return (
            f"INPUT ERROR: Invalid country '{country}'. You must specify 'Aus' or 'NZ'.\n\n"
            f"LLM_Query calls used: {current_count}/{MAX_CALLS} | Remaining: {remaining_after}"
        )
    
    db_path = DB_PATHS[country]

    # --- Step 1: Retrieve content from the database ---
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        if year:
            cursor.execute(
                "SELECT year, content FROM fts_reports WHERE company_name = ? AND section_name = ? AND year = ?",
                (company_name, section_name, year),
            )
        else:
            cursor.execute(
                "SELECT year, content FROM fts_reports WHERE company_name = ? AND section_name = ?",
                (company_name, section_name),
            )

        rows = cursor.fetchall()
        conn.close()
    except Exception as e:
        return (
            f"DATABASE ERROR: Failed to query {country} database — {str(e)}\n\n"
            f"LLM_Query calls used: {current_count}/{MAX_CALLS} | Remaining: {remaining_after}"
        )

    if not rows:
        return (
            f"NO DATA FOUND: No records matched country='{country}', company_name='{company_name}', "
            f"section_name='{section_name}'" + (f", year='{year}'" if year else "") + ". "
            "Double-check that the company name and section name are spelled exactly as stored in the database.\n\n"
            f"LLM_Query calls used: {current_count}/{MAX_CALLS} | Remaining: {remaining_after}"
        )

    # Combine content from all matching rows, labelled by year
    combined_content = ""
    for row_year, content in rows:
        combined_content += f"\n\n===== {company_name} ({country}) — {section_name} — {row_year} =====\n\n"
        combined_content += content

    # --- Step 2: Send content + prompt to the LLM ---
    api_key = os.environ.get("GEMINI_API_KEY")

    client = genai.Client(
        vertexai=False,
        api_key=api_key,
    )

    system_instruction = (
        "You are a financial analyst. You will be given content extracted from an Australian "
        "or New Zealand financial report. Answer the user's question using ONLY the provided content. "
        "Be precise, cite specific figures, and present numbers clearly."
    )

    user_message = f"## User Question\n{prompt}\n\n## Financial Report Content\n{combined_content}"

    contents = [
        types.Content(
            role="user",
            parts=[types.Part.from_text(text=user_message)],
        )
    ]

    config = types.GenerateContentConfig(
        temperature=0.6,
        max_output_tokens=65535,
        system_instruction=system_instruction,
        thinking_config=types.ThinkingConfig(
            thinking_level="HIGH",
        )
    )

    try:
        response = client.models.generate_content(
            model="gemini-3.1-flash-lite",
            contents=contents,
            config=config,
        )
        llm_response = response.text

        # Add usage tracking footer to the response
        usage_footer = f"\n\n{'='*60}\nLLM_Query calls used: {current_count}/{MAX_CALLS} | Remaining: {remaining_after}"
        if remaining_after <= 5:
            usage_footer += f"\nWARNING: Only {remaining_after} LLM_Query calls remaining! Use them wisely."

        return llm_response + usage_footer

    except Exception as e:
        return (
            f"LLM ERROR: Failed to get a response from the LLM — {str(e)}\n\n"
            f"LLM_Query calls used: {current_count}/{MAX_CALLS} | Remaining: {remaining_after}"
        )