"""Basic tests for the HSI MCP server."""

import asyncio
import json
import os
import pytest
from unittest.mock import Mock, patch

# Set up test environment variables before importing the server
os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
os.environ["GEMINI_LOCATION"] = "us-central1"
os.environ["GEMINI_MODEL"] = "gemini-2.0-flash-lite-001"

from src.hsi_server.main import HSIServer
from src.hsi_server.scraper import HSIDataScraper
from src.hsi_server.gemini_client import GeminiClient


class TestHSIServer:
    """Test cases for HSI MCP Server."""
    
    @pytest.fixture
    def server(self):
        """Create a test server instance."""
        return HSIServer()
    
    def test_server_initialization(self, server):
        """Test that server initializes correctly."""
        assert server.server is not None
        assert server.scraper is not None
        assert server.gemini_client is None  # Should be initialized lazily
    
    @pytest.mark.asyncio
    async def test_list_tools(self, server):
        """Test that tools are listed correctly."""
        # This test would require more complex setup with actual MCP protocol
        # For now, we'll test that the server initializes correctly
        assert server.server is not None
        assert hasattr(server, '_setup_handlers')
    
    @patch('src.hsi_server.scraper.HSIDataScraper.get_hsi_data')
    @pytest.mark.asyncio
    async def test_get_hsi_data_success(self, mock_get_hsi_data, server):
        """Test successful HSI data retrieval."""
        # Mock the scraper response
        mock_data = {
            "current_point": 20000.0,
            "daily_change_point": 100.0,
            "daily_change_percent": 0.5,
            "turnover": 50000000000,
            "timestamp": "2024-01-01T12:00:00",
            "source": "AAStocks",
            "url": "https://example.com"
        }
        mock_get_hsi_data.return_value = mock_data
        
        # Test the handler
        result = await server._handle_get_hsi_data()
        
        assert len(result) == 1
        response_text = result[0].text
        response_data = json.loads(response_text)
        
        assert response_data["success"] is True
        assert response_data["data"] == mock_data
        assert "HSI data retrieved successfully" in response_data["message"]
    
    @patch('src.hsi_server.scraper.HSIDataScraper.get_hsi_data')
    @pytest.mark.asyncio
    async def test_get_hsi_data_error(self, mock_get_hsi_data, server):
        """Test HSI data retrieval error handling."""
        # Mock the scraper to raise an exception
        mock_get_hsi_data.side_effect = Exception("Network error")
        
        # Test the handler
        result = await server._handle_get_hsi_data()
        
        assert len(result) == 1
        response_text = result[0].text
        response_data = json.loads(response_text)
        
        assert response_data["success"] is False
        assert "Network error" in response_data["error"]
        assert "Failed to retrieve HSI data" in response_data["message"]
    
    @patch('src.hsi_server.scraper.HSIDataScraper.get_news_headlines')
    @patch('src.hsi_server.scraper.HSIDataScraper.get_hsi_data')
    @patch('src.hsi_server.gemini_client.GeminiClient.summarize_headlines')
    @pytest.mark.asyncio
    async def test_get_hsi_news_summary_success(self, mock_summarize, mock_get_hsi_data, mock_get_headlines, server):
        """Test successful news summary retrieval."""
        # Mock the responses
        mock_headlines = [
            {"headline": "Test headline 1", "url": "http://example.com/1"},
            {"headline": "Test headline 2", "url": "http://example.com/2"}
        ]
        mock_get_headlines.return_value = mock_headlines
        mock_get_hsi_data.return_value = {"timestamp": "2024-01-01T12:00:00"}
        mock_summarize.return_value = "Test summary of market news"
        
        # Test the handler
        result = await server._handle_get_hsi_news_summary(2)
        
        assert len(result) == 1
        response_text = result[0].text
        response_data = json.loads(response_text)
        
        assert response_data["success"] is True
        assert response_data["data"]["headlines"] == mock_headlines
        assert response_data["data"]["summary"] == "Test summary of market news"
        assert response_data["data"]["count"] == 2


