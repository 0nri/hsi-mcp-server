#!/usr/bin/env python3
"""HSI MCP Server main entry point.

This module provides the main entry point for the HSI MCP server,
implementing FastMCP tools for retrieving Hang Seng Index data,
news summaries, and stock quotes from AAStocks.
"""

import json
import logging
import os
import sys
from functools import wraps
from typing import Any, Callable, Dict, Optional

from cachetools import TTLCache
from dotenv import load_dotenv
from mcp.server import FastMCP

from .gemini_client import GeminiClient
from .scraper_index import HSIDataScraper
from .scraper_quote import StockQuoteScraper

load_dotenv()

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)],
)
logger = logging.getLogger("hsi_server")

# Initialize service components
scraper = HSIDataScraper()
quote_scraper = StockQuoteScraper()
gemini_client: GeminiClient | None = None

# Cache configuration
CACHE_ENABLED = os.getenv("CACHE_ENABLED", "false").lower() == "true"
CACHE_TTL_SECONDS = int(os.getenv("CACHE_TTL_SECONDS", "60"))

# Initialize cache if enabled
cache: Optional[TTLCache] = None
if CACHE_ENABLED:
    cache = TTLCache(maxsize=100, ttl=CACHE_TTL_SECONDS)
    logger.info(f"Cache enabled with TTL {CACHE_TTL_SECONDS} seconds")
else:
    logger.info("Cache disabled")


def cache_if_enabled(key_func: Callable[..., str]) -> Callable[[Callable[..., str]], Callable[..., str]]:
    """Decorator to cache function results if caching is enabled.

    Args:
        key_func: Function that takes the same arguments as the decorated function
                 and returns a cache key string

    Returns:
        Decorator function
    """

    def decorator(func: Callable[..., str]) -> Callable[..., str]:
        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> str:
            # If cache is disabled, call function directly
            if not CACHE_ENABLED or cache is None:
                return func(*args, **kwargs)

            # Generate cache key
            try:
                cache_key = key_func(*args, **kwargs)
            except Exception as e:
                logger.warning(f"Failed to generate cache key for {func.__name__}: {e}")
                return func(*args, **kwargs)

            # Check cache first
            try:
                if cache_key in cache:
                    logger.debug(f"Cache hit for {func.__name__} with key: {cache_key}")
                    return cache[cache_key]
            except Exception as e:
                logger.warning(f"Cache read failed for {func.__name__}: {e}")

            # Cache miss - call function
            logger.debug(f"Cache miss for {func.__name__} with key: {cache_key}")
            result = func(*args, **kwargs)

            # Only cache successful responses
            try:
                response_data = json.loads(result)
                if response_data.get("success", False):
                    cache[cache_key] = result
                    logger.debug(
                        f"Cached result for {func.__name__} with key: {cache_key}"
                    )
                else:
                    logger.debug(f"Not caching failed response for {func.__name__}")
            except (json.JSONDecodeError, Exception) as e:
                logger.warning(
                    f"Failed to parse response for caching {func.__name__}: {e}"
                )

            return result

        return wrapper

    return decorator


def _create_json_response(success: bool, data: Any = None, error: Optional[str] = None) -> str:
    """Create standardized JSON response format.

    Args:
        success: Whether the operation was successful
        data: Response data (only included if success=True)
        error: Error message (only included if success=False)

    Returns:
        JSON string with standardized response format
    """
    response: Dict[str, Any] = {"success": success}
    if success and data is not None:
        response["data"] = data
    elif not success and error:
        response["error"] = error
    return json.dumps(response, indent=2)


def get_gemini_client() -> GeminiClient:
    """Initialize and return singleton GeminiClient instance.

    Returns:
        GeminiClient: Configured Gemini client instance

    Raises:
        Exception: If client initialization fails
    """
    global gemini_client
    if gemini_client is None:
        try:
            gemini_client = GeminiClient()
            logger.debug("Successfully initialized Gemini client")
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            raise
    return gemini_client


mcp = FastMCP("HSI MCP Server")


@mcp.tool()
@cache_if_enabled(key_func=lambda: "hsi_data")
def get_hsi_data() -> str:
    """Get current Hang Seng Index data including point, daily change, turnover, and timestamp.

    Returns:
        JSON string containing HSI data with fields:
        - current_point: Current index value
        - daily_change_point: Point change from previous close
        - daily_change_percent: Percentage change from previous close
        - turnover: Total market turnover in HKD
        - timestamp: Data timestamp in ISO format
        - source: Data source identifier
        - url: Source URL
    """
    try:
        logger.debug("Fetching HSI data from scraper")
        hsi_data = scraper.get_hsi_data()
        return _create_json_response(success=True, data=hsi_data)
    except Exception as e:
        logger.error(f"Failed to get HSI data: {e}", exc_info=True)
        return _create_json_response(
            success=False, error=f"Failed to retrieve HSI data: {str(e)}"
        )


