"""
LLM Client for interacting with Anthropic and OpenAI APIs.
"""

from typing import Optional, Dict, Any
import os
import logging
import anthropic
import openai

logger = logging.getLogger(__name__)


class LLMClient:
    """
    Unified client for Anthropic and OpenAI APIs.

    Handles API calls, error handling, and response formatting.
    """

    def __init__(self):
        """Initialize API clients with credentials from environment variables"""
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")

        # Initialize clients if keys are present
        self.anthropic_client = None
        self.openai_client = None

        if self.anthropic_api_key:
            self.anthropic_client = anthropic.Anthropic(api_key=self.anthropic_api_key)
            logger.info("Anthropic client initialized")
        else:
            logger.warning("ANTHROPIC_API_KEY not set")

        if self.openai_api_key:
            self.openai_client = openai.OpenAI(api_key=self.openai_api_key)
            logger.info("OpenAI client initialized")
        else:
            logger.warning("OPENAI_API_KEY not set")

    async def generate(
        self,
        question: str,
        provider: str = "anthropic",
        model: Optional[str] = None,
        max_tokens: int = 1024,
        context: Optional[Dict[str, Any]] = None
    ) -> str:
        """
        Generate a response from the specified LLM provider.

        Args:
            question: The user's question/prompt
            provider: "anthropic" or "openai"
            model: Specific model to use (optional)
            max_tokens: Maximum tokens in response
            context: Additional context for the conversation

        Returns:
            The LLM's response as a string

        Raises:
            ValueError: If provider is invalid or API key not set
            Exception: For API errors
        """
        if provider == "anthropic":
            return await self._generate_anthropic(question, model, max_tokens, context)
        elif provider == "openai":
            return await self._generate_openai(question, model, max_tokens, context)
        else:
            raise ValueError(f"Unknown provider: {provider}")

    async def _generate_anthropic(
        self,
        question: str,
        model: Optional[str],
        max_tokens: int,
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Generate response using Anthropic's API"""
        if not self.anthropic_client:
            raise ValueError("Anthropic API key not configured")

        try:
            # Default to Claude 3.5 Sonnet if no model specified
            if not model:
                model = "claude-3-5-sonnet-20241022"

            # Build messages array
            messages = []

            # Add context if provided
            if context and context.get("conversation_history"):
                messages.extend(context["conversation_history"])

            # Add current question
            messages.append({
                "role": "user",
                "content": question
            })

            logger.info(f"Calling Anthropic API with model {model}")

            # Call Anthropic API
            response = self.anthropic_client.messages.create(
                model=model,
                max_tokens=max_tokens,
                messages=messages
            )

            # Extract text from response
            result = response.content[0].text

            logger.info(f"Anthropic API call successful, response length: {len(result)}")

            return result

        except anthropic.APIError as e:
            logger.error(f"Anthropic API error: {str(e)}")
            raise Exception(f"Anthropic API error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error calling Anthropic: {str(e)}")
            raise

    async def _generate_openai(
        self,
        question: str,
        model: Optional[str],
        max_tokens: int,
        context: Optional[Dict[str, Any]]
    ) -> str:
        """Generate response using OpenAI's API"""
        if not self.openai_client:
            raise ValueError("OpenAI API key not configured")

        try:
            # Default to GPT-4 if no model specified
            if not model:
                model = "gpt-4-turbo-preview"

            # Build messages array
            messages = []

            # Add system message if provided in context
            if context and context.get("system_message"):
                messages.append({
                    "role": "system",
                    "content": context["system_message"]
                })

            # Add conversation history if provided
            if context and context.get("conversation_history"):
                messages.extend(context["conversation_history"])

            # Add current question
            messages.append({
                "role": "user",
                "content": question
            })

            logger.info(f"Calling OpenAI API with model {model}")

            # Call OpenAI API
            response = self.openai_client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=max_tokens
            )

            # Extract text from response
            result = response.choices[0].message.content

            logger.info(f"OpenAI API call successful, response length: {len(result)}")

            return result

        except openai.APIError as e:
            logger.error(f"OpenAI API error: {str(e)}")
            raise Exception(f"OpenAI API error: {str(e)}")
        except Exception as e:
            logger.error(f"Unexpected error calling OpenAI: {str(e)}")
            raise

    def is_anthropic_available(self) -> bool:
        """Check if Anthropic API is configured"""
        return self.anthropic_client is not None

    def is_openai_available(self) -> bool:
        """Check if OpenAI API is configured"""
        return self.openai_client is not None
