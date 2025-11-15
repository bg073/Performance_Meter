import os
import json
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv


def main():
    # Load .env from project root
    root = Path(__file__).parent
    load_dotenv(dotenv_path=root / '.env')

    api_key = os.getenv('GEMINI_API_KEY')
    model = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
    endpoint = os.getenv('GEMINI_ENDPOINT', 'https://generativelanguage.googleapis.com/v1beta/models')

    if not api_key:
        print('[error] GEMINI_API_KEY is not set. Create .env or set environment variable.')
        sys.exit(1)

    text = 'hi'
    if len(sys.argv) > 1:
        text = ' '.join(sys.argv[1:])

    url = f"{endpoint}/{model}:generateContent"
    headers = {"x-goog-api-key": api_key, "Content-Type": "application/json"}
    body = {"contents": [{"parts": [{"text": text}]}]}

    try:
        r = requests.post(url, headers=headers, json=body, timeout=20)
        print(r.status_code)
        try:
            data = r.json()
            print(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception:
            print(r.text)
            sys.exit(1)
    except Exception as e:
        print('[error] request failed:', e)
        sys.exit(1)


if __name__ == '__main__':
    main()
