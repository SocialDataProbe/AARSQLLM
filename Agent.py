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

    interaction = client.interactions.create(
        agent='antigravity-preview-05-2026',
        input=input_text,
        tools=tools,
        background=True,
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

    # Poll until the interaction completes, then return the output
    while True:
        interaction = client.interactions.get(interaction.id)
        if interaction.status == "completed":
            return interaction.output_text
        elif interaction.status == "failed":
            raise RuntimeError(f"Agent interaction failed: {interaction.error}")
        time.sleep(5)

if __name__ == "__main__":
    test_api_key = os.environ.get("GEMINI_API_KEY", "YOUR_API_KEY_HERE")
    result = run_agent(api_key=test_api_key)
    print(result)