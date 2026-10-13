# Learnings

- `lpstat` says "idle" and "Alerts: none" even when the printer is off. Only
  `ioreg -p IOUSB` shows whether the Canon is really there.
- The Canon filter (`capdftopdl`) takes the PDF directly and skips the CUPS step that
  applies page-ranges, page-set, number-up and outputorder. `lp -o page-ranges=1` printed
  all 4 pages (job 130). Fix: the connector builds a new PDF with exactly the sheets to
  print, and only CN* driver options go to lp. The sheet cap is checked on that plan.
- CUPS "completed" only means the data reached the printer: job 131 was "completed" after
  1 s, the sheet came out after about 10 s. So a human has to confirm the pages.
- When the printer is off, a job waits as "pending" and also gets marked stuck after 60 s.
  The checker must look at printer presence before the stuck flag.
- The MCP Python SDK 2.x renamed FastMCP to MCPServer. Pinned to mcp<2 (1.30.0).
- Gemini: `gemini-2.5-flash` returns 404 for new keys. `gemini-flash-latest` works with
  tool calling (tested 13 Oct). It is an alias, so the model behind it can change.
- python.org Python on this Mac fails SSL with urllib (no certificates installed); httpx
  (certifi) works. `load_dotenv()` needs an explicit path when run from stdin.
- Gemini free tier: only 20 requests per day per model for gemini-flash-latest
  (GenerateRequestsPerDayPerProjectPerModel-FreeTier), and frequent 503 "high demand"
  errors. LangChain's default retries burn the quota fast, so planner uses max_retries=1.
  20 a day is too few for a 30-request eval set.
- OpenRouter free models (13 Oct): nvidia/nemotron-3-super-120b-a12b:free works with
  structured output (~12 s). gemma-4-31b-it:free was rate-limited upstream;
  thinkingmachines/inkling:free returns 403 (only for "agentic harnesses").
  Nemotron first put "odd" into page_ranges and changed toner unasked; fixed with a regex
  pattern on page_ranges and a stricter prompt.
- langchain-mcp-adapters: `client.get_tools()` opens a new server session per tool call, so
  the simulator would forget jobs between submit and job_status. graph.py keeps one
  `client.session(...)` open for the whole run. `handle_tool_errors=False` so tool errors raise.
- Evals (13 Oct, 15 cases): 14/15. The planner turned "50 copies" silently into 5 (the
  schema's max) and printed. Fix (David's rule: never change the request): no upper limit
  on copies in the planner's schema, a prompt rule to copy the number and ask, and the
  printer side refuses over 5. Lesson: a schema limit makes the model clamp silently.
