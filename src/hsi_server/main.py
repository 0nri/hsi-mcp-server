#!/usr/bin/env python3
"""HSI MCP Server main entry point."""

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional, Union

from dotenv import load_dotenv
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)

from .gemini_client import GeminiClient
from .scraper import HSIDataScraper

# Load environment variables
load_dotenv()

# Configure logging
log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger("hsi_server")


class HSIServer:
    """HSI MCP Server implementation."""
    
    def __init__(self) -> None:
        self.server = Server("hsi-mcp-server")
        self.scraper = HSIDataScraper()
        self.gemini_client = None  # Initialize lazily to avoid startup errors
        
        # Set up handlers
        self._setup_handlers()
        
        logger.info("HSI MCP Server initialized")
    
    def _get_gemini_client(self) -> GeminiClient:
        """Get Gemini client, initializing if needed."""
        if self.gemini_client is None:
            try:
                self.gemini_client = GeminiClient()
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
                raise RuntimeError(f"Gemini client initialization failed: {e}")
        return self.gemini_client
    
    def _setup_handlers(self) -> None:
        """Set up MCP request handlers."""
        
        @self.server.list_tools()
        async def list_tools() -> List[Tool]:
            """List available tools."""
            return [
                Tool(
                    name="get_hsi_data",
                    description="Get current Hang Seng Index data including current point, daily change (point and percentage), turnover, and timestamp",
                    inputSchema={
                        "type": "object",
                        "properties": {},
                        "required": []
                    }
                ),
                Tool(
                    name="get_hsi_news_summary",
                    description="Get top news headlines that may impact HSI and provide an AI-generated summary",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "limit": {
                                "type": "integer",
                                "description": "Number of headlines to fetch (1-20, default: 10)",
                                "minimum": 1,
                                "maximum": 20,
                                "default": 10
                            }
                        },
                        "required": []
                    }
                )
            ]
        
        @self.server.call_tool()
        async def call_tool(name: str, arguments: Optional[Dict[str, Any]]) -> List[TextContent]:
            """Handle tool calls."""
            try:
                if name == "get_hsi_data":
                    return await self._handle_get_hsi_data()
                elif name == "get_hsi_news_summary":
                    limit = (arguments or {}).get("limit", 10)
                    return await self._handle_get_hsi_news_summary(limit)
                else:
                    raise ValueError(f"Unknown tool: {name}")
            
            except Exception as e:
                logger.error(f"Error handling tool {name}: {e}")
                error_response = {
                    "success": False,
                    "error": str(e),
                    "message": f"Failed to execute tool {name}"
                }
                return [TextContent(
                    type="text",
                    text=json.dumps(error_response, indent=2, ensure_ascii=False)
                )]
    
    async def _handle_get_hsi_data(self) -> List[TextContent]:
        """Handle get_hsi_data tool call."""
        logger.info("Handling get_hsi_data request")
        
        try:
            # Run the scraping in a thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            hsi_data = await loop.run_in_executor(None, self.scraper.get_hsi_data)
            
            # Format the response
            response_data = {
                "success": True,
                "data": hsi_data,
                "message": "HSI data retrieved successfully"
            }
            
            logger.info("Successfully retrieved HSI data")
            return [TextContent(
                type="text",
                text=json.dumps(response_data, indent=2, ensure_ascii=False)
            )]
            
        except Exception as e:
            logger.error(f"Failed to get HSI data: {e}")
            error_response = {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve HSI data"
            }
            return [TextContent(
                type="text",
                text=json.dumps(error_response, indent=2, ensure_ascii=False)
            )]
    
    async def _handle_get_hsi_news_summary(self, limit: int = 10) -> List[TextContent]:
        """Handle get_hsi_news_summary tool call."""
        logger.info(f"Handling get_hsi_news_summary request with limit={limit}")
        
        try:
            # Validate limit
            limit = max(1, min(limit, 20))
            
            # Run the scraping in a thread pool
            loop = asyncio.get_event_loop()
            headlines = await loop.run_in_executor(
                None, self.scraper.get_news_headlines, limit
            )
            
            if not headlines:
                logger.warning("No headlines found")
                response_data = {
                    "success": True,
                    "data": {
                        "headlines": [],
                        "summary": "No headlines available at this time.",
                        "count": 0
                    },
                    "message": "No headlines found"
                }
                return [TextContent(
                    type="text",
                    text=json.dumps(response_data, indent=2, ensure_ascii=False)
                )]
            
            # Generate summary using Gemini
            try:
                gemini_client = self._get_gemini_client()
                summary = await loop.run_in_executor(
                    None, gemini_client.summarize_headlines, headlines
                )
            except Exception as e:
                logger.error(f"Failed to generate AI summary: {e}")
                # Use fallback summary
                summary = f"Unable to generate AI summary. Found {len(headlines)} headlines related to Hong Kong financial markets."
            
            # Format the response
            response_data = {
                "success": True,
                "data": {
                    "headlines": headlines,
                    "summary": summary,
                    "count": len(headlines),
                    "timestamp": self.scraper.get_hsi_data()["timestamp"]  # Get current timestamp
                },
                "message": f"Retrieved {len(headlines)} headlines with AI summary"
            }
            
            logger.info(f"Successfully retrieved {len(headlines)} headlines with summary")
            return [TextContent(
                type="text",
                text=json.dumps(response_data, indent=2, ensure_ascii=False)
            )]
            
        except Exception as e:
            logger.error(f"Failed to get news summary: {e}")
            error_response = {
                "success": False,
                "error": str(e),
                "message": "Failed to retrieve news headlines and summary"
            }
            return [TextContent(
                type="text",
                text=json.dumps(error_response, indent=2, ensure_ascii=False)
            )]


async def main() -> None:
    """Main entry point for the HSI MCP server."""
    
    # Validate required environment variables
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logger.error("GOOGLE_CLOUD_PROJECT environment variable is required")
        sys.exit(1)
    
    logger.info(f"Starting HSI MCP Server (project: {project_id})")
    
    try:
        # Create and run the server
        hsi_server = HSIServer()
        
        # Run the server with stdio transport
        async with stdio_server() as (read_stream, write_stream):
            await hsi_server.server.run(
                read_stream,
                write_stream,
                hsi_server.server.create_initialization_options()
            )
    
    except KeyboardInterrupt:
        logger.info("Server shutdown requested")
    except Exception as e:
        logger.error(f"Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    # Ensure we're running in the correct environment
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        logger.error("Please set up your .env file with required variables")
        logger.error("Copy .env.example to .env and fill in your values")
        sys.exit(1)
    
    # Run the server
    asyncio.run(main())
