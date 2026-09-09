import os
import json
import time
import requests
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("OLLAMA_API_KEY")

print("Key loaded:", bool(api_key))
print("Key length:", len(api_key) if api_key else 0)
print("Key prefix:", api_key[:8] if api_key else "")

url = "https://ollama.com/api/generate"

payload = {
    "model": "gpt-oss:20b",
    "prompt": 'Return only this JSON object: {"ok":true}',
    "stream": False,
    "think": False,
}

headers = {
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json",
}

print("\nPOST", url)
print("Model:", payload["model"])

started = time.time()

try:
    response = requests.post(
        url,
        headers=headers,
        json=payload,
        timeout=120,
    )

    elapsed = time.time() - started

    print("Elapsed:", round(elapsed, 2), "sec")
    print("HTTP status:", response.status_code)
    print("Response headers:", dict(response.headers))
    print("\nResponse:")
    print(response.text)

except Exception as e:
    elapsed = time.time() - started

    print("Elapsed:", round(elapsed, 2), "sec")
    print("EXCEPTION TYPE:", type(e).__name__)
    print("EXCEPTION:", str(e))