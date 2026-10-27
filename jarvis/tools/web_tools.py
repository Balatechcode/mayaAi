"""
Web tools for Jarvis.
Provides website opening, live web searching, and real-time information lookup.
"""

import webbrowser
import urllib.parse
import urllib.request
import json
from jarvis.tools import tool

# Optional DuckDuckGo search import
try:
    from duckduckgo_search import DDGS
    _HAS_DDG = True
except ImportError:
    _HAS_DDG = False


@tool
def open_website(url: str) -> str:
    """
    Opens a website or web page in the user's default browser.
    
    Args:
        url: The web address to open (e.g., 'https://www.google.com', 'youtube.com', 'github.com').
    """
    clean_url = url.strip()
    if not clean_url.startswith(("http://", "https://")):
        clean_url = "https://" + clean_url

    try:
        success = webbrowser.open(clean_url)
        if success:
            return f"Successfully opened {clean_url} in your browser."
        return f"Browser launch triggered for {clean_url}."
    except Exception as e:
        return f"Failed to open website {clean_url}: {str(e)}"


@tool
def web_search(query: str, max_results: int = 4) -> str:
    """
    Searches the live web for current information, news, facts, or answers.
    
    Args:
        query: The search query string.
        max_results: Maximum number of search results to retrieve (default: 4).
    """
    clean_query = query.strip()
    if not clean_query:
        return "Search query cannot be empty."

    if _HAS_DDG:
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(clean_query, max_results=max_results))
                if not results:
                    return f"No web search results found for '{clean_query}'."

                formatted = []
                for i, r in enumerate(results, 1):
                    title = r.get("title", "No Title")
                    body = r.get("body", "No description available.")
                    href = r.get("href", "")
                    formatted.append(f"{i}. {title}\n   Summary: {body}\n   Source: {href}")
                return "\n\n".join(formatted)
        except Exception as e:
            # Fallback if DDG API temporarily throttles
            return f"Web search encountered an issue: {str(e)}. You can browse directly at: https://duckduckgo.com/?q={urllib.parse.quote_plus(clean_query)}"

    return f"Web search library not available. You can view results here: https://duckduckgo.com/?q={urllib.parse.quote_plus(clean_query)}"


@tool
def get_weather(city: str) -> str:
    """
    Fetches real-time weather information for any city or location.
    
    Args:
        city: The name of the city (e.g. 'Mumbai', 'London', 'New Delhi', 'Bangalore').
    """
    clean_city = city.strip()
    if not clean_city:
        return "Please specify a city name."

    # Using wttr.in format string for clean, fast weather data without API keys
    encoded_city = urllib.parse.quote(clean_city)
    url = f"https://wttr.in/{encoded_city}?format=%l:+%c+%t,+Humidity:+%h,+Wind:+%w"

    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "curl/7.68.0"}  # wttr.in gives concise text for curl
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            data = response.read().decode("utf-8").strip()
            return f"Weather report: {data}"
    except Exception as e:
        return f"Could not retrieve weather for '{clean_city}': {str(e)}"
