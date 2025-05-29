#!/usr/bin/env python3
"""HSI MCP Server main entry point."""

import asyncio
import json
import logging
import os
import sys
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import (
    TextContent,
    Tool,
)
import uvicorn

from .gemini_client import GeminiClient
from .scraper import HSIDataScraper

load_dotenv()

log_level = os.getenv("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stderr)]
)
logger = logging.getLogger("hsi_server")

# --- Pydantic Models for FastAPI ---
class CallToolRequest(BaseModel):
    name: str
    arguments: Optional[Dict[str, Any]] = None

class HSIServer:
    """HSI MCP Server implementation."""
    
    def __init__(self) -> None:
        self.server = Server("hsi-mcp-server")
        self.scraper = HSIDataScraper()
        self.gemini_client = None  # Initialize lazily to avoid startup errors
        
        self._setup_mcp_handlers()
        
        logger.info("HSI MCP Server initialized")

    async def get_tool_definitions(self) -> List[Tool]:
        """Returns the list of tool definitions."""
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
    
    def _get_gemini_client(self) -> GeminiClient:
        """Get Gemini client, initializing if needed."""
        if self.gemini_client is None:
            try:
                self.gemini_client = GeminiClient()
            except Exception as e:
                logger.error(f"Failed to initialize Gemini client: {e}")
                raise RuntimeError(f"Gemini client initialization failed: {e}")
        return self.gemini_client
    
    def _setup_mcp_handlers(self) -> None:
        """Set up MCP request handlers."""
        
        @self.server.list_tools()
        async def mcp_sdk_list_tools_adapter() -> List[Tool]:
            """Adapter for MCP SDK to get tools via our method."""
            return await self.get_tool_definitions()
        
        # This decorator is for the MCP library's internal routing for stdio.
        # For FastAPI, we will call _execute_tool_logic directly.
        @self.server.call_tool()
        async def call_tool_handler(name: str, arguments: Optional[Dict[str, Any]]) -> List[TextContent]:
            """Handle tool calls via MCP library (stdio)."""
            return await self._execute_tool_logic(name, arguments)

    async def _execute_tool_logic(self, name: str, arguments: Optional[Dict[str, Any]]) -> List[TextContent]:
        """Core logic for executing a tool and handling errors."""
        try:
            if name == "get_hsi_data":
                return await self._handle_get_hsi_data()
            elif name == "get_hsi_news_summary":
                limit = (arguments or {}).get("limit", 10)
                return await self._handle_get_hsi_news_summary(limit)
            else:
                logger.error(f"Unknown tool requested: {name}")
                raise ValueError(f"Unknown tool: {name}")
        
        except Exception as e:
            logger.error(f"Error handling tool {name}: {e}")
            error_response = {
                "success": False,
                "error": str(e),
                "message": f"Failed to execute tool {name}"
            }
            # This format is for MCP TextContent
            return [TextContent(
                type="text",
                text=json.dumps(error_response, indent=2, ensure_ascii=False)
            )]

    async def _handle_get_hsi_data(self) -> List[TextContent]:
        """Handle get_hsi_data tool call."""
        logger.info("Handling get_hsi_data request")
        
        try:
            loop = asyncio.get_event_loop()
            hsi_data = await loop.run_in_executor(None, self.scraper.get_hsi_data)
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
            limit = max(1, min(limit, 20))
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
            
            try:
                gemini_client = self._get_gemini_client()
                summary = await loop.run_in_executor(
                    None, gemini_client.summarize_headlines, headlines
                )
            except Exception as e:
                logger.error(f"Failed to generate AI summary: {e}")
                summary = f"Unable to generate AI summary. Found {len(headlines)} headlines related to Hong Kong financial markets."
            
            response_data = {
                "success": True,
                "data": {
                    "headlines": headlines,
                    "summary": summary,
                    "count": len(headlines),
                    "timestamp": self.scraper.get_hsi_data()["timestamp"]
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

# --- FastAPI App Setup ---
app = FastAPI(title="HSI MCP Server", version="0.1.0")
hsi_mcp_server_instance: Optional[HSIServer] = None # Global instance

@app.on_event("startup")
async def startup_event():
    global hsi_mcp_server_instance
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logger.error("GOOGLE_CLOUD_PROJECT environment variable is required for FastAPI mode.")
        # This won't stop uvicorn but will log error. Consider raising if critical.
    hsi_mcp_server_instance = HSIServer()
    logger.info("FastAPI application startup: HSIServer instance created.")

@app.post("/mcp", response_model=List[TextContent])
async def mcp_call_tool_endpoint(request_body: CallToolRequest):
    """MCP tool call endpoint for HTTP transport."""
    if not hsi_mcp_server_instance:
        logger.error("HSIServer instance not available.")
        # Return a JSONResponse directly for FastAPI error handling
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "Server not initialized",
                "message": "HSIServer instance is not available. Check server logs."
            }
        )
    try:
        # Use the shared tool execution logic
        results: List[TextContent] = await hsi_mcp_server_instance._execute_tool_logic(
            request_body.name, request_body.arguments
        )
        # mcp.types.TextContent is a Pydantic model, so FastAPI can serialize List[TextContent].
        return results

    except ValueError as ve: # Specifically for "Unknown tool"
        logger.error(f"ValueError in /mcp endpoint: {ve}")
        return JSONResponse(
            status_code=400, # Bad Request
            content={
                "success": False,
                "error": str(ve),
                "message": f"Failed to execute tool {request_body.name}"
            }
        )
    except Exception as e:
        logger.error(f"Unhandled exception in /mcp endpoint: {e}", exc_info=True)
        return JSONResponse(
            status_code=500, # Internal Server Error
            content={
                "success": False,
                "error": str(e),
                "message": f"An unexpected error occurred while executing tool {request_body.name}"
            }
        )