@mcp.tool()
@cache_if_enabled(key_func=lambda limit=10: f"hsi_news_{limit}")
def get_hsi_news_summary(limit: int = 10) -> str:
    """Get top news headlines with an AI-generated summary.

    Args:
        limit: Maximum number of headlines to retrieve (default: 10, max: 20)

    Returns:
        JSON string containing news data with fields:
        - headlines: List of news headlines with URLs
        - summary: AI-generated summary of market themes
        - count: Number of headlines retrieved
        - timestamp: Data collection timestamp
    """
    try:
        logger.debug(f"Fetching {limit} news headlines")
        headlines = scraper.get_news_headlines(limit)

        if not headlines:
            logger.warning("No headlines found")
            no_news_data = {
                "headlines": [],
                "summary": "No headlines available at this time.",
                "count": 0,
            }
            return _create_json_response(success=True, data=no_news_data)

        # Generate AI summary with fallback
        try:
            client = get_gemini_client()
            summary = client.summarize_headlines(headlines)
            logger.debug("Successfully generated AI summary")
        except Exception as e:
            logger.error(f"Failed to generate AI summary: {e}", exc_info=True)
            summary = f"Unable to generate AI summary. Found {len(headlines)} headlines related to Hong Kong financial markets."

        # Get timestamp from HSI data
        try:
            hsi_data = scraper.get_hsi_data()
            timestamp = hsi_data.get("timestamp")
        except Exception as e:
            logger.warning(f"Could not get timestamp from HSI data: {e}")
            timestamp = None

        response_data = {
            "headlines": headlines,
            "summary": summary,
            "count": len(headlines),
            "timestamp": timestamp,
        }

        return _create_json_response(success=True, data=response_data)
    except Exception as e:
        logger.error(f"Failed to get news summary: {e}", exc_info=True)
        return _create_json_response(
            success=False, error=f"Failed to retrieve news summary: {str(e)}"
        )


@mcp.tool()
@cache_if_enabled(
    key_func=lambda symbol_or_company: f"stock_quote_{symbol_or_company.strip()}"
)
def get_stock_quote(symbol_or_company: str) -> str:
    """Get current stock quote data for a Hong Kong listed company by symbol or company name.

    Args:
        symbol_or_company: Either a HK stock symbol (e.g., "00005", "388") or company name (e.g., "HSBC")

    Returns:
        JSON string containing stock data with fields:
        - symbol: Formatted 5-digit stock symbol
        - company_name: Company name (if available)
        - current_price: Current stock price in HKD
        - price_change: Price change from previous close
        - price_change_percent: Percentage change from previous close
        - turnover: Trading volume with unit
        - last_updated_time: Last update timestamp
        - source: Data source identifier
        - url: Source URL
    """
    try:
        input_cleaned = symbol_or_company.strip()

        # Determine input type: numeric symbol vs company name
        company_name = None
        if any(char.isdigit() for char in input_cleaned):
            symbol = input_cleaned
            logger.debug(f"Processing as stock symbol: {symbol}")
        else:
            logger.debug(f"Processing as company name: {input_cleaned}")
            try:
                client = get_gemini_client()
                lookup_result = client.lookup_stock_symbol(input_cleaned)
                if not lookup_result:
                    return _create_json_response(
                        success=False,
                        error=f"Could not find Hong Kong stock symbol for company: {input_cleaned}",
                    )
                symbol = lookup_result["symbol"]
                company_name = lookup_result["company_name"]
                logger.info(
                    f"Symbol lookup successful: {input_cleaned} -> {symbol} ({company_name})"
                )
            except Exception as e:
                logger.error(f"Symbol lookup failed for {input_cleaned}: {e}")
                return _create_json_response(
                    success=False,
                    error=f"Failed to lookup stock symbol for company '{input_cleaned}': {str(e)}",
                )

        # Retrieve stock quote data
        logger.debug(f"Fetching quote data for symbol: {symbol}")
        quote_data = quote_scraper.get_stock_quote(symbol, company_name=company_name)
        return _create_json_response(success=True, data=quote_data)

    except Exception as e:
        logger.error(
            f"Failed to get stock quote for {symbol_or_company}: {e}", exc_info=True
        )
        return _create_json_response(
            success=False, error=f"Failed to retrieve stock quote: {str(e)}"
        )


# --- Main Entry Point ---
def main_entry() -> None:
    """Main entry point for the HSI MCP server using Streamable HTTP transport."""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logger.error("GOOGLE_CLOUD_PROJECT environment variable is required")
        sys.exit(1)

    logger.info(
        f"Starting HSI MCP Server with Streamable HTTP transport (project: {project_id})"
    )

    # Configure server host and port
    port = int(os.getenv("PORT", "8080"))
    host = os.getenv("HOST", "0.0.0.0")

    # Configure FastMCP settings
    mcp.settings.host = host
    mcp.settings.port = port

    logger.info(f"HSI MCP Server running on http://{host}:{port}/mcp")

    try:
        # Use FastMCP's built-in streamable HTTP transport
        mcp.run(transport="streamable-http")
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main_entry()
