"""Safe AI-provider diagnostics for the paper-trading runner.

This script never places trades. It checks provider SDKs, configured model names,
and performs a minimal text-generation probe so provider failures are visible
before the long TradingAgents pipeline begins.

For paper trading, Gemini is the required provider while OpenAI credits are
currently exhausted. OpenAI failures are therefore reported as warnings rather
than blocking the paper pipeline. Gemini failures remain fatal.
"""

from __future__ import annotations

import importlib.metadata
import os


def _version(package: str) -> str:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return "not-installed"


def _has(name: str) -> bool:
    return bool(os.getenv(name, "").strip())


def main() -> int:
    print("AI PROVIDER DIAGNOSTICS")
    print(f"tradingagents version: {_version('tradingagents')}")
    print(f"langchain version: {_version('langchain')}")
    print(f"langchain-openai version: {_version('langchain-openai')}")
    print(f"langchain-google-genai version: {_version('langchain-google-genai')}")
    print(f"openai version: {_version('openai')}")
    print(f"google-genai version: {_version('google-genai')}")

    openai_key = _has("OPENAI_API_KEY")
    gemini_key = _has("GEMINI_API_KEY") or _has("GOOGLE_API_KEY")
    print(f"OpenAI key configured: {openai_key}")
    print(f"Gemini/Google key configured: {gemini_key}")
    print(
        "OpenAI models: "
        f"deep={os.getenv('TRADINGAGENTS_DEEP_THINK_LLM', 'gpt-4.1')} "
        f"quick={os.getenv('TRADINGAGENTS_QUICK_THINK_LLM', 'gpt-4.1-mini')}"
    )
    print(
        "Gemini models: "
        f"deep={os.getenv('GEMINI_DEEP_THINK_LLM', 'gemini-3.1-flash-lite')} "
        f"quick={os.getenv('GEMINI_QUICK_THINK_LLM', 'gemini-3.1-flash-lite')}"
    )

    if openai_key:
        try:
            from langchain_openai import ChatOpenAI

            model = os.getenv("TRADINGAGENTS_QUICK_THINK_LLM", "gpt-4.1-mini")
            print(f"OPENAI PROBE: starting model={model}")
            response = ChatOpenAI(model=model, timeout=20, max_retries=0).invoke(
                "Reply with exactly: OK"
            )
            print(f"OPENAI PROBE: PASS response={str(response.content)[:120]!r}")
        except Exception as exc:
            print(
                "OPENAI PROBE: WARN "
                f"type={type(exc).__name__} message={str(exc)[:1000]!r}"
            )
    else:
        print("OPENAI PROBE: SKIPPED (no key configured)")

    if not gemini_key:
        print("GEMINI PROBE: FAIL no Gemini/Google API key configured")
        print("AI PROVIDER DIAGNOSTICS: FAIL (Gemini is required for paper trading)")
        return 1

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI

        model = os.getenv("GEMINI_QUICK_THINK_LLM", "gemini-3.1-flash-lite")
        print(f"GEMINI PROBE: starting model={model}")
        response = ChatGoogleGenerativeAI(model=model, timeout=20, max_retries=0).invoke(
            "Reply with exactly: OK"
        )
        print(f"GEMINI PROBE: PASS response={str(response.content)[:120]!r}")
    except Exception as exc:
        print(
            "GEMINI PROBE: FAIL "
            f"type={type(exc).__name__} message={str(exc)[:1000]!r}"
        )
        print("AI PROVIDER DIAGNOSTICS: FAIL (Gemini probe failed)")
        return 1

    print("AI PROVIDER DIAGNOSTICS: PASS (Gemini required; OpenAI optional)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
