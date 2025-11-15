import os
import time
import json
from typing import Dict, Any, Optional
import requests


class GeminiClient:
    def __init__(self):
        self.api_key = os.getenv('GEMINI_API_KEY')
        self.model = os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')
        self.endpoint = os.getenv('GEMINI_ENDPOINT', 'https://generativelanguage.googleapis.com/v1beta/models')

    def enabled(self) -> bool:
        return bool(self.api_key)

    def score_metrics(self, role: str, summary: Dict[str, Any], weights: Optional[Dict[str, float]] = None) -> Dict[str, Any]:
        if not self.enabled():
            return {'enabled': False}
        weights = weights or {}
        schema_hint = {
            "score": "integer 0-100",
            "grade": "string one of [A, B, C, D, E, F]",
            "notes": "short string guidance",
            "rationale": "concise string explaining how metrics and weights influenced the score"
        }
        prompt = (
            "You are a performance evaluator. Return STRICT JSON only, no prose. "
            f"Schema: {json.dumps(schema_hint)}. Score 0-100, reflect role and weights.\n"
            f"Role: {role}\n"
            f"Weights: {json.dumps(weights, ensure_ascii=False)}\n"
            f"Metrics: {json.dumps(summary, ensure_ascii=False)}\n"
        )
        url = f"{self.endpoint}/{self.model}:generateContent"
        body = {'contents': [{'parts': [{'text': prompt}]}]}
        headers = {"x-goog-api-key": self.api_key, "Content-Type": "application/json"}
        # simple retry
        last_err = None
        for _ in range(2):
            try:
                r = requests.post(url, json=body, headers=headers, timeout=15)
                r.raise_for_status()
                data = r.json()
                text = data.get('candidates', [{}])[0].get('content', {}).get('parts', [{}])[0].get('text', '')
                parsed = None
                try:
                    parsed = json.loads(text)
                except Exception:
                    # try to extract JSON block if the model added extra text
                    start = text.find('{')
                    end = text.rfind('}')
                    if start != -1 and end != -1 and end > start:
                        parsed = json.loads(text[start:end+1])
                if parsed and isinstance(parsed, dict) and 'score' in parsed:
                    return {'enabled': True, 'ok': True, 'data': parsed}
                return {'enabled': True, 'ok': False, 'raw': data, 'text': text}
            except Exception as e:
                last_err = str(e)
                time.sleep(1.0)
        return {'enabled': True, 'ok': False, 'error': last_err}
