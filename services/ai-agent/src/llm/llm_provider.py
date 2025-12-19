"""
LLM Provider abstraction layer using LiteLLM.
Provides a unified interface for multiple LLM providers with built-in rate limiting.
"""

import os
import time
from typing import Optional, List, Any
from dataclasses import dataclass

import litellm
from litellm import completion, embedding
from litellm.exceptions import RateLimitError, APIError, ServiceUnavailableError

from llm.rate_limiter import SmartRateLimiter


@dataclass
class LLMResponse:
    """Standardized LLM response."""
    text: str
    model: str
    usage: dict
    raw_response: Any = None


class LLMProvider:
    """
    Unified LLM provider with rate limiting and retry logic.
    
    Features:
    - Multiple provider support via LiteLLM
    - Smart rate limiting with Retry-After header support
    - Automatic retries with exponential backoff
    - Easy provider switching via environment variables
    
    Usage:
        llm = LLMProvider()  # Uses GEMINI_API_KEY env var
        response = llm.generate("Analyze this incident...")
        
        # Or with explicit config:
        llm = LLMProvider(
            model="gemini/gemini-2.5-flash",
            max_retries=5,
            rate_limit_rpm=5
        )
    """
    
    # Model prefixes for different providers
    PROVIDER_PREFIXES = {
        'gemini': 'gemini/',
        'openai': 'openai/',
        'anthropic': 'anthropic/',
        'ollama': 'ollama/',
        'azure': 'azure/',
        'huggingface': 'huggingface/',
    }
    
    def __init__(
        self,
        model: Optional[str] = None,
        max_retries: int = 5,
        rate_limit_rpm: float = 5.0,
        rate_limit_enabled: bool = True,
        timeout: float = 120.0,
    ):
        """
        Initialize the LLM provider.
        
        Args:
            model: LiteLLM model string (e.g., "gemini/gemini-2.5-flash")
                   Defaults to LLM_MODEL env var or "gemini/gemini-2.5-flash"
            max_retries: Maximum retry attempts for failed calls
            rate_limit_rpm: Requests per minute limit (set high for self-hosted)
            rate_limit_enabled: Enable/disable rate limiting
            timeout: Request timeout in seconds
        """
        self.model = model or os.getenv("LLM_MODEL", "gemini/gemini-2.5-flash")
        self.max_retries = max_retries
        self.timeout = timeout
        
        # Configure rate limiting
        env_rpm = os.getenv("LLM_RATE_LIMIT_RPM")
        if env_rpm:
            rate_limit_rpm = float(env_rpm)
        
        # Disable rate limiting for self-hosted (high RPM = effectively disabled)
        if rate_limit_rpm >= 1000:
            rate_limit_enabled = False
        
        self.rate_limiter = SmartRateLimiter(
            requests_per_minute=rate_limit_rpm,
            enabled=rate_limit_enabled
        )
        
        # Configure LiteLLM
        litellm.set_verbose = os.getenv("LLM_DEBUG", "false").lower() == "true"
        
        # Set API keys from environment
        self._configure_api_keys()
        
        print(f"LLM Provider initialized: model={self.model}, rpm={rate_limit_rpm}, retries={max_retries}")
    
    def _configure_api_keys(self) -> None:
        """Configure API keys for various providers from environment."""
        # Gemini
        if os.getenv("GEMINI_API_KEY"):
            os.environ["GEMINI_API_KEY"] = os.getenv("GEMINI_API_KEY")
        
        # OpenAI (for fallback or primary)
        if os.getenv("OPENAI_API_KEY"):
            os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")
        
        # Anthropic
        if os.getenv("ANTHROPIC_API_KEY"):
            os.environ["ANTHROPIC_API_KEY"] = os.getenv("ANTHROPIC_API_KEY")
        
        # Ollama base URL (for self-hosted)
        if os.getenv("OLLAMA_API_BASE"):
            os.environ["OLLAMA_API_BASE"] = os.getenv("OLLAMA_API_BASE")
    
    def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Generate a response from the LLM.
        
        Args:
            prompt: The user prompt
            system_prompt: Optional system prompt
            temperature: Sampling temperature (0.0-1.0)
            max_tokens: Maximum tokens to generate
            **kwargs: Additional arguments passed to LiteLLM
            
        Returns:
            Generated text response
            
        Raises:
            Exception: If all retries fail
        """
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        
        messages.append({"role": "user", "content": prompt})
        
        return self._call_with_retry(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            **kwargs
        )
    
    def _call_with_retry(
        self,
        messages: List[dict],
        temperature: float = 0.7,
        max_tokens: Optional[int] = None,
        **kwargs
    ) -> str:
        """
        Call LLM with retry logic and rate limiting.
        
        Handles:
        - Rate limiting (proactive + reactive)
        - Automatic retries with exponential backoff
        - Retry-After header parsing
        """
        last_error = None
        
        for attempt in range(self.max_retries):
            try:
                # Wait for rate limit token
                self.rate_limiter.acquire()
                
                # Make the API call
                response = completion(
                    model=self.model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=max_tokens,
                    timeout=self.timeout,
                    **kwargs
                )
                
                # Extract response headers if available (for rate limit info)
                if hasattr(response, '_response') and hasattr(response._response, 'headers'):
                    self.rate_limiter.update_from_headers(dict(response._response.headers))
                
                # Extract text from response
                return response.choices[0].message.content
                
            except RateLimitError as e:
                last_error = e
                retry_after = self._extract_retry_after(e)
                self.rate_limiter.report_rate_limit_error(retry_after)
                
                print(f"LLM_PROVIDER: Rate limit hit (attempt {attempt + 1}/{self.max_retries})")
                
                # Wait before retry
                wait_time = retry_after if retry_after else (2 ** attempt) * 10
                wait_time = min(wait_time, 120)  # Cap at 2 minutes
                print(f"LLM_PROVIDER: Waiting {wait_time:.1f}s before retry...")
                time.sleep(wait_time)
                
            except (APIError, ServiceUnavailableError) as e:
                last_error = e
                wait_time = (2 ** attempt) * 5  # Exponential backoff
                wait_time = min(wait_time, 60)
                
                print(f"LLM_PROVIDER: API error (attempt {attempt + 1}/{self.max_retries}): {e}")
                print(f"LLM_PROVIDER: Waiting {wait_time:.1f}s before retry...")
                time.sleep(wait_time)
                
            except Exception as e:
                last_error = e
                print(f"LLM_PROVIDER: Unexpected error (attempt {attempt + 1}/{self.max_retries}): {e}")
                
                if attempt < self.max_retries - 1:
                    wait_time = (2 ** attempt) * 2
                    time.sleep(wait_time)
        
        raise Exception(f"LLM call failed after {self.max_retries} attempts: {last_error}")
    
    def _extract_retry_after(self, error: Exception) -> Optional[float]:
        """Extract Retry-After value from error response."""
        # Try to get from error attributes
        if hasattr(error, 'response') and hasattr(error.response, 'headers'):
            headers = error.response.headers
            retry_after = headers.get('Retry-After') or headers.get('retry-after')
            if retry_after:
                try:
                    return float(retry_after)
                except (ValueError, TypeError):
                    pass
        
        # Try to parse from error message (Gemini format)
        error_str = str(error)
        if 'retry after' in error_str.lower():
            import re
            match = re.search(r'retry after (\d+)', error_str.lower())
            if match:
                return float(match.group(1))
        
        return None
    
    def embed(self, text: str, model: Optional[str] = None) -> List[float]:
        """
        Generate embeddings for text.
        
        Args:
            text: Text to embed
            model: Optional embedding model (defaults to provider's default)
            
        Returns:
            Embedding vector as list of floats
        """
        # Use appropriate embedding model based on provider
        embed_model = model
        if not embed_model:
            if self.model.startswith('gemini/'):
                embed_model = "gemini/text-embedding-004"
            elif self.model.startswith('openai/'):
                embed_model = "openai/text-embedding-3-small"
            else:
                # Default to OpenAI-compatible embeddings
                embed_model = "text-embedding-3-small"
        
        for attempt in range(self.max_retries):
            try:
                self.rate_limiter.acquire()
                
                response = embedding(
                    model=embed_model,
                    input=[text]
                )
                
                return response.data[0]['embedding']
                
            except RateLimitError as e:
                retry_after = self._extract_retry_after(e)
                self.rate_limiter.report_rate_limit_error(retry_after)
                
                wait_time = retry_after if retry_after else (2 ** attempt) * 10
                wait_time = min(wait_time, 120)
                print(f"LLM_PROVIDER: Embedding rate limit, waiting {wait_time:.1f}s...")
                time.sleep(wait_time)
                
            except Exception as e:
                if attempt == self.max_retries - 1:
                    raise
                wait_time = (2 ** attempt) * 2
                print(f"LLM_PROVIDER: Embedding error, retrying in {wait_time}s: {e}")
                time.sleep(wait_time)
        
        raise Exception(f"Embedding call failed after {self.max_retries} attempts")
