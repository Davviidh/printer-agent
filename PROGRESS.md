# Progress

## Done (13 Oct)
- Setup: Python 3.11.2, `.venv`, libraries installed with uv.
- `connector.py`: the only code that touches the real printer (lp, cancel, lpstat, ioreg).
  Safety: 20-sheet cap, 60 s stuck flag, every call logged to `logs/actions.jsonl`.
- Real printer tests: job 130 (bug: all 4 pages printed), job 131 (fixed: 1 page).
- `sim_printer.py`: fake printer with the same functions, fake clock, faults "stuck" and "fail".
- `printer_server.py`: MCP server with 5 tools, backend chosen by PRINTER_BACKEND=sim|real.
  Tested on the simulator from a small client.
- LLM: OpenRouter free model nvidia/nemotron-3-super-120b-a12b:free (Gemini free tier was only 20/day). Keys in `.env` (git-ignored).
- `planner.py`: sentence -> print order (no tools), asks when the file is missing or the request is not about printing.

- `graph.py`: full loop planner -> executor (preview) -> approval -> executor (submit, read) -> checker (David's table) with wait / retry / cancel / done. Tested on the simulator: normal, fail, stuck, off. First real run 13 Oct: job 132, 1 page, human confirmed.

- `finder.py`: finds the PDF to print only inside ~/Downloads (case, typos, partial names; several matches -> human picks; links outside Downloads ignored). Used by the executor. Evals use FINDER_DIR=test_docs.

- `doc_finder.py`: if the file is not in Downloads, searches arXiv (only arxiv.org, allowlist checked on every redirect), shows 3 results, downloads only the one the human picks, PDF header and 30 MB checked, saved into Downloads.

## Done (14 Oct): part 2 on the fake printer
David decided not to submit the homework; the project is for himself and for learning.
- `quality/test_page.py`: test page, 5 lines of random letters per size, 4 to 12 pt.
- `quality/measure.py`: Tesseract OCR, character error rate per size.
- `quality/sim_print.py`: fake printer + phone photo (density, toner save, gamma), no paper.
- `quality/optimise.py`: Bayesian optimisation (GP + expected improvement), 12 tries.
  Score = readability - 0.05 x toner (toner relative to a perfect print), David's choice "balanced".
  Final answer = GP's predicted best (not the luckiest try). `--save-images` keeps the fake prints.
- `quality/check_all.py`: answer key, all 128 settings. Latest: both picks within 0.01 of the best;
  the top is flat (density 9-11 save off, or 12-13 save on).

## Next (ideas, nothing required)
- Tie-breaker: among near-equal settings pick the one with least toner.
- Real printer for part 2: ~10 scrap sheets, David photographs, same loop (needs photo import + page alignment).
- Part 1 extras: two-sided printing test, chapters via PDF bookmarks, full eval rerun.
