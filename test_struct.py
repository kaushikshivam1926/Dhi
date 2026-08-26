import json
import os
from google import genai

config_path = os.path.join(os.path.dirname(__file__), 'config.json')
with open(config_path, 'r') as f:
    config = json.load(f)

gemini_key = config.get("api_keys", {}).get("gemini", "")
gemini_model = config.get("gemini_model", "gemini-1.5-flash")

client = genai.Client(api_key=gemini_key)
prompt = "You are an expert editor. Please format and restructure the following raw OCR text (from a newspaper/document) into clean, readable Markdown. Fix broken columns, merge broken sentences, add logical headings, and remove random page numbers or footer artifacts. Do not summarize or omit information; preserve the full article content. Output only the Markdown.\n\nRAW TEXT:\nFINANCIAL TIMES\nFRIDAY I MAY ZUZO\nThe new golden age of space exploration\nBIG READ, PAGE 13\nUSA $3.00\nCan trade maintain peace in the world?"

print(f"Testing model: {gemini_model}")
try:
    response = client.models.generate_content(
        model=gemini_model,
        contents=prompt
    )
    print(f"Response Object: {response}")
    print(f"Response Text: {response.text}")
except Exception as e:
    print(f"Exception: {e}")
