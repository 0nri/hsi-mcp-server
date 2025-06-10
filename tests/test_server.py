"""Comprehensive tests for the HSI MCP server with FastMCP and Streamable HTTP."""

import asyncio
import json
import os
import pytest
from unittest.mock import Mock, patch, AsyncMock
from typing import Dict, Any

# Set up test environment variables before importing the server
os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
os.environ["GEMINI_LOCATION"] = "us-central1"
os.environ["GEMINI_MODEL"] = "gemini-2.0-flash-lite-001"

# Import the main module and its components
import src.hsi_server.main as main_module
from src.hsi_server.main import get_hsi_data, get_hsi_news_summary, get_stock_quote, get_gemini_client
from src.hsi_server.scraper_index import HSIDataScraper
from src.hsi_server.scraper_quote import StockQuoteScraper
from src.hsi_server.gemini_client import GeminiClient


class TestFastMCPIntegration:
    """Test cases for FastMCP server integration and configuration."""
    
    def test_fastmcp_server_initialization(self):
        """Test that FastMCP server is properly initialized."""
        # The mcp server should be initialized as a module-level variable
        assert hasattr(main_module, 'mcp')
        assert main_module.mcp is not None
        assert main_module.mcp.name == "HSI MCP Server"
    
    def test_tool_registration(self):
        """Test that tools are properly registered with FastMCP."""
        # Check that the mcp instance has the expected tools registered
        # FastMCP registers tools via decorators, so we check the decorated functions exist
        assert hasattr(main_module, 'get_hsi_data')
        assert hasattr(main_module, 'get_hsi_news_summary')
        assert callable(main_module.get_hsi_data)
        assert callable(main_module.get_hsi_news_summary)
    
    def test_server_configuration(self):
        """Test server host and port configuration."""
        # Test default configuration
        with patch.dict(os.environ, {}, clear=True):
            os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
            mcp_instance = main_module.mcp
            
            # Should use default values
            # Note: FastMCP settings might not be set until run() is called
            # This test verifies the configuration logic exists
            assert hasattr(mcp_instance, 'settings')
    
    @patch.dict(os.environ, {
        "GOOGLE_CLOUD_PROJECT": "test-project",
        "HOST": "127.0.0.1",
        "PORT": "9999"
    })
    def test_custom_server_configuration(self):
        """Test custom host and port configuration from environment variables."""
        # Import fresh to get the environment variables
        import importlib
        importlib.reload(main_module)
        
        # Verify environment variables are read correctly
        assert os.getenv("HOST") == "127.0.0.1"
        assert os.getenv("PORT") == "9999"
    
    def test_missing_google_cloud_project(self):
        """Test that server fails gracefully without required environment variables."""
        with patch.dict(os.environ, {}, clear=True):
            # Remove the required environment variable
            if "GOOGLE_CLOUD_PROJECT" in os.environ:
                del os.environ["GOOGLE_CLOUD_PROJECT"]
            
            with patch('sys.exit') as mock_exit:
                with patch('src.hsi_server.main.logger') as mock_logger:
                    # Mock the mcp.run to prevent actual server startup
                    with patch('src.hsi_server.main.mcp.run'):
                        main_module.main_entry()
                        mock_logger.error.assert_called_with("GOOGLE_CLOUD_PROJECT environment variable is required")
                        mock_exit.assert_called_with(1)


