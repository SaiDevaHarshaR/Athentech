"""
Tests your Tavily web-search setup directly, outside of the agent, so
any failure shows up clearly instead of being silently swallowed into
"No relevant information found."

Run:
    python check_tavily.py
"""

from config import settings

key = settings.tavily_api_key
print("TAVILY_API_KEY =", f"<{len(key)} chars>" if key else "<EMPTY - not set in .env>")

if not key:
    print("\nNothing to test — TAVILY_API_KEY is empty. Add it to your .env:")
    print("  TAVILY_API_KEY=your_real_key_here")
    print("Get a key at https://tavily.com if you don't have one.")
    raise SystemExit(0)

from tavily import TavilyClient

try:
    client = TavilyClient(api_key=key)
    response = client.search(query="good hospitals in Malkajgiri", search_depth="basic", max_results=3)
    print("\n✅ Tavily search succeeded.")
    print("Answer:", response.get("answer"))
    print("Results found:", len(response.get("results", [])))
except Exception as e:
    print("\n❌ Tavily search failed:")
    print(type(e).__name__, "-", e)