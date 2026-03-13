import os
from google import genai

client = genai.Client(api_key=os.environ.get("GOOGLE_API_KEY"))
for model_id in ["gemini-2.5-flash", "gemini-flash-latest", "gemini-2.0-flash-lite", "gemini-3.1-flash-preview"]:
    print(f"Testing {model_id}...")
    try:
        response = client.models.generate_content(
            model=model_id,
            contents="Say hi"
        )
        print("Success!")
    except Exception as e:
        print(f"Error: {e}")
    print()
