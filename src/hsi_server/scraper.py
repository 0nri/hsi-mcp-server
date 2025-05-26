"""Web scraping functionality for HSI data and news headlines."""

import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

logger = logging.getLogger(__name__)


class HSIDataScraper:
    """Scraper for Hang Seng Index data from AAStocks."""
    
    BASE_URL = "https://www.aastocks.com"
    HSI_URL = "https://www.aastocks.com/en/stocks/market/index/hk-index-con.aspx?index=HSI"
    NEWS_URL = "https://www.aastocks.com/en/stocks/news/aafn/popular-news"
    
    def __init__(self) -> None:
        self.session = requests.Session()
        # Set headers to mimic a real browser
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
    
    def get_hsi_data(self) -> Dict[str, Any]:
        """Scrape current HSI data from AAStocks."""
        logger.info("Scraping HSI data...")
        
        soup = self._get_page(self.HSI_URL)
        
        try:
            # Find the main HSI data section
            # AAStocks typically has the index data in a specific table or div
            # We'll need to look for the current value, change, and percentage
            
            # Look for the main index value
            current_point = None
            daily_change_point = None
            daily_change_percent = None
            turnover = None
            
            # Method 1: Look for table rows with HSI data
            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cells = row.find_all(['td', 'th'])
                    if len(cells) >= 4:
                        # Check if this looks like HSI data
                        text = ' '.join([cell.get_text() for cell in cells])
                        if 'HSI' in text or 'Hang Seng' in text:
                            # Try to extract values from cells
                            for i, cell in enumerate(cells):
                                cell_text = self._clean_text(cell.get_text())
                                if re.match(r'^\d{1,2},?\d{3,5}', cell_text):  # Looks like index value
                                    current_point = self._parse_number(cell_text)
                                elif re.match(r'^[+-]?\d+', cell_text) and '.' in cell_text:
                                    if daily_change_point is None:
                                        daily_change_point = self._parse_number(cell_text)
                                elif '%' in cell_text:
                                    percent_text = cell_text.replace('%', '')
                                    daily_change_percent = self._parse_number(percent_text)
            
            # Method 2: Look for specific class names or IDs (common in AAStocks)
            if current_point is None:
                # Try to find elements with common financial data patterns
                for element in soup.find_all(['span', 'div', 'td'], 
                                           class_=re.compile(r'(price|value|index)', re.I)):
                    text = self._clean_text(element.get_text())
                    if re.match(r'^\d{1,2},?\d{3,5}', text):
                        current_point = self._parse_number(text)
                        break
            
            # Method 3: Look for turnover data
            for element in soup.find_all(text=re.compile(r'turnover|volume', re.I)):
                parent = element.parent
                if parent:
                    # Look for nearby numeric values
                    siblings = parent.find_next_siblings()[:3]  # Check next few siblings
                    for sibling in siblings:
                        if isinstance(sibling, Tag):
                            text = self._clean_text(sibling.get_text())
                            # Look for billion/million patterns
                            if re.search(r'\d+.*[BMK]', text, re.I):
                                turnover_match = re.search(r'([\d,\.]+)\s*([BMK])', text, re.I)
                                if turnover_match:
                                    value = self._parse_number(turnover_match.group(1))
                                    unit = turnover_match.group(2).upper()
                                    if value and unit:
                                        multiplier = {'B': 1e9, 'M': 1e6, 'K': 1e3}.get(unit, 1)
                                        turnover = value * multiplier
                                        break
            
            # If we still don't have data, try a more general approach
            if current_point is None:
                # Look for large numbers that could be the index value
                all_text = soup.get_text()
                numbers = re.findall(r'\b\d{1,2},?\d{3,5}(?:\.\d{1,2})?\b', all_text)
                for num_str in numbers:
                    num = self._parse_number(num_str)
                    if num and 15000 <= num <= 35000:  # Reasonable HSI range
                        current_point = num
                        break
            
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
