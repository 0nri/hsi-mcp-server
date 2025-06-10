#!/usr/bin/env python3
"""HSI MCP Server main entry point."""

import json
import logging
import os
import sys

from dotenv import load_dotenv
from mcp.server import FastMCP

from .gemini_client import GeminiClient
from .scraper_index import HSIDataScraper
from .scraper_quote import StockQuoteScraper

load_dotenv()

log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger("hsi_server")

scraper = HSIDataScraper()
quote_scraper = StockQuoteScraper()
gemini_client: GeminiClient | None = None

def get_gemini_client() -> GeminiClient:
    """Initialize and return singleton GeminiClient instance."""
    global gemini_client
    if gemini_client is None:
        try:
            gemini_client = GeminiClient()
        except Exception as e:
            logger.error(f"Failed to initialize Gemini client: {e}")
            raise e
    return gemini_client

mcp = FastMCP("HSI MCP Server")

@mcp.tool()
def get_hsi_data() -> str:
    """Get current Hang Seng Index data including point, daily change, turnover, and timestamp"""
    try:
        hsi_data = scraper.get_hsi_data()
        return json.dumps({
            "success": True,
            "data": hsi_data
        }, indent=2)
    except Exception as e:
        logger.error(f"Failed to get HSI data: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e)
        }, indent=2)

@mcp.tool()
def get_hsi_news_summary(limit: int = 10) -> str:
    """Get top news headlines with an AI-generated summary"""
    try:
        headlines = scraper.get_news_headlines(limit)
        
        if not headlines:
            logger.warning("No headlines found")
            return json.dumps({
                "success": True,
                "data": {
                    "headlines": [],
                    "summary": "No headlines available at this time.",
                    "count": 0
                }
            }, indent=2)

        try:
            client = get_gemini_client()
            summary = client.summarize_headlines(headlines)
        except Exception as e:
            logger.error(f"Failed to generate AI summary: {e}", exc_info=True)
            summary = f"Unable to generate AI summary. Found {len(headlines)} headlines related to Hong Kong financial markets."
        
        hsi_data = scraper.get_hsi_data()
        timestamp = hsi_data.get("timestamp")

        response_data = {
            "headlines": headlines,
            "summary": summary,
            "count": len(headlines),
            "timestamp": timestamp,
        }
        
        return json.dumps({
            "success": True,
            "data": response_data
        }, indent=2)
    except Exception as e:
        logger.error(f"Failed to get news summary: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e)
        }, indent=2)

@mcp.tool()
def get_stock_quote(symbol_or_company: str) -> str:
    """Get current stock quote data for a Hong Kong listed company by symbol or company name"""
    try:
        # Determine if input is a company name or stock symbol
        input_cleaned = symbol_or_company.strip()
        
        # Check if input looks like a stock symbol (contains digits)
        if any(char.isdigit() for char in input_cleaned):
            # Treat as stock symbol
            symbol = input_cleaned
            logger.info(f"Treating input as stock symbol: {symbol}")
        else:
            # Treat as company name - use Gemini to look up symbol
            logger.info(f"Treating input as company name: {input_cleaned}")
            try:
                client = get_gemini_client()
                symbol = client.lookup_stock_symbol(input_cleaned)
                if not symbol:
                    return json.dumps({
                        "success": False,
                        "error": f"Could not find Hong Kong stock symbol for company: {input_cleaned}"
                    }, indent=2)
                logger.info(f"Found symbol {symbol} for company {input_cleaned}")
            except Exception as e:
                logger.error(f"Failed to lookup symbol for {input_cleaned}: {e}")
                return json.dumps({
                    "success": False,
                    "error": f"Failed to lookup stock symbol for company: {input_cleaned}. Error: {str(e)}"
                }, indent=2)
        
        # Get the stock quote data
        quote_data = quote_scraper.get_stock_quote(symbol)
        
        return json.dumps({
            "success": True,
            "data": quote_data
        }, indent=2)
        
    except Exception as e:
        logger.error(f"Failed to get stock quote for {symbol_or_company}: {e}", exc_info=True)
        return json.dumps({
            "success": False,
            "error": str(e)
        }, indent=2)

# --- Main Entry Point ---
def main_entry() -> None:
    """Main entry point for the HSI MCP server using Streamable HTTP transport."""
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logger.error("GOOGLE_CLOUD_PROJECT environment variable is required")
        sys.exit(1)

    logger.info(f"Starting HSI MCP Server with Streamable HTTP transport (project: {project_id})")
    
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
