"""Document finder: searches free, legal sources on the internet.

For now only arXiv (every paper there is a free PDF). Safety rules:
- allowlist: only arxiv.org / export.arxiv.org are ever contacted
- search never downloads; download() is only called after a human
  picked a result
- the download must really be a PDF (header "%PDF") and under 30 MB
- files are saved only into ~/Downloads (FINDER_DIR for tests), where
  the local file finder looks
"""

import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import urlparse

import httpx

import finder

log = logging.getLogger("doc_finder")

ALLOWED_HOSTS = {"arxiv.org", "export.arxiv.org"}
MAX_BYTES = 30 * 1024 * 1024
ATOM = {"a": "http://www.w3.org/2005/Atom"}
ARXIV_ID = re.compile(r"\b(\d{4}\.\d{4,5})(v\d+)?\b")


def _get(url, params=None):
    """GET that follows redirects by hand, checking every hop is allowed."""
    for _ in range(4):
        host = urlparse(url).hostname
        if host not in ALLOWED_HOSTS:
            log.error(f"blocked: {host} is not on the allowlist")
            raise PermissionError(f"{host} is not an allowed source")
        r = httpx.get(url, params=params, timeout=60, follow_redirects=False)
        if r.is_redirect:
            url, params = str(r.next_request.url), None
            continue
        r.raise_for_status()
        return r
    raise RuntimeError(f"too many redirects for {url}")


def _query(search_query, n):
    r = _get("https://export.arxiv.org/api/query",
             params={"search_query": search_query, "max_results": n,
                     "sortBy": "relevance"})
    out = []
    for e in ET.fromstring(r.text).findall("a:entry", ATOM):
        arxiv_id = e.find("a:id", ATOM).text.rsplit("/abs/", 1)[-1]
        out.append({
            "id": arxiv_id,
            "title": " ".join(e.find("a:title", ATOM).text.split()),
            "authors": [a.find("a:name", ATOM).text for a in e.findall("a:author", ATOM)],
            "year": e.find("a:published", ATOM).text[:4],
            "pdf_url": f"https://arxiv.org/pdf/{arxiv_id}",
        })
    return out


def search_arxiv(text, n=3):
    """Find papers by arXiv id, exact title, or all words. Never downloads."""
    m = ARXIV_ID.search(text)
    if m:
        results = _query(f"id:{m.group(1)}", 1)
    else:
        words = [w for w in re.findall(r"\w+", text.lower()) if w not in finder.FILLER]
        if not words:
            return []
        results = _query(f'ti:"{" ".join(words)}"', n) \
            or _query(" AND ".join(f"all:{w}" for w in words), n)
    log.info(f"search_arxiv({text!r}) -> {[r['id'] for r in results]}")
    return results


def download(paper):
    """Save a paper the human picked into the Downloads folder."""
    r = _get(paper["pdf_url"])
    if not r.content.startswith(b"%PDF"):
        raise ValueError(f"{paper['pdf_url']} did not return a PDF")
    if len(r.content) > MAX_BYTES:
        raise ValueError(f"{paper['pdf_url']} is over {MAX_BYTES // 2**20} MB")
    slug = re.sub(r"[^a-z0-9]+", "_", paper["title"].lower()).strip("_")[:60]
    dest = finder.search_dir() / f"arxiv_{paper['id'].replace('/', '_')}_{slug}.pdf"
    dest.write_bytes(r.content)
    log.info(f"downloaded {paper['pdf_url']} -> {dest} ({len(r.content)} bytes)")
    return str(dest)
