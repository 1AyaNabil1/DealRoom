# verify_setup.py
import os
import sys
from dotenv import load_dotenv
from google import genai

def verify():
    load_dotenv()
    api_key = os.getenv("GOOGLE_API_KEY")
    
    if not api_key:
        print("ERROR: GOOGLE_API_KEY not found in environment variables.")
        sys.exit(1)

    try:
        # Default v1beta
        client = genai.Client(api_key=api_key)
        
        # Use the exact model name from the list
        response = client.models.generate_content(
            model='gemini-flash-latest',
            contents="hi"
        )
        
        if response:
            print("GEMINI CONNECTION OK")
        else:
            print("ERROR: Received empty response.")
            sys.exit(1)
            
    except Exception as e:
        if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
            print("GEMINI CONNECTION OK (API KEY VALID, but Quota Exhausted)")
        else:
            print(f"GEMINI CONNECTION FAILED: {type(e).__name__} - {str(e)}")
            sys.exit(1)

if __name__ == "__main__":
    verify()
