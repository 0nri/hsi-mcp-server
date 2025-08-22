# HSI MCP Server

A Model Context Protocol (MCP) server for **personal use only** that retrieves Hang Seng Index (HSI) data and news headlines from AAStocks for research and educational purposes. This server is built with FastAPI and the `fastapi-mcp` library for robust HTTP-based communication.

## ⚠️ Important Disclaimer

**This project is for personal use only.** Not affiliated with AAStocks (www.aastocks.com). Users are responsible for ensuring compliance with AAStocks' terms of service and applicable laws.

## Features

- **Real-time HSI Data**: Current index point, daily change, turnover, and timestamp.
- **AI-Powered News Summary**: Top headlines with Gemini 2.0 Flash summary.
- **MCP Standard Compliance**: Works with any MCP-compatible client (Cline, Claude Desktop, MCP Inspector, etc.) over HTTP.
- **Unified MCP Endpoint**: Provides both simple and streamable HTTP transport over a single `/mcp` endpoint.
- **Robust Web Scraping**: Multiple fallback methods for reliable data extraction.

## Prerequisites

- Python 3.10 or higher
- Google Cloud Project with Vertex AI API enabled
- Application Default Credentials (ADC) configured

### Quick Google Cloud Setup

```bash
# Enable Vertex AI API
gcloud services enable aiplatform.googleapis.com

# Set up Application Default Credentials
gcloud auth application-default login
```

## Installation

1.  **Clone the repository**:
    ```bash
    git clone https://github.com/0nri/hsi-mcp-server
    cd hsi-mcp-server
    ```

2.  **Install dependencies**:
    ```bash
    pip install -e .
    ```

3.  **Configure environment**:
    ```bash
    cp .env.example .env
    ```
   
    Edit `.env` with your settings:
    ```env
    GOOGLE_CLOUD_PROJECT=your-project-id
    GEMINI_LOCATION=us-central1
    GEMINI_MODEL=gemini-2.0-flash-lite-001
    LOG_LEVEL=INFO
    PORT=8080 # Port for the server, Cloud Run will override this
    ```

## Usage

This server is designed to run as an HTTP service, perfect for local testing with Docker or for deploying to services like Google Cloud Run.

### Running Locally

1.  **Start the server**:
    ```bash
    python -m src.hsi_server.main
    ```
    The server will be running at `http://localhost:8080`.

2.  **Connect with an MCP Client**:
    Use an MCP client like the MCP Inspector to interact with the server. Create a configuration file (e.g., `mcp_config.json`) with the following content:

    ```json
    {
      "mcpServers": {
        "hsi-server": {
          "type": "streamable-http",
          "url": "http://localhost:8080/mcp",
          "useTLS": false
        }
      }
    }
    ```
    Then, run the inspector:
    ```bash
    npx @modelcontextprotocol/inspector --config mcp_config.json --server hsi-server
    ```
    You can now interact with the server at `http://127.0.0.1:6274`.

### Deploying to Cloud Run

A deployment script using Docker and Google Cloud Build is provided.

1.  **Configure `deploy.sh`**:
    Edit the configuration variables at the top of the `deploy.sh` script with your GCP Project ID and desired regions.

2.  **Run the script**:
    ```bash
    chmod +x deploy.sh
    ./deploy.sh
    ```
    The script will build the Docker image using Cloud Build, push it to Artifact Registry, and deploy it to Cloud Run.

3.  **Configure your client**:
    After deployment, the script will output the service URL. Use this URL in your MCP client configuration:
    ```json
    {
      "mcpServers": {
        "hsi-server-cloud": {
          "type": "streamable-http",
          "url": "YOUR_CLOUD_RUN_SERVICE_URL/mcp",
          "useTLS": true
        }
      }
    }
    ```

## Available Tools

#### `get_hsi_data`
Retrieves current Hang Seng Index data.

**Example Response**:
```json
{
  "success": true,
  "data": {
    "current_point": 19234.56,
    "daily_change_point": 123.45,
    "daily_change_percent": 0.65,
    "turnover": 87500000000,
    "timestamp": "2024-01-15T15:30:00.123456",
    "source": "AAStocks"
  }
}
```

#### `get_hsi_news_summary`
Retrieves news headlines with an AI-generated summary.

**Parameters**:
- `limit` (optional): Number of headlines (1-20, default: 10)

#### `get_stock_quote`
Retrieves current stock quote data for a Hong Kong listed company.

**Parameters**:
- `symbol_or_company` (required): Either a HK stock symbol (e.g., "00005", "388") or company name (e.g., "HSBC Holdings")

**Example Response**:
```json
{
  "success": true,
  "data": {
    "symbol": "00005",
    "company_name": "HSBC Holdings plc",
    "current_price": 65.50,
    "price_change": 1.25,
    "price_change_percent": 1.94,
    "turnover": "542.3M",
    "last_updated_time": "2024-01-15T15:30:00.123456",
    "source": "AAStocks",
    "url": "https://www.aastocks.com/en/stocks/quote/detail-quote.aspx?symbol=00005"
  }
}
```

**Note**: The tool supports both stock symbols and company names thanks to AI-powered symbol lookup using Gemini.

## Troubleshooting

### Common Issues

1.  **"GOOGLE_CLOUD_PROJECT environment variable is required"**
    - Ensure your `.env` file is configured with your Google Cloud project ID.

2.  **"Failed to initialize Gemini client"**
    - Check that the Vertex AI API is enabled: `gcloud services enable aiplatform.googleapis.com`
    - Verify your ADC setup: `gcloud auth application-default login`

### Debug Mode
Set `LOG_LEVEL=DEBUG` in your `.env` file for detailed logging.

## License

This project is licensed under the MIT License.
