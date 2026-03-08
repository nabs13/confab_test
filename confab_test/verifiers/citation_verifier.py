"""
Citation Verifier — checks ISBNs, arxiv IDs, and DOIs against public APIs.

APIs used (all free, no key required):
  - Open Library  https://openlibrary.org/api/books
  - arXiv         https://arxiv.org/abs/<id>  (HTTP check only)
  - doi.org       https://doi.org/<doi>       (redirect check)
"""
from __future__ import annotations

import asyncio
import re

import httpx

_HEADERS = {
    "User-Agent": "confab-test/0.1 (citation-verification-research)"
}


class CitationVerifier:
    def __init__(self, timeout: float = 15) -> None:
        self.timeout = timeout

    # ------------------------------------------------------------------
    # ISBNs
    # ------------------------------------------------------------------
    async def check_isbns(self, isbns: list[str]) -> list[dict]:
        """Check each ISBN against Open Library. Returns list of result dicts."""
        tasks = [self._check_isbn(isbn) for isbn in isbns]
        return await asyncio.gather(*tasks)

    async def _check_isbn(self, isbn: str) -> dict:
        clean = re.sub(r"[^0-9X]", "", isbn.upper())
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{clean}&format=json&jscmd=data"
        try:
            async with httpx.AsyncClient(timeout=self.timeout, headers=_HEADERS) as c:
                r = await c.get(url)
                r.raise_for_status()
                data = r.json()
            key = f"ISBN:{clean}"
            if key in data:
                book = data[key]
                return {
                    "isbn": clean,
                    "exists": True,
                    "title": book.get("title", ""),
                    "authors": [a.get("name", "") for a in book.get("authors", [])],
                }
            return {"isbn": clean, "exists": False, "title": None, "authors": []}
        except Exception as e:
            return {"isbn": clean, "exists": False, "error": str(e)}

    # ------------------------------------------------------------------
    # arXiv IDs
    # ------------------------------------------------------------------
    async def check_arxiv_ids(self, ids: list[str]) -> list[dict]:
        tasks = [self._check_arxiv(arxiv_id) for arxiv_id in ids]
        return await asyncio.gather(*tasks)

    async def _check_arxiv(self, arxiv_id: str) -> dict:
        # Strip version suffix for the abs URL
        base_id = re.sub(r"v\d+$", "", arxiv_id)
        abs_url = f"https://arxiv.org/abs/{base_id}"
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True, headers=_HEADERS
            ) as c:
                r = await c.get(abs_url)
                exists = r.status_code == 200
                # If page exists, try to extract title
                title = None
                if exists:
                    m = re.search(
                        r'<h1 class="title mathjax"><span class="descriptor">Title:</span>(.*?)</h1>',
                        r.text,
                        re.DOTALL,
                    )
                    if m:
                        title = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                return {"id": arxiv_id, "exists": exists, "url": abs_url, "title": title}
        except Exception as e:
            return {"id": arxiv_id, "exists": False, "error": str(e)}

    # ------------------------------------------------------------------
    # DOIs
    # ------------------------------------------------------------------
    async def check_dois(self, dois: list[str]) -> list[dict]:
        tasks = [self._check_doi(doi) for doi in dois]
        return await asyncio.gather(*tasks)

    async def _check_doi(self, doi: str) -> dict:
        url = f"https://doi.org/{doi}"
        try:
            async with httpx.AsyncClient(
                timeout=self.timeout, follow_redirects=True, headers=_HEADERS
            ) as c:
                r = await c.head(url)
                resolves = r.status_code < 400
                return {
                    "doi": doi,
                    "resolves": resolves,
                    "final_url": str(r.url),
                    "status_code": r.status_code,
                }
        except Exception as e:
            return {"doi": doi, "resolves": False, "error": str(e)}
