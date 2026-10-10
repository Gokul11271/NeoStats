import os
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

endpoint = os.getenv("NEOSTATS_OPENAI_BASE_URL", "https://neo-hackathon.services.ai.azure.com/openai/v1/")
deployment_name = os.getenv("NEOSTATS_OPENAI_MODEL", "Neo-Hackathon")
api_key = os.getenv("NEOSTATS_OPENAI_API_KEY", "")

if not api_key:
    raise ValueError("NEOSTATS_OPENAI_API_KEY environment variable is missing. Set it in .env file.")

client = OpenAI(
    base_url=endpoint,
    api_key=api_key
)

completion = client.chat.completions.create(
    model=deployment_name,
    messages=[
        {
            "role": "user",
            "content": "What is the capital of France?",
        }
    ],
)

print(completion.choices[0].message)