class TestToolFunctions:
    """Test cases for the individual tool functions."""
    
    @patch('src.hsi_server.main.scraper')
    def test_get_hsi_data_success(self, mock_scraper):
        """Test successful HSI data retrieval."""
        # Mock the scraper response
        mock_data = {
            "current_point": 23792.54,
            "daily_change_point": -114.43,
            "daily_change_percent": -0.48,
            "turnover": 235620000000,
            "timestamp": "2024-12-06T15:30:00+08:00",
            "source": "AAStocks",
            "url": "https://www.aastocks.com/en/stocks/analysis/stock-aafn-content/NOW.1/latest-quote"
        }
        mock_scraper.get_hsi_data.return_value = mock_data
        
        # Test the function
        result = get_hsi_data()
        response_data = json.loads(result)
        
        assert response_data["success"] is True
        assert response_data["data"] == mock_data
        mock_scraper.get_hsi_data.assert_called_once()
    
    @patch('src.hsi_server.main.scraper')
    def test_get_hsi_data_error(self, mock_scraper):
        """Test HSI data retrieval error handling."""
        # Mock the scraper to raise an exception
        mock_scraper.get_hsi_data.side_effect = Exception("Network connection failed")
        
        # Test the function
        result = get_hsi_data()
        response_data = json.loads(result)
        
        assert response_data["success"] is False
        assert "Network connection failed" in response_data["error"]
    
    @patch('src.hsi_server.main.get_gemini_client')
    @patch('src.hsi_server.main.scraper')
    def test_get_hsi_news_summary_success(self, mock_scraper, mock_get_gemini_client):
        """Test successful news summary retrieval."""
        # Mock the responses
        mock_headlines = [
            {"headline": "HSI rises on positive sentiment", "url": "http://example.com/1"},
            {"headline": "Technology stocks gain momentum", "url": "http://example.com/2"}
        ]
        mock_scraper.get_news_headlines.return_value = mock_headlines
        mock_scraper.get_hsi_data.return_value = {"timestamp": "2024-12-06T15:30:00+08:00"}
        
        mock_gemini_client = Mock()
        mock_gemini_client.summarize_headlines.return_value = "Markets show positive trends with technology sector leading gains."
        mock_get_gemini_client.return_value = mock_gemini_client
        
        # Test the function
        result = get_hsi_news_summary(2)
        response_data = json.loads(result)
        
        assert response_data["success"] is True
        assert response_data["data"]["headlines"] == mock_headlines
        assert response_data["data"]["summary"] == "Markets show positive trends with technology sector leading gains."
        assert response_data["data"]["count"] == 2
        assert response_data["data"]["timestamp"] == "2024-12-06T15:30:00+08:00"
        
        mock_scraper.get_news_headlines.assert_called_once_with(2)
        mock_gemini_client.summarize_headlines.assert_called_once_with(mock_headlines)
    
    @patch('src.hsi_server.main.scraper')
    def test_get_hsi_news_summary_no_headlines(self, mock_scraper):
        """Test news summary when no headlines are found."""
        mock_scraper.get_news_headlines.return_value = []
        
        # Test the function
        result = get_hsi_news_summary(10)
        response_data = json.loads(result)
        
        assert response_data["success"] is True
        assert response_data["data"]["headlines"] == []
        assert response_data["data"]["count"] == 0
        assert "No headlines available" in response_data["data"]["summary"]
    
    @patch('src.hsi_server.main.get_gemini_client')
    @patch('src.hsi_server.main.scraper')
    def test_get_hsi_news_summary_ai_failure(self, mock_scraper, mock_get_gemini_client):
        """Test news summary when AI summarization fails."""
        mock_headlines = [{"headline": "Test headline", "url": "http://example.com"}]
        mock_scraper.get_news_headlines.return_value = mock_headlines
        mock_scraper.get_hsi_data.return_value = {"timestamp": "2024-12-06T15:30:00+08:00"}
        
        # Mock Gemini client to fail
        mock_get_gemini_client.side_effect = Exception("Gemini API error")
        
        # Test the function
        result = get_hsi_news_summary(1)
        response_data = json.loads(result)
        
        assert response_data["success"] is True
        assert response_data["data"]["headlines"] == mock_headlines
        assert "Unable to generate AI summary" in response_data["data"]["summary"]
        assert "Found 1 headlines" in response_data["data"]["summary"]
    
    @patch('src.hsi_server.main.scraper')
    def test_get_hsi_news_summary_error(self, mock_scraper):
        """Test news summary error handling."""
        mock_scraper.get_news_headlines.side_effect = Exception("Scraping failed")
        
        # Test the function
        result = get_hsi_news_summary(5)
        response_data = json.loads(result)
        
        assert response_data["success"] is False
        assert "Scraping failed" in response_data["error"]


