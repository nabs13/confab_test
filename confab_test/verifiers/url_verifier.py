"""
URL Verifier — performs real HTTP HEAD requests to check URL existence.
Rate-limited to avoid triggering anti-bot measures.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import httpx


@dataclass
class UrlStatus:
    url: str
    code: int | None      # HTTP status code, or None on error
    ok: bool              # True if 2xx or 3xx
    error: str | None     # Error message if request failed
    final_url: str | None # URL after redirects
    content_type: str | None

    @classmethod
    def from_error(cls, url: str, error: str) -> "UrlStatus":
        return cls(url=url, code=None, ok=False, error=error,
                   final_url=None, content_type=None)


class UrlVerifier:
    def __init__(self, timeout: float = 10, rate_limit: float = 1.0) -> None:
        self.timeout = timeout
        # rate_limit = requests per second; convert to min delay between requests
        self._delay = 1.0 / max(rate_limit, 0.1)
        self._sem = asyncio.Semaphore(3)  # max 3 concurrent requests

    async def check(self, url: str) -> UrlStatus:
        """Check a single URL."""
        async with self._sem:
            return await self._do_check(url)

    async def check_many(self, urls: list[str]) -> list[UrlStatus]:
        """Check multiple URLs, rate-limited."""
        results = []
        for url in urls:
            status = await self.check(url)
            results.append(status)
            await asyncio.sleep(self._delay)
        return results

    async def _do_check(self, url: str) -> UrlStatus:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (compatible; confab-test/0.1; "
                "link-verification-research-tool)"
            )
        }
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout,
                follow_redirects=True,
                headers=headers,
            ) as client:
                # Try HEAD first (lighter), fall back to GET if blocked
                try:
                    resp = await client.head(url)
                    if resp.status_code == 405:
                        resp = await client.get(url)
                except httpx.HTTPError:
                    resp = await client.get(url)

                code = resp.status_code
                ok = 200 <= code < 400
                ct = resp.headers.get("content-type", "")
                return UrlStatus(
                    url=url,
                    code=code,
                    ok=ok,
                    error=None,
                    final_url=str(resp.url),
                    content_type=ct,
                )
        except httpx.TimeoutException:
            return UrlStatus.from_error(url, "Timeout")
        except httpx.ConnectError as e:
            return UrlStatus.from_error(url, f"Connection failed: {e}")
        except Exception as e:
            return UrlStatus.from_error(url, str(e))
