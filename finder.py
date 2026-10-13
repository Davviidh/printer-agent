"""File finder: finds the document to print, ONLY inside ~/Downloads.

Safety rules:
- only looks in one folder (~/Downloads, or FINDER_DIR for tests)
- only returns PDFs whose real path is inside that folder, so a link
  pointing elsewhere (for example to ~/Documents) is ignored
- never guesses between several candidates: it returns them all and the
  human picks

Matching forgives small differences: case, missing ".pdf", "_" vs " ",
and typos ("alice in wonderlnd" finds "Alice_in_Wonderland.pdf").
"""

import difflib
import logging
import os
import re
from pathlib import Path

log = logging.getLogger("finder")

MAX_DEPTH = 3          # how deep into subfolders of Downloads to look
CLOSE_ENOUGH = 0.75    # similarity needed for a typo match (0 to 1)


def search_dir():
    return Path(os.environ.get("FINDER_DIR", Path.home() / "Downloads")).resolve()


# words people say around a name that are not part of it
FILLER = {"the", "my", "a", "an", "document", "doc", "file", "pdf", "book", "paper", "article"}


def _norm(name):
    """'the Alice_in-Wonderland.PDF book' -> 'alice in wonderland'"""
    name = re.sub(r"\.pdf$", "", name.strip().lower())
    words = re.sub(r"[\s_\-.]+", " ", name).split()
    return " ".join(w for w in words if w not in FILLER)


def _pdfs(root):
    for dirpath, dirnames, filenames in os.walk(root):
        depth = Path(dirpath).relative_to(root).parts
        if len(depth) >= MAX_DEPTH:
            dirnames.clear()
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for f in filenames:
            p = Path(dirpath) / f
            if f.lower().endswith(".pdf") and p.resolve().is_relative_to(root):
                yield p.resolve()


def find(name):
    """Returns {"path": ...} for one clear match, {"choices": [...]} if
    several files fit, or {"error": ...} if nothing fits."""
    root = search_dir()
    if not name or not name.strip():
        return {"error": "no file name given"}
    want = _norm(Path(name).name)
    files = list(_pdfs(root))

    exact = [p for p in files if _norm(p.name) == want]
    if not exact:
        # name is part of the file name: "alice" -> "alice in wonderland"
        exact = [p for p in files if want and want in _norm(p.name)]
    if not exact:
        scored = [(difflib.SequenceMatcher(None, want, _norm(p.name)).ratio(), p) for p in files]
        exact = [p for r, p in sorted(scored, reverse=True) if r >= CLOSE_ENOUGH]

    if len(exact) == 1:
        result = {"path": str(exact[0])}
    elif exact:
        result = {"choices": [str(p) for p in exact[:5]]}
    else:
        result = {"error": f"no PDF matching '{name}' in {root}"}
    log.info(f"find({name!r}) in {root} -> {result}")
    return result
