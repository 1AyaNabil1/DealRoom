import os
import google.generativeai as gai

gai.configure(api_key=os.environ.get("GOOGLE_API_KEY"))
for m in gai.list_models():
    if "flash" in m.name:
        print(m.name)
