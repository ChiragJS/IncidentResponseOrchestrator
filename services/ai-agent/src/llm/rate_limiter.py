"""
Rate limiter with Retry-After header support for LLM API calls.
Implements token bucket algorithm with dynamic adjustment based on API feedback.
"""

import time
import threading
from dataclasses import dataclass
from typing import Optional


@dataclass
class RateLimitState:
    """Tracks rate limit state including API feedback."""
    tokens: float
    last_refill: float
    retry_after: Optional[float] = None
    retry_after_until: Optional[float] = None


class SmartRateLimiter:
    """
    Token bucket rate limiter with Retry-After header support.
    
    Features:
    - Proactive rate limiting (token bucket)
    - Reactive rate limiting (Retry-After header parsing)
    - Thread-safe
    - Dynamic adjustment based on API feedback
    """
    
    def __init__(
        self,
        requests_per_minute: float = 5.0,  # Gemini free tier default
        burst_size: Optional[int] = None,
        enabled: bool = True
    ):
        """
        Initialize the rate limiter.
        
        Args:
            requests_per_minute: Sustained request rate limit
            burst_size: Max burst size (defaults to requests_per_minute)
            enabled: Whether rate limiting is active (disable for self-hosted)
        """
        self.rpm = requests_per_minute
        self.tokens_per_second = requests_per_minute / 60.0
        self.max_tokens = burst_size if burst_size else max(1, int(requests_per_minute))
        self.enabled = enabled
        
        self._state = RateLimitState(
            tokens=self.max_tokens,
            last_refill=time.monotonic()
        )
        self._lock = threading.Lock()
    
    def acquire(self, timeout: Optional[float] = None) -> bool:
        """
        Acquire a token, waiting if necessary.
        
        Args:
            timeout: Max time to wait (None = wait forever)
            
        Returns:
            True if token acquired, False if timed out
        """
        if not self.enabled:
            return True
        
        start_time = time.monotonic()
        
        while True:
            wait_time = self._try_acquire()
            
            if wait_time == 0:
                return True
            
            # Check timeout
            if timeout is not None:
                elapsed = time.monotonic() - start_time
                if elapsed + wait_time > timeout:
                    return False
            
            print(f"RATE_LIMITER: Waiting {wait_time:.1f}s before next request...")
            time.sleep(min(wait_time, 1.0))  # Sleep in chunks for responsiveness
    
    def _try_acquire(self) -> float:
        """
        Try to acquire a token.
        
        Returns:
            0 if acquired, otherwise seconds to wait
        """
        with self._lock:
            now = time.monotonic()
            
            # Check if we're in a Retry-After window
            if self._state.retry_after_until and now < self._state.retry_after_until:
                return self._state.retry_after_until - now
            
            # Refill tokens
            elapsed = now - self._state.last_refill
            self._state.tokens = min(
                self.max_tokens,
                self._state.tokens + elapsed * self.tokens_per_second
            )
            self._state.last_refill = now
            
            # Try to consume a token
            if self._state.tokens >= 1.0:
                self._state.tokens -= 1.0
                return 0
            
            # Calculate wait time for next token
            tokens_needed = 1.0 - self._state.tokens
            return tokens_needed / self.tokens_per_second
    
    def update_from_headers(self, headers: dict) -> None:
        """
        Update rate limit state from API response headers.
        
        Handles:
        - Retry-After (standard)
        - X-Retry-After (custom)
        - X-RateLimit-Reset (epoch timestamp)
        
        Args:
            headers: Response headers dict
        """
        if not self.enabled:
            return
        
        retry_after = None
        
        # Check standard Retry-After header (seconds or HTTP-date)
        if 'Retry-After' in headers:
            retry_after = self._parse_retry_after(headers['Retry-After'])
        elif 'retry-after' in headers:
            retry_after = self._parse_retry_after(headers['retry-after'])
        elif 'X-Retry-After' in headers:
            retry_after = self._parse_retry_after(headers['X-Retry-After'])
        elif 'x-retry-after' in headers:
            retry_after = self._parse_retry_after(headers['x-retry-after'])
        
        # Check rate limit reset (epoch timestamp)
        reset_header = headers.get('X-RateLimit-Reset') or headers.get('x-ratelimit-reset')
        if reset_header and not retry_after:
            try:
                reset_time = float(reset_header)
                retry_after = max(0, reset_time - time.time())
            except (ValueError, TypeError):
                pass
        
        if retry_after and retry_after > 0:
            with self._lock:
                self._state.retry_after = retry_after
                self._state.retry_after_until = time.monotonic() + retry_after
                print(f"RATE_LIMITER: Received Retry-After header, waiting {retry_after:.1f}s")
    
    def _parse_retry_after(self, value: str) -> Optional[float]:
        """Parse Retry-After header value (seconds or HTTP-date)."""
        try:
            # Try as seconds first
            return float(value)
        except (ValueError, TypeError):
            pass
        
        # Try as HTTP-date (e.g., "Wed, 21 Oct 2015 07:28:00 GMT")
        try:
            from email.utils import parsedate_to_datetime
            dt = parsedate_to_datetime(value)
            return max(0, (dt.timestamp() - time.time()))
        except Exception:
            pass
        
        return None
    
    def report_rate_limit_error(self, retry_after: Optional[float] = None) -> None:
        """
        Report a rate limit error (429 response).
        
        If no Retry-After value provided, uses exponential backoff.
        
        Args:
            retry_after: Seconds to wait (from header) or None for default
        """
        if not self.enabled:
            return
        
        with self._lock:
            if retry_after:
                wait_time = retry_after
            else:
                # Default backoff: 60 seconds for Gemini free tier
                wait_time = 60.0
            
            self._state.retry_after = wait_time
            self._state.retry_after_until = time.monotonic() + wait_time
            # Drain tokens to prevent immediate retry
            self._state.tokens = 0
            
            print(f"RATE_LIMITER: Rate limit hit, backing off for {wait_time:.1f}s")
    
    @property
    def available_tokens(self) -> float:
        """Current available tokens (for monitoring)."""
        with self._lock:
            now = time.monotonic()
            elapsed = now - self._state.last_refill
            return min(
                self.max_tokens,
                self._state.tokens + elapsed * self.tokens_per_second
            )
