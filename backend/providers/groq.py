from openai import OpenAI
import os
from pathlib import Path
from dotenv import load_dotenv

# Pin to backend/.env so the key is found regardless of the working directory.
load_dotenv()

api_key = os.getenv("GROQ_API_KEY")
if not api_key:
    raise RuntimeError("GROQ_API_KEY is not set in the environment (.env)")

client = OpenAI(
    api_key=api_key,
    base_url="https://api.groq.com/openai/v1",
)

MODEL = "openai/gpt-oss-20b"


def GPTresponse(query: str) -> str:
    response = client.chat.completions.create(
        model=MODEL,
        messages=[{"role": "user", "content": query}],
    )
    return response.choices[0].message.content
