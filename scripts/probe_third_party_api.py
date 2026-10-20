"""Non-trading smoke test for the optional third-party Responses provider."""
import json
import os
import sys
import urllib.error
import urllib.request

def main():
    key = os.getenv("THIRD_PARTY_API_KEY", "").strip()
    if not key:
        print("THIRD_PARTY PROBE: FAIL missing secret")
        return 1
    base = "https://www.ainipy.com/api/desktop/v1"
    payload = json.dumps({
        "model": "gpt-5.6-sol",
        "input": "Reply with exactly OK.",
        "max_output_tokens": 64,
        "store": False,
    }).encode()
    request = urllib.request.Request(base + "/responses", data=payload, method="POST", headers={
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-OpenAI-Actor-Authorization": "b2-desktop-runtime-v1",
    })
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            data = json.load(response)
        if not isinstance(data, dict):
            raise ValueError("Expected JSON object")
        content = data.get("output_text") or "".join(
            part.get("text", "")
            for item in data.get("output", [])
            if isinstance(item, dict)
            for part in item.get("content", [])
            if isinstance(part, dict) and part.get("type") == "output_text"
        )
        if not isinstance(content, str) or not content.strip():
            raise ValueError("No output text in Responses payload")
        print(f"THIRD_PARTY PROBE: PASS model_response_present=true text_length={len(content)}")
        return 0
    except urllib.error.HTTPError as exc:
        print(f"THIRD_PARTY PROBE: FAIL http_status={exc.code}")
    except Exception as exc:
        print(f"THIRD_PARTY PROBE: FAIL error_type={type(exc).__name__}")
    return 1

if __name__ == "__main__":
    sys.exit(main())