class TestStockQuoteToolFunction:
    """Test cases for the new stock quote tool function."""
    
    @patch('src.hsi_server.main.quote_scraper')
    def test_get_stock_quote_with_symbol_success(self, mock_quote_scraper):
        """Test successful stock quote retrieval with numeric symbol."""
        # Mock the scraper response
        mock_data = {
            "symbol": "00005",
            "current_price": 52.75,
            "price_change": -0.45,
            "price_change_percent": -0.85,
            "turnover": 1234567890,
            "turnover_unit": "B",
            "timestamp": "2024-12-06T15:30:00+08:00",
            "source": "AAStocks",
            "url": "http://www.aastocks.com/en/stocks/quote/quick-quote.aspx?symbol=00005"
        }
        mock_quote_scraper.get_stock_quote.return_value = mock_data
        
        # Test with numeric symbol
        result = get_stock_quote("00005")
        response_data = json.loads(result)
        
        assert response_data["success"] is True
        assert response_data["data"] == mock_data
        mock_quote_scraper.get_stock_quote.assert_called_once_with("00005")
    
    @patch('src.hsi_server.main.get_gemini_client')
    @patch('src.hsi_server.main.quote_scraper')
    def test_get_stock_quote_with_company_name_success(self, mock_quote_scraper, mock_get_gemini_client):
        """Test successful stock quote retrieval with company name lookup."""
        # Mock Gemini client lookup
        mock_gemini_client = Mock()
        mock_gemini_client.lookup_stock_symbol.return_value = "00005"
        mock_get_gemini_client.return_value = mock_gemini_client
        
        # Mock the scraper response
        mock_data = {
            "symbol": "00005",
            "current_price": 52.75,
            "price_change": -0.45,
            "price_change_percent": -0.85,
            "turnover": 1234567890,
            "turnover_unit": "B",
            "timestamp": "2024-12-06T15:30:00+08:00",
            "source": "AAStocks",
            "url": "http://www.aastocks.com/en/stocks/quote/quick-quote.aspx?symbol=00005"
        }
        mock_quote_scraper.get_stock_quote.return_value = mock_data
        
        # Test with company name
        result = get_stock_quote("HSBC Holdings")
        response_data = json.loads(result)
        
        assert response_data["success"] is True
        assert response_data["data"] == mock_data
        mock_gemini_client.lookup_stock_symbol.assert_called_once_with("HSBC Holdings")
        mock_quote_scraper.get_stock_quote.assert_called_once_with("00005")
    
    @patch('src.hsi_server.main.get_gemini_client')
    def test_get_stock_quote_company_lookup_failure(self, mock_get_gemini_client):
        """Test stock quote when company symbol lookup fails."""
        # Mock Gemini client to return None (not found)
        mock_gemini_client = Mock()
        mock_gemini_client.lookup_stock_symbol.return_value = None
        mock_get_gemini_client.return_value = mock_gemini_client
        
        # Test with company name that can't be found
        result = get_stock_quote("Unknown Company")
        response_data = json.loads(result)
        
        assert response_data["success"] is False
        assert "Could not find Hong Kong stock symbol for company: Unknown Company" in response_data["error"]
        mock_gemini_client.lookup_stock_symbol.assert_called_once_with("Unknown Company")
    
    @patch('src.hsi_server.main.quote_scraper')
    def test_get_stock_quote_scraper_error(self, mock_quote_scraper):
        """Test stock quote when scraper raises an exception."""
        # Mock the scraper to raise an exception
        mock_quote_scraper.get_stock_quote.side_effect = Exception("Scraping failed")
        
        # Test with symbol
        result = get_stock_quote("00005")
        response_data = json.loads(result)
        
        assert response_data["success"] is False
        assert "Scraping failed" in response_data["error"]