@app.get("/tools", response_model=List[Tool])
async def list_mcp_tools_endpoint():
    """MCP list_tools endpoint for HTTP transport."""
    if not hsi_mcp_server_instance:
        logger.error("HSIServer instance not available for /tools.")
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": "Server not initialized",
                "message": "HSIServer instance is not available. Check server logs."
            }
        )
    
    try:
        # Directly call our new async method on the HSIServer instance
        tools_list = await hsi_mcp_server_instance.get_tool_definitions()
        return tools_list
    except Exception as e:
        logger.error(f"Error calling get_tool_definitions: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "error": f"Error retrieving tool definitions: {str(e)}",
            }
        )


async def run_stdio_mode():
    """Run the server in stdio mode."""
    global hsi_mcp_server_instance
    # hsi_mcp_server_instance is guaranteed to be created by main_entry.
    logger.info(f"Starting HSI MCP Server in STDIO mode (project: {os.getenv('GOOGLE_CLOUD_PROJECT')})")
    try:
        async with stdio_server() as (read_stream, write_stream):
            await hsi_mcp_server_instance.server.run(
                read_stream,
                write_stream,
                hsi_mcp_server_instance.server.create_initialization_options()
            )
    except KeyboardInterrupt:
        logger.info("Stdio server shutdown requested")
    except Exception as e:
        logger.error(f"Stdio server error: {e}", exc_info=True)
        sys.exit(1)

async def main_entry() -> None: # Renamed from main to avoid conflict with uvicorn's potential main
    """Main entry point for the HSI MCP server, decides mode."""
    
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        logger.error("GOOGLE_CLOUD_PROJECT environment variable is required")
        sys.exit(1)

    global hsi_mcp_server_instance
    if not hsi_mcp_server_instance: # Ensure instance is created if not by FastAPI startup (e.g., for stdio)
        hsi_mcp_server_instance = HSIServer()

    server_mode = os.getenv("MCP_SERVER_MODE", "stdio").lower()
    
    if server_mode == "http":
        logger.info(f"Starting HSI MCP Server in HTTP mode (project: {project_id})")
        port = int(os.getenv("PORT", "8080")) # Cloud Run provides PORT
        # Uvicorn will use the 'app' instance defined globally
        # The HSIServer instance is created in app's startup event
        config = uvicorn.Config(app, host="0.0.0.0", port=port, log_level=log_level.lower())
        server = uvicorn.Server(config)
        await server.serve()
    elif server_mode == "stdio":
        await run_stdio_mode()
    else:
        logger.error(f"Invalid MCP_SERVER_MODE: {server_mode}. Must be 'http' or 'stdio'.")
        sys.exit(1)

if __name__ == "__main__":
    if not os.getenv("GOOGLE_CLOUD_PROJECT"):
        logger.error("Please set up your .env file with required variables (GOOGLE_CLOUD_PROJECT).")
        logger.error("Copy .env.example to .env and fill in your values.")
        sys.exit(1)
    
    asyncio.run(main_entry())
