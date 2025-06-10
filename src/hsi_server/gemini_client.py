"""Gemini AI client for news summarization and stock symbol lookup using Vertex AI.

This module provides a client interface for interacting with Google's Gemini AI
through Vertex AI, supporting both headline summarization and stock symbol lookup
with Google Search grounding capabilities.
"""

import logging
import os
import re
from typing import Dict, List, Optional

import vertexai
from vertexai.generative_models import GenerativeModel, Tool
from vertexai.preview.generative_models import grounding

logger = logging.getLogger(__name__)


class GeminiClient:
    """Client for interacting with Gemini AI via Vertex AI.

    Provides functionality for:
    - News headline summarization with fallback mechanisms
    - Stock symbol lookup using Google Search grounding
    - Configurable model parameters and error handling
    - Multiple model support for different use cases
    """

    # Model configuration for different use cases
    MODEL_CONFIGS = {
        "summarization": {
            "default": "gemini-2.0-flash-lite-001",
            "env_var": "GEMINI_SUMMARIZATION_MODEL",
            "description": "Cost-effective model for text summarization",
        },
        "grounding": {
            "default": "gemini-2.0-flash-001",
            "env_var": "GEMINI_GROUNDING_MODEL",
            "description": "Full model with Google Search grounding support",
        },
        "default": {
            "default": "gemini-2.0-flash-lite-001",
            "env_var": "GEMINI_MODEL",
            "description": "Default model for general use",
        },
    }

    # Generation configuration presets
    SUMMARIZATION_CONFIG = {
        "temperature": 0.3,
        "top_p": 0.8,
        "top_k": 40,
        "max_output_tokens": 200,
    }

    LOOKUP_CONFIG = {
        "temperature": 0.1,
        "top_p": 0.8,
        "top_k": 10,
        "max_output_tokens": 50,
    }

    def __init__(self) -> None:
        """Initialize the Gemini client with environment configuration.

        Raises:
            ValueError: If GOOGLE_CLOUD_PROJECT environment variable is not set
            Exception: If Vertex AI initialization fails
        """
        self.project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
        self.location = os.getenv("GEMINI_LOCATION", "us-central1")

        if not self.project_id:
            raise ValueError("GOOGLE_CLOUD_PROJECT environment variable is required")

        try:
            # Initialize Vertex AI
            vertexai.init(project=self.project_id, location=self.location)

            # Initialize model cache
            self._models: Dict[str, GenerativeModel] = {}

            # Log model configuration
            self._log_model_configuration()

            logger.info(f"Initialized Gemini client in {self.location}")
        except Exception as e:
            logger.error(f"Failed to initialize Vertex AI: {e}")
            raise

    def _log_model_configuration(self) -> None:
        """Log the current model configuration for debugging."""
        logger.info("Gemini model configuration:")
        for model_type, config in self.MODEL_CONFIGS.items():
            model_name = os.getenv(config["env_var"], config["default"])
            logger.info(f"  {model_type}: {model_name} ({config['description']})")

    def _get_model(self, model_type: str = "default") -> GenerativeModel:
        """Get or create a model instance for the specified type.

        Args:
            model_type: Type of model needed ("summarization", "grounding", "default")

        Returns:
            GenerativeModel instance for the specified type
        """
        if model_type not in self.MODEL_CONFIGS:
            logger.warning(f"Unknown model type '{model_type}', using 'default'")
            model_type = "default"

        # Return cached model if available
        if model_type in self._models:
            return self._models[model_type]

        # Get model name from environment or use default
        config = self.MODEL_CONFIGS[model_type]
        model_name = os.getenv(config["env_var"], config["default"])

        # Create and cache model
        try:
            model = GenerativeModel(model_name)
            self._models[model_type] = model
            logger.debug(f"Created {model_type} model: {model_name}")
            return model
        except Exception as e:
            logger.error(f"Failed to create {model_type} model '{model_name}': {e}")
            raise

    @property
    def model(self) -> GenerativeModel:
        """Backward compatibility property for default model."""
        return self._get_model("default")

    def summarize_headlines(self, headlines: List[Dict[str, str]]) -> str:
        """Summarize news headlines into a brief market analysis paragraph.

        Args:
            headlines: List of headline dictionaries with 'headline' and 'url' keys

        Returns:
            A 2-3 sentence summary of market themes and sentiment, or fallback summary
        """
        if not headlines:
            return "No headlines available for summarization."

        logger.debug(f"Summarizing {len(headlines)} headlines")

        # Format headlines for AI processing
        headlines_text = self._format_headlines_for_prompt(headlines)

        # Create optimized prompt for market analysis
        prompt = self._create_summarization_prompt(headlines_text)

        try:
            # Use summarization-specific model for cost optimization
            summarization_model = self._get_model("summarization")
            logger.debug("Requesting headline summarization from Gemini")

            response = summarization_model.generate_content(
                prompt, generation_config=self.SUMMARIZATION_CONFIG
            )

            if response.text and response.text.strip():
                summary = response.text.strip()
                logger.debug("Successfully generated AI summary")
                return summary
            else:
                logger.warning("Gemini returned empty response")
                return self._generate_fallback_summary(headlines)

        except Exception as e:
            logger.error(f"Error generating summary with Gemini: {e}")
            return self._generate_fallback_summary(headlines)

    def _format_headlines_for_prompt(self, headlines: List[Dict[str, str]]) -> str:
        """Format headlines list into numbered text for AI processing."""
        return "\n".join(
            [f"{i+1}. {headline['headline']}" for i, headline in enumerate(headlines)]
        )

    def _create_summarization_prompt(self, headlines_text: str) -> str:
        """Create optimized prompt for market sentiment analysis."""
        return f"""Analyze the following Hong Kong stock market news headlines and provide a brief paragraph summary (2-3 sentences) that captures the key market themes and sentiment. Focus on major trends, market movements, and significant developments that may impact the Hang Seng Index.

Headlines:
{headlines_text}

Summary:"""

    def _generate_fallback_summary(self, headlines: List[Dict[str, str]]) -> str:
        """Generate a simple fallback summary when Gemini is unavailable."""
        if not headlines:
            return "No headlines available."

        # Extract key terms from headlines to identify themes
        all_text = " ".join([h["headline"].lower() for h in headlines])

        # Count mentions of key market-related terms
        key_terms = {
            "gain": ["gain", "rise", "up", "higher", "surge", "rally", "climb"],
            "loss": ["fall", "drop", "down", "lower", "decline", "tumble", "slide"],
            "tech": ["tech", "technology", "ai", "semiconductor", "chip"],
            "finance": ["bank", "financial", "finance", "credit"],
            "energy": ["oil", "energy", "gas", "petrochemical"],
            "china": ["china", "chinese", "mainland", "beijing"],
            "us": ["us", "america", "american", "fed", "federal"],
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
        if "gain" in dict(top_themes) and "loss" in dict(top_themes):
            summary_parts.append(
                "Mixed market sentiment with both gains and losses reported"
            )
        elif "gain" in dict(top_themes):
            summary_parts.append(
                "Generally positive market sentiment with reported gains"
            )
        elif "loss" in dict(top_themes):
            summary_parts.append("Market showing decline with reported losses")

        # Add sector information
        sectors = [
            theme for theme, _ in top_themes if theme in ["tech", "finance", "energy"]
        ]
        if sectors:
            summary_parts.append(f"Key activity in {', '.join(sectors)} sectors")

        # Add geographic context
        regions = [theme for theme, _ in top_themes if theme in ["china", "us"]]
        if regions:
            summary_parts.append(
                f"International focus on {', '.join(r.upper() if r == 'us' else r.title() for r in regions)}"
            )

        if summary_parts:
            return (
                ". ".join(summary_parts)
                + f". Summary based on {len(headlines)} recent headlines."
            )
        else:
            return f"Market update covering {len(headlines)} recent developments across Hong Kong financial markets."

    def lookup_stock_symbol(self, company_name: str) -> Optional[Dict[str, str]]:
        """Look up Hong Kong stock symbol and official company name using Google Search grounding.

        Args:
            company_name: Company name to look up (e.g., "HSBC Holdings", "Tencent")

        Returns:
            Dict with 'symbol' and 'company_name' keys, or None if not found
            Example: {"symbol": "00005", "company_name": "HSBC Holdings Limited"}
        """
        if not company_name or not company_name.strip():
            return None

        company_name = company_name.strip()
        logger.debug(f"Looking up stock symbol and company name for: {company_name}")

        try:
            prompt = self._create_lookup_prompt(company_name)

            # Try Google Search grounding first for better accuracy
            result = self._try_grounded_lookup(prompt, company_name)
            if result:
                return result

            # Fallback to regular Gemini
            return self._try_fallback_lookup(prompt, company_name)

        except Exception as e:
            logger.error(f"Error looking up stock symbol for {company_name}: {e}")
            return None

    def _create_lookup_prompt(self, company_name: str) -> str:
        """Create optimized prompt for stock symbol and company name lookup."""
        return f"""Find the Hong Kong Stock Exchange (HKEX) symbol and official company name for "{company_name}".

Examples:
- HSBC Holdings → Symbol: 00005, Company: HSBC Holdings Limited
- Hang Seng Bank → Symbol: 00011, Company: Hang Seng Bank Limited
- Tencent → Symbol: 00700, Company: Tencent Holdings Limited
- AIA Group → Symbol: 01299, Company: AIA Group Limited

Respond in this exact format: "Symbol: [5-digit code], Company: [official company name]"
If not found, respond "NOT_FOUND".

Company: {company_name}
Response:"""

    def _try_grounded_lookup(
        self, prompt: str, company_name: str
    ) -> Optional[Dict[str, str]]:
        """Attempt symbol and company name lookup using Google Search grounding."""
        try:
            # Use grounding-specific model that supports Google Search grounding
            grounding_config = self.MODEL_CONFIGS["grounding"]
            grounding_model_name = os.getenv(
                grounding_config["env_var"], grounding_config["default"]
            )

            grounded_model = GenerativeModel(
                grounding_model_name,
                tools=[
                    Tool.from_google_search_retrieval(grounding.GoogleSearchRetrieval())
                ],
            )

            logger.debug(f"Using grounding model: {grounding_model_name}")

            response = grounded_model.generate_content(
                prompt, generation_config=self.LOOKUP_CONFIG
            )

            if response.text:
                result = self._extract_symbol_and_company_from_response(
                    response.text.strip()
                )
                if result:
                    logger.info(
                        f"Grounded lookup successful: {company_name} → {result['symbol']} ({result['company_name']})"
                    )
                    return result

        except Exception as e:
            logger.warning(f"Grounded lookup failed for {company_name}: {e}")

        return None

    def _try_fallback_lookup(
        self, prompt: str, company_name: str
    ) -> Optional[Dict[str, str]]:
        """Attempt symbol and company name lookup using regular Gemini without grounding."""
        try:
            response = self.model.generate_content(
                prompt, generation_config=self.LOOKUP_CONFIG
            )

            if response.text:
                result = self._extract_symbol_and_company_from_response(
                    response.text.strip()
                )
                if result:
                    logger.info(
                        f"Fallback lookup successful: {company_name} → {result['symbol']} ({result['company_name']})"
                    )
                    return result

            logger.warning(f"Could not find stock symbol for: {company_name}")

        except Exception as e:
            logger.error(f"Fallback lookup failed for {company_name}: {e}")

        return None

    def _extract_symbol_and_company_from_response(
        self, response_text: str
    ) -> Optional[Dict[str, str]]:
        """Extract stock symbol and company name from structured Gemini response.

        Expected format: "Symbol: 00005, Company: HSBC Holdings Limited"
        """
        if not response_text:
            return None

        # Handle "NOT_FOUND" response
        if "NOT_FOUND" in response_text.upper():
            return None

        # Parse structured response format
        pattern = r"Symbol:\s*(\d{1,5}),\s*Company:\s*(.+)"
        match = re.search(pattern, response_text, re.IGNORECASE)

        if match:
            symbol_raw = match.group(1)
            company_name = match.group(2).strip()

            # Format symbol to 5 digits
            symbol = symbol_raw.zfill(5)

            # Validate company name
            if company_name and len(company_name) > 2:
                return {"symbol": symbol, "company_name": company_name}

        # Fallback: try to extract just the symbol using old method
        symbol = self._extract_symbol_from_response(response_text)
        if symbol:
            logger.warning(f"Could only extract symbol from response: {response_text}")
            # Use a generic company name as fallback
            return {"symbol": symbol, "company_name": f"Company {symbol}"}

        return None

    def _extract_symbol_from_response(self, response_text: str) -> Optional[str]:
        """Extract stock symbol from Gemini response text."""
        if not response_text:
            return None

        # Handle "NOT_FOUND" response
        if "NOT_FOUND" in response_text.upper():
            return None

        # Look for 5-digit patterns (most common for HK stocks)
        five_digit_match = re.search(r"\b(\d{5})\b", response_text)
        if five_digit_match:
            return five_digit_match.group(1)

        # Look for shorter digit patterns and pad them
        digit_match = re.search(r"\b(\d{1,4})\b", response_text)
        if digit_match:
            symbol = digit_match.group(1)
            # Pad to 5 digits
            return symbol.zfill(5)

        # Look for patterns like "0005.HK" or "5.HK"
        hk_pattern_match = re.search(r"\b(\d{1,5})\.HK\b", response_text, re.IGNORECASE)
        if hk_pattern_match:
            symbol = hk_pattern_match.group(1)
            return symbol.zfill(5)

        return None
