"""List the Gemini "flash" models available to your API key (live API call)."""
import os

from google import genai

client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
for model in client.models.list():
    if "flash" in (model.name or ""):
        print(model.name)
