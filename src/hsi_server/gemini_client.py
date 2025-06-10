"""Gemini AI client for news summarization using Vertex AI."""

import logging
import os
import re
from typing import List, Dict, Optional

import vertexai
from vertexai.generative_models import GenerativeModel, Tool
from vertexai.preview.generative_models import grounding

logger = logging.getLogger(__name__)


class GeminiClient:
    """Client for interacting with Gemini via Vertex AI."""
    
    def __init__(self) -> None:
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("GEMINI_LOCATION", "global")
        self.model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite-001")
        
        if not self.project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is required")
        
        # Initialize Vertex AI
        vertexai.init(project=self.project_id, location=self.location)
        
        # Initialize the model
        self.model = GenerativeModel(self.model_name)
        
        logger.info(f"Initialized Gemini client with model {self.model_name} in {self.location}")
    
    def summarize_headlines(self, headlines: List[Dict[str, str]]) -> str:
        """Summarize news headlines into a brief paragraph."""
        if not headlines:
            return "No headlines available for summarization."
        
        # Prepare the headlines text for summarization
        headlines_text = "\n".join([
            f"{i+1}. {headline['headline']}" 
            for i, headline in enumerate(headlines)
        ])
        
        # Create the prompt for summarization
        prompt = f"""
Please analyze the following Hong Kong stock market news headlines and provide a brief paragraph summary (2-3 sentences) that captures the key market themes and sentiment. Focus on major trends, market movements, and significant developments that may impact the Hang Seng Index.

Headlines:
{headlines_text}

Summary:"""
        
        try:
            logger.info("Requesting headline summarization from Gemini...")
            
            # Generate the summary using Gemini
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.3,  # Lower temperature for more focused, consistent summaries
                    "top_p": 0.8,
                    "top_k": 40,
                    "max_output_tokens": 200,  # Keep summary concise
                }
            )
            
            if response.text:
                summary = response.text.strip()
                logger.info("Successfully generated headline summary")
                return summary
            else:
                logger.warning("Gemini returned empty response")
                return "Unable to generate summary at this time."
                
        except Exception as e:
            logger.error(f"Error generating summary with Gemini: {e}")
            # Return a fallback summary
            return self._generate_fallback_summary(headlines)
    
    def _generate_fallback_summary(self, headlines: List[Dict[str, str]]) -> str:
        """Generate a simple fallback summary when Gemini is unavailable."""
        if not headlines:
            return "No headlines available."
        
        # Extract key terms from headlines to identify themes
        all_text = " ".join([h['headline'].lower() for h in headlines])
        
        # Count mentions of key market-related terms
        key_terms = {
            'gain': ['gain', 'rise', 'up', 'higher', 'surge', 'rally', 'climb'],
            'loss': ['fall', 'drop', 'down', 'lower', 'decline', 'tumble', 'slide'],
            'tech': ['tech', 'technology', 'ai', 'semiconductor', 'chip'],
            'finance': ['bank', 'financial', 'finance', 'credit'],
            'energy': ['oil', 'energy', 'gas', 'petrochemical'],
            'china': ['china', 'chinese', 'mainland', 'beijing'],
            'us': ['us', 'america', 'american', 'fed', 'federal'],
        }
        
        theme_counts = {}
        for theme, terms in key_terms.items():
            count = sum(all_text.count(term) for term in terms)
            if count > 0:
                theme_counts[theme] = count
        
        # Generate a basic summary based on most common themes
        if not theme_counts:
            return f"Market news update covering {len(headlines)} recent developments in Hong Kong financial markets."
        
        top_themes = sorted(theme_counts.items(), key=lambda x: x[1], reverse=True)[:3]
        
        summary_parts = []
        if 'gain' in dict(top_themes) and 'loss' in dict(top_themes):
            summary_parts.append("Mixed market sentiment with both gains and losses reported")
        elif 'gain' in dict(top_themes):
            summary_parts.append("Generally positive market sentiment with reported gains")
        elif 'loss' in dict(top_themes):
            summary_parts.append("Market showing decline with reported losses")
        
        # Add sector information
        sectors = [theme for theme, _ in top_themes if theme in ['tech', 'finance', 'energy']]
        if sectors:
            summary_parts.append(f"Key activity in {', '.join(sectors)} sectors")
        
        # Add geographic context
        regions = [theme for theme, _ in top_themes if theme in ['china', 'us']]
        if regions:
            summary_parts.append(f"International focus on {', '.join(regions.upper() if r == 'us' else r.title() for r in regions)}")
        
        if summary_parts:
            return ". ".join(summary_parts) + f". Summary based on {len(headlines)} recent headlines."
        else:
            return f"Market update covering {len(headlines)} recent developments across Hong Kong financial markets."
    
    def lookup_stock_symbol(self, company_name: str) -> Optional[str]:
        """Look up Hong Kong stock symbol for a company name using Google Search grounding."""
        if not company_name:
            return None
        
        logger.info(f"Looking up stock symbol for company: {company_name}")
        
        try:
            # Create the lookup prompt
            prompt = f"""
Please find the Hong Kong stock exchange symbol for the company "{company_name}". 
I need the numeric stock code used on the Hong Kong Stock Exchange (HKEX).

For example:
- HSBC Holdings Limited → 00005
- Hang Seng Bank → 00011
- Tencent Holdings → 00700
- AIA Group → 01299

Please respond with ONLY the numeric stock code (5 digits, padded with zeros if necessary). 
If you cannot find a valid Hong Kong stock symbol, respond with "NOT_FOUND".

Company: {company_name}
Hong Kong Stock Symbol:"""

            # Try with Google Search grounding first
            try:
                # Create model with Google Search grounding
                grounded_model = GenerativeModel(
                    self.model_name,
                    tools=[
                        Tool.from_google_search_retrieval(
                            grounding.GoogleSearchRetrieval()
                        )
                    ]
                )
                
                response = grounded_model.generate_content(
                    prompt,
                    generation_config={
                        "temperature": 0.1,  # Very low temperature for factual lookup
                        "top_p": 0.8,
                        "top_k": 10,
                        "max_output_tokens": 50,  # Short response expected
                    }
                )
                
                if response.text:
                    symbol = self._extract_symbol_from_response(response.text.strip())
                    if symbol:
                        logger.info(f"Found symbol using grounded search: {company_name} → {symbol}")
                        return symbol
                        
            except Exception as e:
                logger.warning(f"Google Search grounding failed: {e}, trying fallback")
            
            # Fallback to regular Gemini without grounding
            response = self.model.generate_content(
                prompt,
                generation_config={
                    "temperature": 0.1,
                    "top_p": 0.8,
                    "top_k": 10,
                    "max_output_tokens": 50,
                }
            )
            
            if response.text:
                symbol = self._extract_symbol_from_response(response.text.strip())
                if symbol:
                    logger.info(f"Found symbol using fallback: {company_name} → {symbol}")
                    return symbol
            
            logger.warning(f"Could not find stock symbol for: {company_name}")
            return None
            
        except Exception as e:
            logger.error(f"Error looking up stock symbol for {company_name}: {e}")
            return None
    
    def _extract_symbol_from_response(self, response_text: str) -> Optional[str]:
        """Extract stock symbol from Gemini response text."""
        if not response_text:
            return None
        
        # Handle "NOT_FOUND" response
        if "NOT_FOUND" in response_text.upper():
            return None
        
        # Look for 5-digit patterns (most common for HK stocks)
        five_digit_match = re.search(r'\b(\d{5})\b', response_text)
        if five_digit_match:
            return five_digit_match.group(1)
        
        # Look for shorter digit patterns and pad them
        digit_match = re.search(r'\b(\d{1,4})\b', response_text)
        if digit_match:
            symbol = digit_match.group(1)
            # Pad to 5 digits
            return symbol.zfill(5)
        
        # Look for patterns like "0005.HK" or "5.HK"
        hk_pattern_match = re.search(r'\b(\d{1,5})\.HK\b', response_text, re.IGNORECASE)
        if hk_pattern_match:
            symbol = hk_pattern_match.group(1)
            return symbol.zfill(5)
        
        return None
