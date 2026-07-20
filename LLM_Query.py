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

# Section descriptions — gives the inner LLM context about what kind of document it's reading
SECTION_DESCRIPTIONS = {
    "Financial Statements": (
        "Primary financial statements: Statement of Profit or Loss, Statement of Financial Position "
        "(Balance Sheet), Statement of Changes in Equity, and Statement of Cash Flows. "
        "Contains key financial figures, totals, and comparative year columns. Data is often in tabular format."
    ),
    "Notes to Financial Statements": (
        "Supporting disclosures that explain and provide additional detail for the financial statements, "
        "including accounting policies, disaggregated line-item breakdowns, significant judgments, "
        "estimates, assumptions, and other required disclosures."
    ),
    "Remuneration Report": (
        "Mandatory statutory section on Key Management Personnel (KMP) compensation: remuneration policies, "
        "executive and director pay, short-term and long-term incentives, share-based compensation, "
        "and links between remuneration and company performance."
    ),
    "Business Review & Management Commentary": (
        "Narrative and quantitative discussion of the company's operations, financial performance, strategy, "
        "principal risks, governance, and future outlook. May include quantified measures, estimates, "
        "forecasts, targets, and other explanatory information."
    ),
    "Directors Report": (
        "Statutory report by the directors: names of directors, principal activities, review of operations, "
        "significant events, significant changes in the state of affairs, and likely developments. "
        "May sometimes include remuneration content if no separate Remuneration Report exists."
    ),
    "Auditor's Report": (
        "Independent external auditor's assurance report expressing an opinion on the financial statements, "
        "including the basis for the opinion and other required audit disclosures."
    ),
    "Directors' Declaration": (
        "Formal statement by the directors confirming the financial statements comply with applicable "
        "accounting standards, give a true and fair view, and that the company is solvent."
    ),
    "Other Information": (
        "Supplementary or administrative sections: shareholder information, corporate directory, "
        "appendices, sustainability summaries, and similar supporting information."
    ),
}

# Maximum allowed calls per session
MAX_CALLS = 20

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

    **USAGE LIMIT: This function can only be called 20 times per session.**
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
        UsageLimitExceeded: If the 20-call limit has been reached.
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
    #api_key = os.environ.get("GEMINI_API_KEY")
    os.environ["GEMINI_API_KEY"] = "DUMMY_KEY"
    client = genai.Client()

    section_desc = SECTION_DESCRIPTIONS.get(section_name, "")
    year_label = year if year else "All available"

    system_instruction = (
        f"You are a financial analyst specialising in Australian and New Zealand annual reports.\n\n"
        f"## Context\n"
        f"- Company: {company_name}\n"
        f"- Country: {'Australia' if country == 'Aus' else 'New Zealand'}\n"
        f"- Section: {section_name}\n"
        f"- Year(s): {year_label}\n\n"
        f"## Section Description\n"
        f"{section_desc}\n\n"
        f"## Rules\n"
        f"1. Answer ONLY from the provided content. If the information is not present, "
        f"explicitly state 'Not found in the provided content' — do NOT guess or use general knowledge.\n"
        f"2. The content is Markdown-formatted and may contain tables. Parse tables carefully.\n"
        f"3. When citing figures, ALWAYS include the currency and units exactly as stated in the "
        f"source (e.g., 'AUD $1,234 million', 'NZD \'000s'). If units are ambiguous, flag this.\n"
        f"4. Be precise and concise. Structure your answer with clear headings if multiple data points are requested.\n"
        f"5. If the content spans multiple years, clearly label each year's figures.\n"
    )

    user_message = (
        f"## Your Task\n{prompt}\n\n"
        f"## Output Requirements\n"
        f"- State currency/units for all figures\n"
        f"- If data spans multiple years, present comparatively\n"
        f"- If the requested information is not in the content, state this explicitly\n\n"
        f"## Source Content\n{combined_content}"
    )

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

        # Add usage tracking footer every 4th call or when running low
        usage_footer = ""
        if current_count % 4 == 0 or remaining_after <= 5:
            usage_footer = f"\n\n{'='*60}\nLLM_Query calls used: {current_count}/{MAX_CALLS} | Remaining: {remaining_after}"
            if remaining_after <= 5:
                usage_footer += f"\nWARNING: Only {remaining_after} LLM_Query calls remaining! Use them wisely."

        return llm_response + usage_footer

    except Exception as e:
        return (
            f"LLM ERROR: Failed to get a response from the LLM — {str(e)}\n\n"
            f"LLM_Query calls used: {current_count}/{MAX_CALLS} | Remaining: {remaining_after}"
        )