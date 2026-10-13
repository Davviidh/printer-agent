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

## Next
- Four-role LangGraph agent graph (planner, human approval, executor with the MCP tools, checker).
- Then: Downloads file finder, document finder, manual two-sided printing test, evals, part 2.
