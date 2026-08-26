import os
import json
from google import genai

config_path = os.path.join(os.path.dirname(__file__), 'config.json')
with open(config_path, 'r') as f:
    config = json.load(f)

api_key = config.get("api_keys", {}).get("gemini", "")
model_id = config.get("gemini_model", "gemini-1.5-flash")

print(f"Using model: {model_id}")

client = genai.Client(api_key=api_key)
pdf_path = "RawMaterials/FT US ³¹'⁰³'²⁰²⁶.pdf"

print("Uploading...")
myfile = client.files.upload(file=pdf_path)

print("Extracting...")
prompt = "Extract the complete text from the first page of this document. Do not summarize."
response = client.models.generate_content(
    model=model_id,
    contents=[prompt, myfile]
)

print(response.text)

try:
    client.files.delete(name=myfile.name)
except:
    pass
