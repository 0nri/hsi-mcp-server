"""Web scraping functionality for HSI data and news headlines."""

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class HSIDataScraper:
    """Scraper for Hang Seng Index data from AAStocks."""
    
    BASE_URL = "https://www.aastocks.com"
    HSI_URL = "https://www.aastocks.com/en/stocks/market/index/hk-index-con.aspx?index=HSI"
    NEWS_URL = "https://www.aastocks.com/en/stocks/news/aafn/popular-news"
    
    def __init__(self) -> None:
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
            'Upgrade-Insecure-Requests': '1',
        })
    
    def _get_page(self, url: str) -> BeautifulSoup:
        """Fetch and parse a web page."""
        try:
            response = self.session.get(url, timeout=10)
            response.raise_for_status()
            return BeautifulSoup(response.content, 'html.parser')
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {url}: {e}")
            raise
    
    def _clean_text(self, text: str) -> str:
        """Clean and normalize text content."""
        if not text:
            return ""
        # Remove extra whitespace and normalize
        text = re.sub(r'\s+', ' ', text.strip())
        # Remove any unwanted characters
        text = re.sub(r'[\r\n\t]', ' ', text)
        return text.strip()
    
    def _parse_number(self, text: str) -> Optional[float]:
        """Parse a number from text, handling commas and signs."""
        if not text:
            return None
        
        # Clean the text
        text = self._clean_text(text)
        # Remove commas and extract number
        text = re.sub(r'[,\s]', '', text)
        
        try:
            # Handle parentheses as negative (common in financial data)
            if text.startswith('(') and text.endswith(')'):
                text = '-' + text[1:-1]
            return float(text)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse number: {text}")
            return None
    
    def _parse_change_string(self, change_text: str) -> tuple[Optional[float], Optional[float]]:
        """Parse change string in format '14.76 (0.06%)' into point and percentage values."""
        if not change_text:
            return None, None
        
        # Clean the text
        change_text = self._clean_text(change_text)
        
        # Pattern to match "14.76 (0.06%)" or similar formats
        pattern = r'^([+-]?[\d,\.]+)\s*\(([+-]?[\d,\.]+)%\)$'
        match = re.match(pattern, change_text)
        
        if match:
            point_change = self._parse_number(match.group(1))
            percent_change = self._parse_number(match.group(2))
            return point_change, percent_change
        
        logger.warning(f"Could not parse change string: {change_text}")
        return None, None
    
    def _extract_current_point(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract current HSI point value using CSS selector."""
        try:
            element = soup.select_one("#hkIdxContainer > div.hkidx-last.txt_r")
            if element:
                text = self._clean_text(element.get_text())
                return self._parse_number(text)
        except Exception as e:
            logger.warning(f"Failed to extract current point: {e}")
        return None
    
    def _extract_turnover(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract turnover value using CSS selector."""
        try:
            element = soup.select_one("#hkIdxContainer > div.hkidx-turnover.cls > span")
            if element:
                text = self._clean_text(element.get_text())
                # Handle turnover in billions/millions format
                turnover_match = re.search(r'([\d,\.]+)\s*([BMK])', text, re.I)
                if turnover_match:
                    value = self._parse_number(turnover_match.group(1))
                    unit = turnover_match.group(2).upper()
                    if value and unit:
                        multiplier = {'B': 1e9, 'M': 1e6, 'K': 1e3}.get(unit, 1)
                        return value * multiplier
                # If no unit, try to parse as raw number
                return self._parse_number(text)
        except Exception as e:
            logger.warning(f"Failed to extract turnover: {e}")
        return None
    
    def _extract_change_data(self, soup: BeautifulSoup) -> tuple[Optional[float], Optional[float]]:
        """Extract daily change point and percentage using CSS selector."""
        try:
            # First, get the arrow direction from the inner span
            arrow_element = soup.select_one("#hkIdxContainer > div.hkidx-change.cls > span > span")
            is_negative = False
            if arrow_element:
                arrow_text = self._clean_text(arrow_element.get_text())
                is_negative = "▼" in arrow_text
            
            # Get the full text that contains the change values
            element = soup.select_one("#hkIdxContainer > div.hkidx-change.cls > span")
            if element:
                text = self._clean_text(element.get_text())
                # Remove the arrow symbols to get just the numeric values
                text = re.sub(r'^[▲▼]\s*', '', text)
                
                # Parse the change values (always positive from text)
                point_change, percent_change = self._parse_change_string(text)
                
                # Apply negative sign if the arrow indicates down movement
                if is_negative and point_change is not None:
                    point_change = -point_change
                if is_negative and percent_change is not None:
                    percent_change = -percent_change
                
                return point_change, percent_change
        except Exception as e:
            logger.warning(f"Failed to extract change data: {e}")
        return None, None

    def get_hsi_data(self) -> Dict[str, Any]:
        """Scrape current HSI data from AAStocks using specific CSS selectors."""
        logger.info("Scraping HSI data...")
        
        soup = self._get_page(self.HSI_URL)
        
        try:
            # Extract data using targeted CSS selectors
            current_point = self._extract_current_point(soup)
            turnover = self._extract_turnover(soup)
            daily_change_point, daily_change_percent = self._extract_change_data(soup)
            
            return {
                "current_point": current_point,
                "daily_change_point": daily_change_point,
                "daily_change_percent": daily_change_percent,
                "turnover": turnover,
                "timestamp": datetime.now().isoformat(),
                "source": "AAStocks",
                "url": self.HSI_URL
            }
            
        except Exception as e:
            logger.error(f"Error parsing HSI data: {e}")
            raise RuntimeError(f"Failed to parse HSI data: {e}")
    
    def get_news_headlines(self, limit: int = 10) -> List[Dict[str, str]]:
        """Scrape news headlines from AAStocks."""
        logger.info(f"Scraping top {limit} news headlines...")
        
        soup = self._get_page(self.NEWS_URL)
        headlines = []
        
        try:
            # Look for news articles - common patterns in AAStocks
            # Method 1: Look for article links
            article_links = soup.find_all('a', href=re.compile(r'news|article'))
            
            for link in article_links[:limit * 2]:  # Get more than needed in case some are filtered
                headline_text = self._clean_text(link.get_text())
                if headline_text and len(headline_text) > 20:  # Filter out short/empty headlines
                    href = link.get('href', '')
                    full_url = urljoin(self.BASE_URL, href) if href else ''
                    
                    headlines.append({
                        "headline": headline_text,
                        "url": full_url
                    })
                    
                    if len(headlines) >= limit:
                        break
            
            # Method 2: If we don't have enough, look for headlines in common containers
            if len(headlines) < limit:
                for container in soup.find_all(['div', 'section', 'article'], 
                                             class_=re.compile(r'news|headline|article', re.I)):
                    links = container.find_all('a')
                    for link in links:
                        headline_text = self._clean_text(link.get_text())
                        if headline_text and len(headline_text) > 20:
                            href = link.get('href', '')
                            full_url = urljoin(self.BASE_URL, href) if href else ''
                            
                            # Avoid duplicates
                            if not any(h['headline'] == headline_text for h in headlines):
                                headlines.append({
                                    "headline": headline_text,
                                    "url": full_url
                                })
                                
                                if len(headlines) >= limit:
                                    break
                    
                    if len(headlines) >= limit:
                        break
            
            # Method 3: Fallback - look for any text that looks like headlines
            if len(headlines) < limit:
                all_links = soup.find_all('a')
                for link in all_links:
                    headline_text = self._clean_text(link.get_text())
                    # Filter for potential headlines (reasonable length, contains relevant keywords)
                    if (headline_text and 
                        20 <= len(headline_text) <= 200 and
                        any(keyword in headline_text.lower() for keyword in 
                            ['stock', 'market', 'hong kong', 'hk', 'china', 'economic', 
                             'trade', 'financial', 'investment', 'company'])):
                        
                        href = link.get('href', '')
                        full_url = urljoin(self.BASE_URL, href) if href else ''
                        
                        # Avoid duplicates
                        if not any(h['headline'] == headline_text for h in headlines):
                            headlines.append({
                                "headline": headline_text,
                                "url": full_url
                            })
                            
                            if len(headlines) >= limit:
                                break
            
            logger.info(f"Found {len(headlines)} headlines")
            return headlines[:limit]
            
        except Exception as e:
            logger.error(f"Error scraping news headlines: {e}")
            raise RuntimeError(f"Failed to scrape news headlines: {e}")
