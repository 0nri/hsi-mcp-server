# HSI MCP Server

A Model Context Protocol (MCP) server for **personal use only** that retrieves Hang Seng Index (HSI) data and news headlines from AAStocks for research and educational purposes.

## ⚠️ Important Disclaimer

**This project is for personal use only.** Not affiliated with AAStocks (www.aastocks.com). Users are responsible for ensuring compliance with AAStocks' terms of service and applicable laws.

## Features

- **Real-time HSI Data**: Current index point, daily change, turnover, and timestamp
- **AI-Powered News Summary**: Top headlines with Gemini 2.0 Flash summary
- **MCP Standard Compliance**: Works with any MCP-compatible client (Cline, Claude Desktop, etc.)
- **Robust Web Scraping**: Multiple fallback methods for reliable data extraction

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

1. **Clone the repository**:
   ```bash
   git clone https://github.com/0nri/hsi-mcp-server
   cd hsi-mcp-server
   ```

2. **Install dependencies**:
   ```bash
   pip install -e .
   ```

3. **Configure environment**:
   ```bash
   cp .env.example .env
   ```
   
   Edit `.env` with your settings:
   ```env
   GOOGLE_CLOUD_PROJECT=your-project-id
   GEMINI_LOCATION=us-central1
   GEMINI_MODEL=gemini-2.0-flash-lite-001
   LOG_LEVEL=INFO
   ```

## Usage

### With MCP Clients

#### Cline/Claude Desktop
Add to your MCP settings:

```json
{
  "mcpServers": {
    "hsi-server": {
      "command": "python",
      "args": ["-m", "src.hsi_server.main"],
      "cwd": "/path/to/hsi-mcp-server",
      "env": {
        "GOOGLE_CLOUD_PROJECT": "your-project-id",
        "GEMINI_LOCATION": "us-central1",
        "GEMINI_MODEL": "gemini-2.0-flash-lite-001"
      }
    }
  }
}
```

Then ask questions like:
- "What's the current HSI performance?"
- "Give me a summary of today's Hong Kong market news"

### Available Tools

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
Retrieves news headlines with AI-generated summary.

**Parameters**:
- `limit` (optional): Number of headlines (1-20, default: 10)

**Example Response**:
```json
{
  "success": true,
  "data": {
    "headlines": [
      {
        "headline": "Hong Kong stocks rise as tech shares gain momentum",
        "url": "https://www.aastocks.com/en/stocks/news/..."
      }
    ],
    "summary": "Hong Kong markets showed positive momentum with technology stocks leading gains...",
    "count": 10
  }
}
```

## Testing

### Quick Test
```bash
# Run tests
pytest tests/

# Test server directly
python -m src.hsi_server.main
```

### Using MCP Inspector
```bash
npx @modelcontextprotocol/inspector python -m src.hsi_server.main
```

## Troubleshooting

### Common Issues

1. **"GOOGLE_CLOUD_PROJECT environment variable is required"**
   - Ensure `.env` file is configured with your Google Cloud project ID

2. **"Failed to initialize Gemini client"**
   - Check Vertex AI API is enabled: `gcloud services enable aiplatform.googleapis.com`
   - Verify ADC setup: `gcloud auth application-default login`

### Debug Mode
Set `LOG_LEVEL=DEBUG` in your `.env` file for detailed logging.

## License

This project is licensed under the MIT License.

## Disclaimer

**Personal Use Only**: This tool is for personal research and educational purposes only. Not for commercial use or trading decisions.

**No Affiliation**: Not affiliated with AAStocks. Independent open-source tool accessing publicly available data.

**User Responsibility**: Users must ensure compliance with AAStocks' terms of service and applicable laws.

**No Warranty**: Software provided "as is" without warranty. Authors not responsible for damages or losses.

**Data Accuracy**: Always verify information from official sources. Market data may be delayed or inaccurate.

## Data Sources

- **HSI Data**: [AAStocks Hong Kong Index](https://www.aastocks.com/en/stocks/market/index/hk-index-con.aspx?index=HSI)
- **News Headlines**: [AAStocks Popular News](https://www.aastocks.com/en/stocks/news/aafn/popular-news)
- **AI Summarization**: Google Gemini 2.0 Flash via Vertex AI
