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

## Next (as of 13 Oct, end of day)
Homework items first:
1. Architecture diagram and sequence diagrams of real runs.
2. Use cases: real runs written as request -> what the printer did -> what the agent decided (logs have them).
3. Video of a real run.
4. Submission: one PDF, GitHub link, email to aramsargsyan@ysu.am.
Then: part 2 (test page, photo, OCR, Bayesian optimisation of toner settings).
Extras: two-sided printing test (4-page doc), chapters via PDF bookmarks, rerun all 17 evals (free model limit ~50/day).