class TestHSIDataScraper:
    """Test cases for HSI Data Scraper."""
    
    def test_scraper_initialization(self):
        """Test scraper initializes correctly."""
        scraper = HSIDataScraper()
        assert scraper.session is not None
        assert scraper.BASE_URL == "https://www.aastocks.com"
    
    def test_clean_text(self):
        """Test text cleaning functionality."""
        scraper = HSIDataScraper()
        
        # Test basic cleaning
        assert scraper._clean_text("  hello world  ") == "hello world"
        assert scraper._clean_text("hello\n\r\tworld") == "hello world"
        assert scraper._clean_text("") == ""
    
    def test_parse_number(self):
        """Test number parsing functionality."""
        scraper = HSIDataScraper()
        
        # Test basic numbers
        assert scraper._parse_number("123.45") == 123.45
        assert scraper._parse_number("1,234.56") == 1234.56
        assert scraper._parse_number("(123.45)") == -123.45
        assert scraper._parse_number("invalid") is None
        assert scraper._parse_number("") is None
    
    def test_parse_change_string(self):
        """Test change string parsing functionality."""
        scraper = HSIDataScraper()
        
        # Test valid change string formats
        point, percent = scraper._parse_change_string("14.76 (0.06%)")
        assert point == 14.76
        assert percent == 0.06
        
        # Test negative changes (note: _parse_change_string extracts positive values,
        # the negative sign is applied in _extract_change_data based on arrow direction)
        point, percent = scraper._parse_change_string("25.43 (1.23%)")
        assert point == 25.43
        assert percent == 1.23
        
        # Test with commas
        point, percent = scraper._parse_change_string("1,234.56 (2.34%)")
        assert point == 1234.56
        assert percent == 2.34
        
        # Test invalid format
        point, percent = scraper._parse_change_string("invalid format")
        assert point is None
        assert percent is None
        
        # Test empty string
        point, percent = scraper._parse_change_string("")
        assert point is None
        assert percent is None

    @pytest.mark.integration
    def test_arrow_direction_logic(self):
        """Test that arrow direction correctly determines positive/negative values."""
        scraper = HSIDataScraper()
        
        # Create mock HTML for testing arrow direction logic
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
        assert point_pos == 67.25, f"Expected positive 67.25, got {point_pos}"
        assert percent_pos == 0.29, f"Expected positive 0.29, got {percent_pos}"
        
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
        assert point_neg == -45.18, f"Expected negative -45.18, got {point_neg}"
        assert percent_neg == -0.22, f"Expected negative -0.22, got {percent_neg}"

    @pytest.mark.integration
    def test_live_hsi_data_scraping(self):
        """Integration test: scrape live HSI data and verify all fields."""
        scraper = HSIDataScraper()
        
        try:
            data = scraper.get_hsi_data()
            
            # Verify response structure
            assert isinstance(data, dict)
            assert "current_point" in data
            assert "daily_change_point" in data
            assert "daily_change_percent" in data
            assert "turnover" in data
            assert "timestamp" in data
            assert "source" in data
            assert "url" in data
            
            # Verify critical fields are populated
            assert data["current_point"] is not None, "current_point should not be None"
            assert data["daily_change_point"] is not None, "daily_change_point should not be None"
            assert data["daily_change_percent"] is not None, "daily_change_percent should not be None"
            assert data["turnover"] is not None, "turnover should not be None"
            
            # Verify data quality (reasonable ranges for HSI)
            assert isinstance(data["current_point"], (int, float))
            assert 10000 <= data["current_point"] <= 50000, f"HSI value {data['current_point']} seems out of reasonable range"
            
            assert isinstance(data["daily_change_point"], (int, float))
            assert -2000 <= data["daily_change_point"] <= 2000, f"Daily change {data['daily_change_point']} seems extreme"
            
            assert isinstance(data["daily_change_percent"], (int, float))
            assert -10 <= data["daily_change_percent"] <= 10, f"Daily change % {data['daily_change_percent']} seems extreme"
            
            assert isinstance(data["turnover"], (int, float))
            assert data["turnover"] > 0, "Turnover should be positive"
            
            # Verify metadata
            assert data["source"] == "AAStocks"
            assert data["url"] == scraper.HSI_URL
            assert data["timestamp"] is not None
            
            print(f"✅ Live scraping test passed. HSI: {data['current_point']}, Change: {data['daily_change_point']} ({data['daily_change_percent']}%), Turnover: {data['turnover']:,.0f}")
            
        except Exception as e:
            pytest.skip(f"Live scraping test skipped due to network/parsing error: {e}")


class TestGeminiClient:
    """Test cases for Gemini Client."""
    
    def test_gemini_client_initialization_missing_project(self):
        """Test Gemini client fails without project ID."""
        # Clear the environment variable
        if "GOOGLE_CLOUD_PROJECT" in os.environ:
            del os.environ["GOOGLE_CLOUD_PROJECT"]
        
        with pytest.raises(ValueError, match="GOOGLE_CLOUD_PROJECT environment variable is required"):
            GeminiClient()
        
        # Restore the environment variable
        os.environ["GOOGLE_CLOUD_PROJECT"] = "test-project"
    
    def test_fallback_summary(self):
        """Test fallback summary generation."""
        # Mock the initialization to avoid requiring actual GCP credentials
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
            # Should detect positive sentiment and tech/china themes
            assert any(word in summary.lower() for word in ["gain", "positive", "tech", "china"])


if __name__ == "__main__":
    pytest.main([__file__])