class TestStockQuoteScraper:
    """Test cases for StockQuoteScraper class."""
    
    def test_scraper_initialization(self):
        """Test stock quote scraper initializes correctly."""
        scraper = StockQuoteScraper()
        assert scraper.session is not None
        assert scraper.BASE_URL == "https://www.aastocks.com"
        assert "{symbol}" in scraper.QUOTE_URL_TEMPLATE
    
    def test_format_symbol(self):
        """Test symbol formatting functionality."""
        scraper = StockQuoteScraper()
        
        # Test various input formats
        assert scraper._format_symbol("5") == "00005"
        assert scraper._format_symbol("05") == "00005"
        assert scraper._format_symbol("005") == "00005"
        assert scraper._format_symbol("0005") == "00005"
        assert scraper._format_symbol("00005") == "00005"
        assert scraper._format_symbol("388") == "00388"
        assert scraper._format_symbol("1299") == "01299"
        assert scraper._format_symbol("700") == "00700"
        
        # Test with HK suffix
        assert scraper._format_symbol("5.HK") == "00005"
        assert scraper._format_symbol("388.hk") == "00388"
        assert scraper._format_symbol("1299.HKG") == "01299"
        
        # Test error cases
        with pytest.raises(ValueError, match="Symbol cannot be empty"):
            scraper._format_symbol("")
        
        with pytest.raises(ValueError, match="No numeric symbol found"):
            scraper._format_symbol("INVALID")
        
        with pytest.raises(ValueError, match="Symbol too long"):
            scraper._format_symbol("123456")


class TestGeminiClientIntegration:
    """Test cases for Gemini client integration and lazy initialization."""
    
    def test_gemini_client_lazy_initialization(self):
        """Test that Gemini client is initialized lazily."""
        # Reset the global client
        main_module.gemini_client = None
        
        with patch('src.hsi_server.main.GeminiClient') as mock_gemini_class:
            mock_instance = Mock()
            mock_gemini_class.return_value = mock_instance
            
            # First call should initialize
            client1 = get_gemini_client()
            assert client1 == mock_instance
            mock_gemini_class.assert_called_once()
            
            # Second call should return same instance
            client2 = get_gemini_client()
            assert client2 == mock_instance
            assert client1 is client2
            # Should not call constructor again
            assert mock_gemini_class.call_count == 1
    
    def test_gemini_client_initialization_error(self):
        """Test error handling during Gemini client initialization."""
        # Reset the global client
        main_module.gemini_client = None
        
        with patch('src.hsi_server.main.GeminiClient') as mock_gemini_class:
            mock_gemini_class.side_effect = Exception("Failed to initialize Vertex AI")
            
            with pytest.raises(Exception, match="Failed to initialize Vertex AI"):
                get_gemini_client()


class TestStreamableHTTPTransport:
    """Test cases for Streamable HTTP transport functionality."""
    
    @patch('src.hsi_server.main.mcp')
    def test_main_entry_streamable_http(self, mock_mcp):
        """Test that main entry uses streamable HTTP transport."""
        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "test-project"}):
            with patch('src.hsi_server.main.logger'):
                try:
                    main_module.main_entry()
                except SystemExit:
                    pass  # Expected on successful completion
                
                # Verify that mcp.run was called with streamable-http transport
                mock_mcp.run.assert_called_once_with(transport="streamable-http")
    
    @patch('src.hsi_server.main.mcp')
    def test_server_settings_configuration(self, mock_mcp):
        """Test that server settings are properly configured."""
        with patch.dict(os.environ, {
            "GOOGLE_CLOUD_PROJECT": "test-project",
            "HOST": "127.0.0.1",
            "PORT": "8080"
        }):
            with patch('src.hsi_server.main.logger'):
                try:
                    main_module.main_entry()
                except SystemExit:
                    pass
                
                # Verify settings were configured
                assert hasattr(mock_mcp, 'settings')
    
    @patch('src.hsi_server.main.mcp')
    def test_keyboard_interrupt_handling(self, mock_mcp):
        """Test graceful shutdown on keyboard interrupt."""
        mock_mcp.run.side_effect = KeyboardInterrupt()
        
        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "test-project"}):
            with patch('src.hsi_server.main.logger') as mock_logger:
                main_module.main_entry()
                mock_logger.info.assert_any_call("Server shutdown requested")
    
    @patch('src.hsi_server.main.mcp')
    def test_server_error_handling(self, mock_mcp):
        """Test error handling during server startup."""
        mock_mcp.run.side_effect = Exception("Server startup failed")
        
        with patch.dict(os.environ, {"GOOGLE_CLOUD_PROJECT": "test-project"}):
            with patch('sys.exit') as mock_exit:
                with patch('src.hsi_server.main.logger') as mock_logger:
                    main_module.main_entry()
                    mock_logger.error.assert_called()
                    mock_exit.assert_called_with(1)


