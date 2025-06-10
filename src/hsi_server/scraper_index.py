"""Web scraping functionality for HSI data and news headlines from AAStocks.

This module provides robust web scraping capabilities for retrieving Hang Seng Index
data and related news headlines with multiple fallback strategies and error handling.
"""

import logging
import re
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


class HSIDataScraper:
    """Scraper for Hang Seng Index data and news headlines from AAStocks.

    Provides reliable data extraction with multiple parsing strategies,
    fallback mechanisms, and comprehensive error handling for:
    - Current HSI point value and daily changes
    - Market turnover data
    - News headlines with content filtering
    """

    # URL Configuration
    BASE_URL = "https://www.aastocks.com"
    HSI_URL = (
        "https://www.aastocks.com/en/stocks/market/index/hk-index-con.aspx?index=HSI"
    )
    NEWS_URL = "https://www.aastocks.com/en/stocks/news/aafn/popular-news"

    # Content filtering constants
    MIN_HEADLINE_LENGTH = 20
    MAX_HEADLINE_LENGTH = 200
    REQUEST_TIMEOUT = 10

    # Market-related keywords for news filtering
    MARKET_KEYWORDS = [
        "stock",
        "market",
        "hong kong",
        "hk",
        "china",
        "economic",
        "trade",
        "financial",
        "investment",
        "company",
    ]

    def __init__(self) -> None:
        """Initialize the scraper with configured HTTP session."""
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.5",
                "Accept-Encoding": "gzip, deflate",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        logger.debug("Initialized HSI data scraper with configured session")

    def _get_page(self, url: str) -> BeautifulSoup:
        """Fetch and parse a web page with error handling.

        Args:
            url: URL to fetch

        Returns:
            BeautifulSoup parsed HTML content

        Raises:
            requests.RequestException: If the request fails
        """
        try:
            response = self.session.get(url, timeout=self.REQUEST_TIMEOUT)
            response.raise_for_status()
            return BeautifulSoup(response.content, "html.parser")
        except requests.RequestException as e:
            logger.error(f"Failed to fetch {url}: {e}")
            raise

    def _clean_text(self, text: str) -> str:
        """Clean and normalize text content by removing extra whitespace and special characters.

        Args:
            text: Raw text to clean

        Returns:
            Cleaned and normalized text string
        """
        if not text:
            return ""
        # Normalize whitespace and remove unwanted characters
        text = re.sub(r"\s+", " ", text.strip())
        text = re.sub(r"[\r\n\t]", " ", text)
        return text.strip()

    def _parse_number(self, text: str) -> Optional[float]:
        """Parse a numeric value from text, handling financial data formatting.

        Args:
            text: Text containing a number (may include commas, parentheses)

        Returns:
            Parsed float value or None if parsing fails
        """
        if not text:
            return None

        text = self._clean_text(text)
        text = re.sub(r"[,\s]", "", text)  # Remove commas and spaces

        try:
            # Handle parentheses as negative (financial convention)
            if text.startswith("(") and text.endswith(")"):
                text = "-" + text[1:-1]
            return float(text)
        except (ValueError, TypeError):
            logger.warning(f"Could not parse number: {text}")
            return None

    def _parse_change_string(
        self, change_text: str
    ) -> tuple[Optional[float], Optional[float]]:
        """Parse change string in format '14.76 (0.06%)' into point and percentage values."""
        if not change_text:
            return None, None

        # Clean the text
        change_text = self._clean_text(change_text)

        # Pattern to match "14.76 (0.06%)" or similar formats
        pattern = r"^([+-]?[\d,\.]+)\s*\(([+-]?[\d,\.]+)%\)$"
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
                turnover_match = re.search(r"([\d,\.]+)\s*([BMK])", text, re.I)
                if turnover_match:
                    value = self._parse_number(turnover_match.group(1))
                    unit = turnover_match.group(2).upper()
                    if value and unit:
                        multiplier = {"B": 1e9, "M": 1e6, "K": 1e3}.get(unit, 1)
                        return value * multiplier
                # If no unit, try to parse as raw number
                return self._parse_number(text)
        except Exception as e:
            logger.warning(f"Failed to extract turnover: {e}")
        return None

    def _extract_change_data(
        self, soup: BeautifulSoup
    ) -> tuple[Optional[float], Optional[float]]:
        """Extract daily change point and percentage using CSS selector."""
        try:
            # First, get the arrow direction from the inner span
            arrow_element = soup.select_one(
                "#hkIdxContainer > div.hkidx-change.cls > span > span"
            )
            is_negative = False
            if arrow_element:
                arrow_text = self._clean_text(arrow_element.get_text())
                is_negative = "▼" in arrow_text

            # Get the full text that contains the change values
            element = soup.select_one("#hkIdxContainer > div.hkidx-change.cls > span")
            if element:
                text = self._clean_text(element.get_text())
                # Remove the arrow symbols to get just the numeric values
                text = re.sub(r"^[▲▼]\s*", "", text)

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
                "url": self.HSI_URL,
            }

        except Exception as e:
            logger.error(f"Error parsing HSI data: {e}")
            raise RuntimeError(f"Failed to parse HSI data: {e}")

    def get_news_headlines(self, limit: int = 10) -> List[Dict[str, str]]:
        """Scrape news headlines from AAStocks using multiple extraction strategies.

        Args:
            limit: Maximum number of headlines to retrieve (default: 10)

        Returns:
            List of headline dictionaries with 'headline' and 'url' keys
        """
        logger.debug(f"Scraping top {limit} news headlines from AAStocks")

        soup = self._get_page(self.NEWS_URL)
        headlines = []

        try:
            # Strategy 1: Direct news/article links
            headlines.extend(self._extract_article_links(soup, limit))

            # Strategy 2: Container-based extraction
            if len(headlines) < limit:
                headlines.extend(
                    self._extract_container_headlines(soup, limit - len(headlines))
                )

            # Strategy 3: Keyword-filtered fallback
            if len(headlines) < limit:
                headlines.extend(
                    self._extract_filtered_headlines(soup, limit - len(headlines))
                )

            # Remove duplicates while preserving order
            unique_headlines = self._deduplicate_headlines(headlines)

            logger.info(
                f"Successfully extracted {len(unique_headlines)} unique headlines"
            )
            return unique_headlines[:limit]

        except Exception as e:
            logger.error(f"Error scraping news headlines: {e}")
            raise RuntimeError(f"Failed to scrape news headlines: {e}")

    def _extract_article_links(
        self, soup: BeautifulSoup, limit: int
    ) -> List[Dict[str, str]]:
        """Extract headlines from direct article/news links."""
        headlines = []
        article_links = soup.find_all("a", href=re.compile(r"news|article"))

        for link in article_links[: limit * 2]:  # Get extra for filtering
            headline = self._process_headline_link(link)
            if headline and len(headline["headline"]) > self.MIN_HEADLINE_LENGTH:
                headlines.append(headline)
                if len(headlines) >= limit:
                    break

        return headlines

    def _extract_container_headlines(
        self, soup: BeautifulSoup, limit: int
    ) -> List[Dict[str, str]]:
        """Extract headlines from news/article containers."""
        headlines = []
        containers = soup.find_all(
            ["div", "section", "article"],
            class_=re.compile(r"news|headline|article", re.I),
        )

        for container in containers:
            if len(headlines) >= limit:
                break

            links = container.find_all("a")
            for link in links:
                headline = self._process_headline_link(link)
                if (
                    headline
                    and len(headline["headline"]) > self.MIN_HEADLINE_LENGTH
                    and not self._is_duplicate_headline(headline["headline"], headlines)
                ):
                    headlines.append(headline)
                    if len(headlines) >= limit:
                        break

        return headlines

    def _extract_filtered_headlines(
        self, soup: BeautifulSoup, limit: int
    ) -> List[Dict[str, str]]:
        """Extract headlines using keyword filtering as fallback."""
        headlines = []
        all_links = soup.find_all("a")

        for link in all_links:
            if len(headlines) >= limit:
                break

            headline = self._process_headline_link(link)
            if (
                headline
                and self._is_valid_headline(headline["headline"])
                and not self._is_duplicate_headline(headline["headline"], headlines)
            ):
                headlines.append(headline)

        return headlines

    def _process_headline_link(self, link) -> Optional[Dict[str, str]]:
        """Process a single link element into a headline dictionary."""
        headline_text = self._clean_text(link.get_text())
        if not headline_text:
            return None

        href = link.get("href", "")
        full_url = urljoin(self.BASE_URL, href) if href else ""

        return {"headline": headline_text, "url": full_url}

    def _is_valid_headline(self, headline_text: str) -> bool:
        """Check if headline text meets quality criteria."""
        return self.MIN_HEADLINE_LENGTH <= len(
            headline_text
        ) <= self.MAX_HEADLINE_LENGTH and any(
            keyword in headline_text.lower() for keyword in self.MARKET_KEYWORDS
        )

    def _is_duplicate_headline(
        self, headline_text: str, existing_headlines: List[Dict[str, str]]
    ) -> bool:
        """Check if headline already exists in the list."""
        return any(h["headline"] == headline_text for h in existing_headlines)

    def _deduplicate_headlines(
        self, headlines: List[Dict[str, str]]
    ) -> List[Dict[str, str]]:
        """Remove duplicate headlines while preserving order."""
        seen = set()
        unique_headlines = []

        for headline in headlines:
            if headline["headline"] not in seen:
                seen.add(headline["headline"])
                unique_headlines.append(headline)

        return unique_headlines
