from dotenv import load_dotenv
import os
import requests
import json

load_dotenv()

payload = {
    "model": os.getenv("OPENROUTER_MODEL"),
    "messages": [
        {
            "role": "user",
            "content": 'Return exactly this JSON: {"status":"READY"}'
        }
    ],
    "stream": False,
    "temperature": 0,
    "response_format": {
        "type": "json_object"
    }
}

response = requests.post(
    "https://openrouter.ai/api/v1/chat/completions",
    headers={
        "Authorization": "Bearer " + os.environ["OPENROUTER_API_KEY"],
        "Content-Type": "application/json",
    },
    json=payload,
    timeout=180,
)

print("STATUS:", response.status_code)
print(json.dumps(response.json(), indent=2, ensure_ascii=False))
