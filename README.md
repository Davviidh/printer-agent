# Printer agent

An AI print assistant for a real office printer (Canon i-SENSYS LBP6020B on USB).
You ask in plain language, for example "print only odd pages of report.pdf, save toner".
The agent plans the job, shows you a summary, prints only after you say yes, and then
watches the printer and decides what to do next (done, retry, cancel, or ask you).

Homework 3 for the course "AI-driven science and autonomous laboratories":
a closed loop of decide, command the hardware, read the result, decide again.

## How it works

```
your sentence
   |
planner   (LLM, no printer tools)       turns the sentence into a print order
   |
executor  (the only one with tools)     asks the printer: are you on? what would this print?
   |
approval  (you)                          see the summary, answer yes / no
   |  no -> stop
   |  yes
executor                                 sends the job, then reads the printer every 3 s
   |
checker   (no tools)                     decides from the readings:
                                         printer off      -> ask you to switch it on, keep watching
                                         finished         -> ask you to confirm the pages came out
                                         stuck over 60 s  -> ask you to check, never resend
                                         failed           -> ask you to check, offer a retry
```

| File | What it does |
|---|---|
| `connector.py` | The only code that touches the real printer (CUPS `lp`, `lpstat`, `cancel`, and `ioreg` for USB). Safety: 20-sheet cap, 60 s stuck flag, every action logged to `logs/actions.jsonl`. |
| `sim_printer.py` | A fake printer with the same functions and the real printer's timing. Can fake "off", "stuck" and "fail". |
| `printer_server.py` | MCP server that offers the printer actions as 5 tools. |
| `planner.py` | Turns a sentence into a print order with an LLM. |
| `graph.py` | The LangGraph graph: planner, executor, approval, checker. |
| `LEARNINGS.md` | What we found out while building (read this, some of it is surprising). |
| `PROGRESS.md` | What is done and what is next. |

## Requirements

- macOS with CUPS (built in). The real-printer mode only works with a USB Canon queue;
  everything else works on any Mac using the simulator.
- Python 3.11 or newer.
- A free [OpenRouter](https://openrouter.ai) API key (the free models need no money).

## Download and install

The repository is private, so you need access to it first.

```
git clone https://github.com/Davviidh/printer-agent.git
cd printer-agent
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
```

## Add your API key

Create a file called `.env` in the project folder with this line:

```
OPENROUTER_API_KEY=sk-or-...your key...
```

`.env` is in `.gitignore`, so the key never goes to GitHub. Never paste it anywhere else.

The planner uses the free model `nvidia/nemotron-3-super-120b-a12b:free` by default.
To try another one: `PLANNER_MODEL=some/model:free .venv/bin/python graph.py "..."`.
Free models allow about 50 requests a day.

## Use it

### 1. Safe first: the simulated printer (no paper)

```
.venv/bin/python graph.py "print only odd pages of test_docs/four_pages.pdf, save toner"
```

You will see the print order:

```
PRINT ORDER - please check
File:      test_docs/four_pages.pdf (4 pages)
Pages:     odd -> [1, 3]
Layout:    1 page(s) per sheet, 1 copy/copies
Order:     normal
Paper:     2 sheet(s)
Toner:     density 4, save mode on
Printer:   ON
Warnings:  none
Reply: yes / no
```

Type `yes` or `no`. After `yes`, answer the checker's questions.

Try the problem cases on the simulator:

```
SIM_FAULT=fail  .venv/bin/python graph.py "print page 1 of test_docs/four_pages.pdf"   # job fails
SIM_FAULT=stuck .venv/bin/python graph.py "print page 1 of test_docs/four_pages.pdf"   # stuck, wait about 60 s
SIM_POWERED=0 SIM_ON_AFTER=20 .venv/bin/python graph.py "print page 1 of test_docs/four_pages.pdf"   # off, comes on after 20 s
```

### 2. The real printer

Switch the printer on, then:

```
PRINTER_BACKEND=real .venv/bin/python graph.py "print page 1 of test_docs/four_pages.pdf"
```

Nothing prints until you type `yes`. Start with one page.

### Things you can ask for

- pages: "pages 2 to 5", "pages 1, 3 and 7"
- odd or even pages: "only odd pages"
- reverse order: "in reverse order", "last page first"
- copies (1 to 5): "2 copies"
- pages per sheet (1, 2 or 4): "two pages per sheet"
- toner: "light toner", "very light", "dark", "save toner"

Only PDF files are supported. If you don't name a file, the agent asks for one.

### Other ways to run the parts

```
.venv/bin/python sim_printer.py            # the simulator in 4 situations, no LLM needed
.venv/bin/python planner.py "print pages 2 to 5, light toner"   # only the planner
.venv/bin/mcp dev printer_server.py        # click through the MCP tools in a browser
```

## Logs

- `logs/actions.jsonl`: every printer action and reading, one JSON line each.
- `logs/agent.log`: what the planner, executor and checker did.
- `logs/prepared/`: the exact PDFs sent to the printer.
