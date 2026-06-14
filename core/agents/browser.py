import argparse
import json
import os
import re
import sys
import textwrap
from datetime import datetime, timezone
from typing import Any

import requests
from dotenv import load_dotenv
from duckduckgo_search import DDGS

load_dotenv()

try:
    import trafilatura
    HAVE_TRAFILATURA = True
except ImportError:
    HAVE_TRAFILATURA = False

from bs4 import BeautifulSoup

OLLAMA_BASE_URL   = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL     = os.getenv("OLLAMA_DEFAULT_MODEL", "llama3.2:latest")
DEFAULT_N_RESULTS = 5
FETCH_TIMEOUT     = 10          
MAX_PAGE_CHARS    = 4000        
REQUEST_HEADERS   = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/123.0 Safari/537.36"
    )
}

def ollama_chat(messages: list[dict], model: str) -> str:
    payload = {
        "model": model, 
        "messages": messages, 
        "stream": False
    }
    try:
        resp = requests.post(f"{OLLAMA_BASE_URL}/api/chat", json=payload, timeout=180)
        resp.raise_for_status()
        return resp.json()["message"]["content"]
    except requests.exceptions.ConnectionError:
        sys.exit("[ERROR] Cannot reach Ollama at localhost:11434. Make sure 'ollama serve' is running.")

def search_web(query: str, max_results: int = DEFAULT_N_RESULTS) -> list[dict]:
    results = []
    with DDGS() as ddgs:
        for r in ddgs.text(query, max_results=max_results):
            results.append({
                "title":   r.get("title", ""),
                "url":     r.get("href", r.get("link", "")),
                "snippet": r.get("body", ""),
            })
    return results

def fetch_page_text(url: str, max_chars: int = MAX_PAGE_CHARS) -> str:
    try:
        resp = requests.get(url, headers=REQUEST_HEADERS, timeout=FETCH_TIMEOUT)
        resp.raise_for_status()
        html = resp.text
    except Exception:
        return ""

    text = ""
    if HAVE_TRAFILATURA:
        try:
            text = trafilatura.extract(html) or ""
        except Exception:
            text = ""

    if not text:
        try:
            soup = BeautifulSoup(html, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            text = " ".join(soup.get_text(separator=" ").split())
        except Exception:
            text = ""

    return text[:max_chars]

def enrich_results(results: list[dict], fetch: bool = True) -> list[dict]:
    if not fetch:
        for r in results:
            r["content"] = ""
        return results

    for r in results:
        print(f"[Agent] Fetching: {r['url']}")
        r["content"] = fetch_page_text(r["url"])
    return results

def _build_source_blob(results: list[dict]) -> str:
    parts = []
    for i, r in enumerate(results, 1):
        body = r["content"] or r["snippet"]
        parts.append(
            f"--- SOURCE {i} ---\n"
            f"Title:   {r['title']}\n"
            f"URL:     {r['url']}\n"
            f"Snippet: {r['snippet']}\n"
            f"Content (excerpt): {body[:2000]}"
        )
    return "\n\n".join(parts)

def synthesize(query: str, results: list[dict], model: str) -> dict:
    system_prompt = textwrap.dedent("""
        You are a research assistant. You are given a user query and a set of
        web sources (title, url, snippet, content excerpt).

        Using ONLY the information in these sources:
          1. Write a clear, direct "answer" to the query (2-5 sentences).
          2. Extract 3-7 "key_points" as short factual bullet strings.
          3. For each source, note its "relevance" (1 short sentence: how it
             relates to the query). Use the URL given for each.

        Return ONLY a single JSON object, no markdown, no prose, with this shape:
        {
          "answer": "...",
          "key_points": ["...", "..."],
          "sources": [
            {"title": "...", "url": "...", "relevance": "..."}
          ]
        }

        If sources conflict, mention the disagreement in "answer".
        If sources don't actually answer the query, say so honestly in "answer".
    """).strip()

    user_prompt = f"QUERY: {query}\n\n{_build_source_blob(results)}"

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user",   "content": user_prompt},
    ]
    raw = ollama_chat(messages, model)
    raw = re.sub(r"```json|```", "", raw).strip()

    try:
        return json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Ollama returned invalid JSON for synthesis:\n{raw}") from exc

def run_agent(
    query: str,
    model: str = DEFAULT_MODEL,
    max_results: int = DEFAULT_N_RESULTS,
    fetch_pages: bool = True,
) -> dict[str, Any]:
    print(f"[Agent] Searching DuckDuckGo for: {query!r}")
    results = search_web(query, max_results=max_results)
    print(f"[Agent] Found {len(results)} result(s).")

    results = enrich_results(results, fetch=fetch_pages)

    print(f"[Agent] Synthesizing with Ollama ({model}) ...")
    synthesis = synthesize(query, results, model)

    return {
        "query":        query,
        "timestamp":    datetime.now(timezone.utc).isoformat(),
        "result_count": len(results),
        "synthesis":    synthesis,
        "raw_results":  results,
    }

def main():
    parser = argparse.ArgumentParser(description="Web research agent (DuckDuckGo + local Ollama)")
    parser.add_argument("--model",    default=DEFAULT_MODEL, help=f"Ollama model name (default: {DEFAULT_MODEL})")
    parser.add_argument("--results",  type=int, default=DEFAULT_N_RESULTS, help="Number of search results to use")
    parser.add_argument("--no-fetch", action="store_true", help="Skip fetching full page content (snippets only)")
    parser.add_argument("--no-raw",   action="store_true", help="Omit raw_results from output JSON")
    parser.add_argument("--output",   default=None, help="Write JSON result to this file")
    args = parser.parse_args()

    print("Web Agent  |  type 'exit' or Ctrl-C to quit\n")

    while True:
        try:
            query = input("You: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\nBye!")
            break

        if not query:
            continue
        if query.lower() in {"exit", "quit", "q"}:
            print("Bye!")
            break

        try:
            result = run_agent(
                query,
                model=args.model,
                max_results=args.results,
                fetch_pages=not args.no_fetch,
            )

            if args.no_raw:
                result.pop("raw_results", None)

            pretty = json.dumps(result, indent=2, ensure_ascii=True)
            print("\n-- Agent Response -------------------------------------")
            print(pretty)
            print("-------------------------------------------------------\n")

            if args.output:
                with open(args.output, "w") as fh:
                    fh.write(pretty)
                print(f"[Agent] Result written to {args.output}\n")

        except Exception as exc:
            clean_exc = str(exc).encode('ascii', 'ignore').decode('ascii')
            print(f"[ERROR] {clean_exc}\n")

if __name__ == "__main__":
    main()