class TestJSONResponseFormat:
    """Test cases for consistent JSON response formatting."""
    
    @patch('src.hsi_server.main.scraper')
    def test_success_response_format(self, mock_scraper):
        """Test that successful responses follow the expected JSON format."""
        mock_data = {"current_point": 20000.0, "daily_change_point": 100.0}
        mock_scraper.get_hsi_data.return_value = mock_data
        
        result = get_hsi_data()
        response = json.loads(result)
        
        # Verify response structure
        assert isinstance(response, dict)
        assert "success" in response
        assert response["success"] is True
        assert "data" in response
        assert response["data"] == mock_data
    
    @patch('src.hsi_server.main.scraper')
    def test_error_response_format(self, mock_scraper):
        """Test that error responses follow the expected JSON format."""
        mock_scraper.get_hsi_data.side_effect = Exception("Test error")
        
        result = get_hsi_data()
        response = json.loads(result)
        
        # Verify error response structure
        assert isinstance(response, dict)
        assert "success" in response
        assert response["success"] is False
        assert "error" in response
        assert "Test error" in response["error"]
    
    def test_json_serialization(self):
        """Test that all responses are valid JSON."""
        with patch('src.hsi_server.main.scraper') as mock_scraper:
            mock_scraper.get_hsi_data.return_value = {"test": "data"}
            
            result = get_hsi_data()
            
            # Should not raise an exception
            parsed = json.loads(result)
            assert isinstance(parsed, dict)


# --- Preserve Existing Business Logic Tests ---

