from langchain_core.tools import tool
from tavily import TavilyClient
from config import settings

tavily_client = TavilyClient(api_key=settings.tavily_api_key)

@tool
def web_search(query: str) -> str:
    """
    Search the web for real-time information about hospitals, doctors, specialties, ratings etc.
    Use this tool when the user asks about specific hospitals, doctors, or current information.
    """
    try:
        response = tavily_client.search(
    query=query,
    search_depth="advanced",      
    max_results=8,                
    include_answer=True
)

        # Prefer the generated answer if available
        if response.get("answer"):
            return response["answer"]

        # Otherwise combine the top results
        results = []
        for r in response.get("results", [])[:4]:
            title = r.get("title", "")
            content = r.get("content", "")
            url = r.get("url", "")
            results.append(f"• {title}\n  {content}\n  Source: {url}")

        return "\n\n".join(results) if results else "No relevant results found."

    except Exception as e:
        return f"Search failed: {str(e)}"