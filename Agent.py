import os
import time
from google import genai

def run_agent(input_text: str = 'Hey this a test to see if the api is working', api_key: str = None):
    # Define file paths relative to this script's location
    base_dir = os.path.dirname(os.path.abspath(__file__))
    agents_path = os.path.join(base_dir, ".agents", "AGENTS.md")
    bm25_path = os.path.join(base_dir, "BM25_Search.py")
    llm_path = os.path.join(base_dir, "LLM_Query.py")


    # Read the files into variables
    with open(agents_path, 'r', encoding='utf-8') as f:
        agents_content = f.read()

    with open(bm25_path, 'r', encoding='utf-8') as f:
        BM25_content = f.read()

    with open(llm_path, 'r', encoding='utf-8') as f:
        LLM_content = f.read()

    if api_key:
        LLM_content = LLM_content.replace(
            'api_key = os.environ.get("GEMINI_API_KEY")',
            f'api_key = "{api_key}"'
        )

    client = genai.Client(
        api_key=api_key,
    )

    tools = [
        {
            'type': 'code_execution',
        },
    ]

    stream = client.interactions.create(
        agent='antigravity-preview-05-2026',
        input=input_text,
        tools=tools,
        stream=True,
        environment={
            'type': 'remote',
            'network': {
                'allowlist': [
                    {
                        'domain': 'generativelanguage.googleapis.com',
                        'transform': [
                            {
                                'key': 'x-goog-api-key',
                                'value': 'GEMINI_API_KEY'
                            }
                        ],
                    }
                ]
            },
            'sources': [
                {
                    'type': 'gcs',
                    'source': 'gs://asx_aus_sql',
                    'target': '/Data',
                },
                {
                    'type': 'inline',
                    'target': '/.agents/AGENTS.md',
                    'content': agents_content,
                },
                {
                    'type': 'inline',
                    'target': '/BM25_Search.py',
                    'content': BM25_content,
                },
                {
                    'type': 'inline',
                    'target': '/LLM_Query.py',
                    'content': LLM_content,
                }
            ],
        },
    )

    for event in stream:
        yield event

def run_context_gatherer(topic: str, api_key: str = None) -> str:
    """Use a background agent with google_search to gather context on a topic."""
    client = genai.Client(api_key=api_key)

    tools = [
        {
            'type': 'google_search',
        },
    ]

    interaction = client.interactions.create(
        agent='antigravity-preview-05-2026',
        input=topic,
        background=True,
        tools=tools,
        environment={
            'type': 'remote',
            'network': {
                'allowlist': [
                    {
                        'domain': 'generativelanguage.googleapis.com',
                        'transform': [
                            {
                                'key': 'x-goog-api-key',
                                'value': 'GEMINI_API_KEY'
                            }
                        ],
                    }
                ]
            },
        },
    )

    print(f"Research started: {interaction.id}")

    while True:
        interaction = client.interactions.get(interaction.id)
        if interaction.status == "completed":
            break
        elif interaction.status == "failed":
            error_msg = getattr(interaction, 'error', 'Unknown error')
            print(f"Research failed: {error_msg}")
            return f"Research failed: {error_msg}"
        time.sleep(10)

    # Extract the final text output
    output_text = ''
    if hasattr(interaction, 'output_text'):
        output_text = interaction.output_text
    else:
        for step in getattr(interaction, 'steps', []):
            for part in getattr(step, 'output', []):
                text = getattr(part, 'text', None)
                if text:
                    output_text += text

    print(output_text.strip())
    return output_text.strip()

if __name__ == "__main__":
    import os
    test_api_key = os.environ.get("GEMINI_API_KEY", "YOUR_API_KEY_HERE")
    for event in run_agent(api_key=test_api_key):
        print(event)