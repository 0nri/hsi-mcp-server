"""Web scraping functionality for individual stock quotes from AAStocks."""

import logging
import re
from datetime import datetime
from typing import Dict, Optional, Any

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class StockQuoteScraper:
    """Scraper for individual stock quotes from AAStocks."""
    
    BASE_URL = "https://www.aastocks.com"
    QUOTE_URL_TEMPLATE = "http://www.aastocks.com/en/stocks/quote/quick-quote.aspx?symbol={symbol}"
    
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
    
    def _format_symbol(self, symbol: str) -> str:
        """Format symbol to 5-digit Hong Kong stock code."""
        if not symbol:
            raise ValueError("Symbol cannot be empty")
        
        # Clean the symbol
        symbol = symbol.strip().upper()
        
        # Remove common suffixes
        symbol = re.sub(r'\.(HK|HKG)$', '', symbol, flags=re.IGNORECASE)
        
        # Extract numeric part
        numeric_match = re.search(r'(\d+)', symbol)
        if not numeric_match:
            raise ValueError(f"No numeric symbol found in: {symbol}")
        
        numeric_part = numeric_match.group(1)
        
        # Pad to 5 digits
        if len(numeric_part) > 5:
            raise ValueError(f"Symbol too long: {numeric_part}")
        
        formatted_symbol = numeric_part.zfill(5)
        logger.info(f"Formatted symbol '{symbol}' to '{formatted_symbol}'")
        
        return formatted_symbol
    
    def _extract_current_price(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract current stock price using CSS selector."""
        try:
            # Primary selector
            element = soup.select_one("#tbQuote > tbody > tr:nth-child(1) > td.rel.lastBox.c1 > div.abs.txt_c.ss3.cls.font-num.font-b > span > span")
            if element:
                text = self._clean_text(element.get_text())
                return self._parse_number(text)
            
            # Fallback selectors
            fallback_selectors = [
                "#tbQuote td.lastBox span span",
                "#tbQuote .font-num span",
                ".lastBox span",
                "[class*='lastBox'] span"
            ]
            
            for selector in fallback_selectors:
                element = soup.select_one(selector)
                if element:
                    text = self._clean_text(element.get_text())
                    price = self._parse_number(text)
                    if price and price > 0:
                        logger.info(f"Used fallback selector '{selector}' for current price")
                        return price
                        
        except Exception as e:
            logger.warning(f"Failed to extract current price: {e}")
        return None
    
    def _extract_price_change(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract price change using CSS selector."""
        try:
            # Primary selector
            element = soup.select_one("#dc7bd > span")
            if element:
                # Check for direction indicator
                is_negative = False
                direction_span = element.find('span')
                if direction_span:
                    direction_text = self._clean_text(direction_span.get_text())
                    is_negative = "▼" in direction_text
                
                # Get the numeric text (remove direction symbols)
                text = self._clean_text(element.get_text())
                text = re.sub(r'^[▲▼]\s*', '', text)
                
                change = self._parse_number(text)
                if change is not None and is_negative:
                    change = -change
                
                return change
            
            # Fallback selectors
            fallback_selectors = [
                "#dc7bd",
                "[id*='dc7bd']",
                ".change span",
                "[class*='change'] span"
            ]
            
            for selector in fallback_selectors:
                element = soup.select_one(selector)
                if element:
                    text = self._clean_text(element.get_text())
                    # Handle direction indicators
                    is_negative = "▼" in text or text.startswith('-')
                    text = re.sub(r'^[▲▼\-\+]\s*', '', text)
                    change = self._parse_number(text)
                    if change is not None:
                        if is_negative:
                            change = -change
                        logger.info(f"Used fallback selector '{selector}' for price change")
                        return change
                        
        except Exception as e:
            logger.warning(f"Failed to extract price change: {e}")
        return None
    
    def _extract_price_change_percent(self, soup: BeautifulSoup) -> Optional[float]:
        """Extract price change percentage using CSS selector."""
        try:
            # Primary selector
            element = soup.select_one("#tbQuote > tbody > tr:nth-child(2) > td > div.ss4.abs.cls.bold.font-num > span > span:nth-child(1)")
            if element:
                # Check for direction indicator in parent or nearby elements
                is_negative = False
                parent_text = self._clean_text(element.parent.get_text() if element.parent else "")
                is_negative = "▼" in parent_text
                
                text = self._clean_text(element.get_text())
                text = re.sub(r'^[▲▼\-\+]\s*', '', text).replace('%', '')
                
                percent = self._parse_number(text)
                if percent is not None and is_negative:
                    percent = -percent
                
                return percent
            
            # Fallback selectors
            fallback_selectors = [
                "#tbQuote .font-num span",
                "#tbQuote span[class*='percent']",
                ".ss4 span",
                "[class*='percent'] span"
            ]
            
            for selector in fallback_selectors:
                elements = soup.select(selector)
                for element in elements:
                    text = self._clean_text(element.get_text())
                    if '%' in text or 'percent' in text.lower():
                        # Handle direction indicators
                        is_negative = "▼" in text or text.startswith('-')
                        text = re.sub(r'^[▲▼\-\+]\s*', '', text).replace('%', '')
                        percent = self._parse_number(text)
                        if percent is not None:
                            if is_negative:
                                percent = -percent
                            logger.info(f"Used fallback selector '{selector}' for percentage change")
                            return percent
                            
        except Exception as e:
            logger.warning(f"Failed to extract price change percentage: {e}")
        return None
    
    def _extract_turnover(self, soup: BeautifulSoup) -> tuple[Optional[float], Optional[str]]:
        """Extract turnover value and unit using CSS selector."""
        try:
            # Primary selector for main turnover
            main_element = soup.select_one("#tbQuote > tbody > tr:nth-child(4) > td:nth-child(1) > div.ss2.abs.lbl_r.font-num.cls")
            # Primary selector for unit
            unit_element = soup.select_one("#tbQuote > tbody > tr:nth-child(4) > td:nth-child(1) > div.ss2.abs.lbl_r.font-num.cls > span")
            
            turnover_value = None
            turnover_unit = None
            
            if main_element:
                # Get the main text and extract number
                main_text = self._clean_text(main_element.get_text())
                
                # If there's a unit element, extract unit from it and remove from main text
                if unit_element:
                    unit_text = self._clean_text(unit_element.get_text())
                    if unit_text:
                        turnover_unit = unit_text
                        # Remove unit text from main text to get clean number
                        main_text = main_text.replace(unit_text, '').strip()
                
                # Parse the numeric value
                turnover_value = self._parse_number(main_text)
                
                # If we got a value but no unit, try to extract unit from the original text
                if turnover_value is not None and not turnover_unit:
                    original_text = self._clean_text(main_element.get_text())
                    unit_match = re.search(r'([BMK]|billion|million|thousand)', original_text, re.I)
                    if unit_match:
                        turnover_unit = unit_match.group(1).upper()
                        if turnover_unit in ['BILLION', 'MILLION', 'THOUSAND']:
                            turnover_unit = turnover_unit[0]  # Convert to B, M, K
            
            # Fallback selectors if primary didn't work
            if turnover_value is None:
                fallback_selectors = [
                    "#tbQuote .lbl_r",
                    "#tbQuote [class*='turnover']",
                    ".ss2 .font-num",
                    "[class*='turnover'] span"
                ]
                
                for selector in fallback_selectors:
                    elements = soup.select(selector)
                    for element in elements:
                        text = self._clean_text(element.get_text())
                        # Look for patterns that suggest turnover data
                        if any(keyword in text.lower() for keyword in ['turnover', 'volume', 'billion', 'million']):
                            # Extract number and unit
                            number_match = re.search(r'([\d,\.]+)', text)
                            unit_match = re.search(r'([BMK]|billion|million|thousand)', text, re.I)
                            
                            if number_match:
                                turnover_value = self._parse_number(number_match.group(1))
                                if unit_match:
                                    unit = unit_match.group(1).upper()
                                    if unit in ['BILLION', 'MILLION', 'THOUSAND']:
                                        turnover_unit = unit[0]  # Convert to B, M, K
                                    else:
                                        turnover_unit = unit
                                
                                if turnover_value is not None:
                                    logger.info(f"Used fallback selector '{selector}' for turnover")
                                    break
                    
                    if turnover_value is not None:
                        break
            
            return turnover_value, turnover_unit
            
        except Exception as e:
            logger.warning(f"Failed to extract turnover: {e}")
        return None, None

    def _extract_company_name(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract company name from the page."""
        try:
            # Look for company name in common locations
            name_selectors = [
                "#SQ_Name",  # Stock bar name
                ".stockName",
                ".company-name",
                "[class*='name']",
                "h1", "h2"
            ]
            
            for selector in name_selectors:
                elements = soup.select(selector)
                for element in elements:
                    text = self._clean_text(element.get_text())
                    # Look for text that might be a company name
                    if text and len(text) > 3 and len(text) < 100:
                        # Filter out obvious non-company names
                        if not any(keyword in text.lower() for keyword in ['quote', 'chart', 'analysis', 'market']):
                            logger.info(f"Found potential company name: {text}")
                            return text
            
            # Look in page title
            title = soup.find('title')
            if title:
                title_text = self._clean_text(title.get_text())
                if 'stock' in title_text.lower() and len(title_text) < 100:
                    return title_text
                    
        except Exception as e:
            logger.warning(f"Failed to extract company name: {e}")
        return None
    
    def _extract_last_updated_time(self, soup: BeautifulSoup) -> Optional[str]:
        """Extract last updated time using the specified selector."""
        try:
            # Primary selector provided by user
            primary_selector = "#mainForm > div.container_16.resize > div > div.content > div.lastUpdate.mar10B"
            element = soup.select_one(primary_selector)
            
            if element:
                text = self._clean_text(element.get_text())
                if text:
                    logger.info(f"Found last updated time: {text}")
                    return text
            
            # Fallback selectors
            fallback_selectors = [
                ".lastUpdate",
                "[class*='update']",
                "[class*='time']",
                ".mar10B",
                "[class*='last']"
            ]
            
            for selector in fallback_selectors:
                elements = soup.select(selector)
                for element in elements:
                    text = self._clean_text(element.get_text())
                    # Look for time patterns
                    if text and any(pattern in text.lower() for pattern in ['update', 'time', 'last', ':']):
                        if len(text) < 100:
                            logger.info(f"Found last updated time with fallback selector '{selector}': {text}")
                            return text
            
            # Look for time patterns in JavaScript variables
            scripts = soup.find_all('script')
            for script in scripts:
                if script.string:
                    script_text = script.string
                    # Look for server time or last update time
                    if 'ServerDate' in script_text or 'last_update' in script_text:
                        import re
                        time_match = re.search(r"'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})'", script_text)
                        if time_match:
                            return time_match.group(1)
                            
        except Exception as e:
            logger.warning(f"Failed to extract last updated time: {e}")
        return None

    def _parse_change_html(self, html_str: str) -> tuple[Optional[float], Optional[float], str]:
        """Parse change and percentage from HTML string like '<span class='pos'>+0.400(0.426%)</span>'."""
        try:
            # Determine direction from class
            direction = "unchanged"
            if "class='pos'" in html_str:
                direction = "up"
            elif "class='neg'" in html_str:
                direction = "down"
            
            # Extract text content
            import re
            from bs4 import BeautifulSoup
            soup = BeautifulSoup(html_str, 'html.parser')
            text = soup.get_text().strip()
            
            # Parse change and percentage: "+0.400(0.426%)" or "-1.200(1.25%)"
            match = re.match(r'([+-]?)([0-9,.]+)\(([+-]?[0-9,.]+)%\)', text)
            if match:
                sign_prefix, change_str, percent_str = match.groups()
                
                # Parse change value
                change_value = self._parse_number(change_str)
                if change_value is not None:
                    if sign_prefix == '-' or direction == "down":
                        change_value = -abs(change_value)
                    elif sign_prefix == '+' or direction == "up":
                        change_value = abs(change_value)
                
                # Parse percentage value
                percent_value = self._parse_number(percent_str)
                if percent_value is not None:
                    if sign_prefix == '-' or direction == "down":
                        percent_value = -abs(percent_value)
                    elif sign_prefix == '+' or direction == "up":
                        percent_value = abs(percent_value)
                
                return change_value, percent_value, direction
            
        except Exception as e:
            logger.warning(f"Failed to parse change HTML '{html_str}': {e}")
        
        return None, None, "unknown"
    
    def _parse_turnover(self, turnover_str: str) -> tuple[Optional[float], Optional[str]]:
        """Parse turnover string like '514.06M' or '1.04B'."""
        try:
            if not turnover_str:
                return None, None
            
            # Extract number and unit
            import re
            match = re.match(r'([0-9,.]+)([KMBT]?)', turnover_str.strip())
            if match:
                number_str, unit = match.groups()
                value = self._parse_number(number_str)
                
                # Normalize unit
                if unit:
                    unit_map = {'K': 'K', 'M': 'M', 'B': 'B', 'T': 'T'}
                    unit = unit_map.get(unit.upper(), unit)
                
                return value, unit or None
                
        except Exception as e:
            logger.warning(f"Failed to parse turnover '{turnover_str}': {e}")
        
        return None, None

    def get_stock_quote(self, symbol: str) -> Dict[str, Any]:
        """Get stock quote data from AAStocks using AJAX endpoint."""
        logger.info(f"Getting stock quote for symbol: {symbol}")
        
        try:
            # Format the symbol to 5-digit Hong Kong format
            formatted_symbol = self._format_symbol(symbol)
            
            # Use AJAX endpoint for real-time data
            ajax_url = f"http://www.aastocks.com/en/resources/datafeed/getrtqsymbol.ashx?s={formatted_symbol}"
            logger.info(f"Fetching quote from AJAX endpoint: {ajax_url}")
            
            # Set appropriate headers for AJAX request
            headers = self.session.headers.copy()
            headers.update({
                'Accept': 'application/json, text/javascript, */*; q=0.01',
                'X-Requested-With': 'XMLHttpRequest',
                'Referer': f'http://www.aastocks.com/en/stocks/quote/quick-quote.aspx?symbol={formatted_symbol}'
            })
            
            response = self.session.get(ajax_url, headers=headers, timeout=10)
            response.raise_for_status()
            
            # Parse JSON response
            import json
            data = json.loads(response.text)
            
            if not data or not isinstance(data, list) or len(data) == 0:
                raise ValueError(f"No data returned for symbol {formatted_symbol}")
            
            stock_data = data[0]  # First item in the array
            
            # Extract and parse data fields
            current_price = self._parse_number(stock_data.get('a', ''))
            change_value, change_percent, direction = self._parse_change_html(stock_data.get('b', ''))
            turnover_value, turnover_unit = self._parse_turnover(stock_data.get('d', ''))
            last_updated_time = stock_data.get('e', '')
            
            # Also get company name from the main page
            page_url = self.QUOTE_URL_TEMPLATE.format(symbol=formatted_symbol)
            try:
                soup = self._get_page(page_url)
                company_name = self._extract_company_name(soup)
            except Exception as e:
                logger.warning(f"Failed to get company name from main page: {e}")
                company_name = None
            
            logger.info(f"Successfully extracted quote data for {formatted_symbol}")
            
            return {
                "symbol": formatted_symbol,
                "company_name": company_name,
                "current_price": current_price,
                "price_change": change_value,
                "price_change_percent": change_percent,
                "turnover": turnover_value,
                "turnover_unit": turnover_unit,
                "last_updated_time": last_updated_time,
                "timestamp": datetime.now().isoformat(),
                "source": "AAStocks",
                "url": page_url
            }
            
        except Exception as e:
            logger.error(f"Error getting stock quote for {symbol}: {e}")
            raise RuntimeError(f"Failed to get stock quote for {symbol}: {e}")