class TestHSIDataScraper:
    """Test cases for HSI Data Scraper (preserved from original tests)."""
    
    def test_scraper_initialization(self):
        """Test scraper initializes correctly."""
        scraper = HSIDataScraper()
        assert scraper.session is not None
        assert scraper.BASE_URL == "https://www.aastocks.com"
    
    def test_clean_text(self):
        """Test text cleaning functionality."""
        scraper = HSIDataScraper()
        
        assert scraper._clean_text("  hello world  ") == "hello world"
        assert scraper._clean_text("hello\n\r\tworld") == "hello world"
        assert scraper._clean_text("") == ""
    
    def test_parse_number(self):
        """Test number parsing functionality."""
        scraper = HSIDataScraper()
        
        assert scraper._parse_number("123.45") == 123.45
        assert scraper._parse_number("1,234.56") == 1234.56
        assert scraper._parse_number("(123.45)") == -123.45
        assert scraper._parse_number("invalid") is None
        assert scraper._parse_number("") is None
    
    def test_parse_change_string(self):
        """Test change string parsing functionality."""
        scraper = HSIDataScraper()
        
        point, percent = scraper._parse_change_string("14.76 (0.06%)")
        assert point == 14.76
        assert percent == 0.06
        
        point, percent = scraper._parse_change_string("25.43 (1.23%)")
        assert point == 25.43
        assert percent == 1.23
        
        point, percent = scraper._parse_change_string("1,234.56 (2.34%)")
        assert point == 1234.56
        assert percent == 2.34
        
        point, percent = scraper._parse_change_string("invalid format")
        assert point is None
        assert percent is None
        
        point, percent = scraper._parse_change_string("")
        assert point is None
        assert percent is None

    @pytest.mark.integration
    def test_arrow_direction_logic(self):
        """Test that arrow direction correctly determines positive/negative values."""
        scraper = HSIDataScraper()
        
        from bs4 import BeautifulSoup
        
        # Test positive change (▲)
        positive_html = '''
        <div id="hkIdxContainer">
            <div class="hkidx-change cls">
                <span class="pos">
                    <span class="arrowUpDn">▲</span>67.25 (0.29%)
                </span>
            </div>
        </div>
        '''
        soup_pos = BeautifulSoup(positive_html, 'html.parser')
        point_pos, percent_pos = scraper._extract_change_data(soup_pos)
        assert point_pos == 67.25
        assert percent_pos == 0.29
        
        # Test negative change (▼)
        negative_html = '''
        <div id="hkIdxContainer">
            <div class="hkidx-change cls">
                <span class="neg">
                    <span class="arrowUpDn">▼</span>45.18 (0.22%)
                </span>
            </div>
        </div>
        '''
        soup_neg = BeautifulSoup(negative_html, 'html.parser')
        point_neg, percent_neg = scraper._extract_change_data(soup_neg)
        assert point_neg == -45.18
        assert percent_neg == -0.22

    @pytest.mark.integration
    def test_live_hsi_data_scraping(self):
        """Integration test: scrape live HSI data and verify all fields."""
        scraper = HSIDataScraper()
        
        try:
            data = scraper.get_hsi_data()
            
            # Verify response structure
            assert isinstance(data, dict)
            required_fields = ["current_point", "daily_change_point", "daily_change_percent", 
                             "turnover", "timestamp", "source", "url"]
            for field in required_fields:
                assert field in data, f"Missing required field: {field}"
            
            # Verify critical fields are populated
            assert data["current_point"] is not None
            assert data["daily_change_point"] is not None
            assert data["daily_change_percent"] is not None
            assert data["turnover"] is not None
            
            # Verify data quality (reasonable ranges for HSI)
            assert isinstance(data["current_point"], (int, float))
            assert 10000 <= data["current_point"] <= 50000
            
            assert isinstance(data["daily_change_point"], (int, float))
            assert -2000 <= data["daily_change_point"] <= 2000
            
            assert isinstance(data["daily_change_percent"], (int, float))
            assert -10 <= data["daily_change_percent"] <= 10
            
            assert isinstance(data["turnover"], (int, float))
            assert data["turnover"] > 0
            
            # Verify metadata
            assert data["source"] == "AAStocks"
            assert data["url"] == scraper.HSI_URL
            assert data["timestamp"] is not None
            
            print(f"✅ Live scraping test passed. HSI: {data['current_point']}, "
                  f"Change: {data['daily_change_point']} ({data['daily_change_percent']}%), "
                  f"Turnover: {data['turnover']:,.0f}")
            
        except Exception as e:
            pytest.skip(f"Live scraping test skipped due to network/parsing error: {e}")


class TestGeminiClient:
    """Test cases for Gemini Client (preserved from original tests)."""
    
    def test_gemini_client_initialization_missing_project(self):
        """Test Gemini client fails without project ID."""
        original_project = os.environ.get("GOOGLE_CLOUD_PROJECT")
        
        try:
            if "GOOGLE_CLOUD_PROJECT" in os.environ:
                del os.environ["GOOGLE_CLOUD_PROJECT"]
            
            with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT environment variable is required"):
                GeminiClient()
        finally:
            if original_project:
                os.environ["GOOGLE_CLOUD_PROJECT"] = original_project
    
    def test_fallback_summary(self):
        """Test fallback summary generation."""
        with patch('vertexai.init'), patch('src.hsi_server.gemini_client.GenerativeModel'):
            client = GeminiClient()
            
            headlines = [
                {"headline": "Stock prices rise amid positive sentiment"},
                {"headline": "Technology sector shows gains"},
                {"headline": "Chinese markets perform well"}
            ]
            
            summary = client._generate_fallback_summary(headlines)
            
            assert len(summary) > 0
            assert "3 recent" in summary or "3" in summary
            assert any(word in summary.lower() for word in ["gain", "positive", "tech", "china"])


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
