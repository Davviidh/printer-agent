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
| `finder.py` | Finds the PDF to print, only inside `~/Downloads`. |
| `doc_finder.py` | Searches arXiv when the file is not in Downloads, and downloads the paper you pick. |
| `evals/` | Test requests with expected answers, and a runner that scores the agent on the simulator. |
| `LEARNINGS.md` | What we found out while building (read this, some of it is surprising). |
| `PROGRESS.md` | What is done and what is next. |

## Requirements

- Python 3.11 or newer.
- A free [OpenRouter](https://openrouter.ai) API key (the free models need no money).

### Which computers it works on

| Part | macOS | Linux | Windows |
|---|---|---|---|
| Simulator, agent, evals, arXiv | yes (tested) | should work, not tested | should work, not tested |
| Real printer | yes (tested) | not yet | no |

The real-printer mode is macOS only for now, and it was built for one printer:
- it checks that the printer is switched on with `ioreg`, a macOS-only command
  (on Linux this would be `lsusb`, a small change in `connector.py`)
- it prints through CUPS (`lp`, `lpstat`, `cancel`), which macOS and Linux have and Windows does not
- the queue name (`Canon_LBP6020`) and the toner settings (`CNTonerDensity`, `CNDraftMode`, ...)
  are specific to the Canon i-SENSYS LBP6020B driver. Another printer needs its own queue name
  (`lpstat -p`) and options (`lpoptions -p <queue> -l`) in `connector.py`.

The macOS commands in this README (`.venv/bin/python`, `open -e`) work the same on Linux.
On Windows use `.venv\Scripts\python` instead.

## Download and install

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

The agent looks for files in `~/Downloads`. `FINDER_DIR=test_docs` makes it look in the
project's test documents instead, so these examples work right away.

```
FINDER_DIR=test_docs .venv/bin/python graph.py "print only odd pages of four_pages.pdf, save toner"
```

You will see the print order:

```
PRINT ORDER - please check
File:      .../test_docs/four_pages.pdf (4 pages)
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
FINDER_DIR=test_docs SIM_FAULT=fail  .venv/bin/python graph.py "print page 1 of four_pages.pdf"   # job fails
FINDER_DIR=test_docs SIM_FAULT=stuck .venv/bin/python graph.py "print page 1 of four_pages.pdf"   # stuck, wait about 60 s
FINDER_DIR=test_docs SIM_POWERED=0 SIM_ON_AFTER=20 .venv/bin/python graph.py "print page 1 of four_pages.pdf"   # off, comes on after 20 s
```

### 2. The real printer

Switch the printer on, then:

```
FINDER_DIR=test_docs PRINTER_BACKEND=real .venv/bin/python graph.py "print page 1 of four_pages.pdf"
```

Nothing prints until you type `yes`. Start with one page.

### Things you can ask for

- pages: "pages 2 to 5", "pages 1, 3 and 7"
- odd or even pages: "only odd pages"
- reverse order: "in reverse order", "last page first"
- copies (1 to 5): "2 copies"
- pages per sheet (1, 2 or 4): "two pages per sheet"
- toner: "light toner", "very light", "dark", "save toner"

Only PDF files are supported, and the agent only looks for them in your `~/Downloads` folder (and its subfolders). Small typos in the name are fine. If several files match, it asks you to name one exactly. If you do not name a file, it asks for one.

### Papers from arXiv

If the document is not in your Downloads, the agent searches [arXiv](https://arxiv.org)
(free research papers) and asks before downloading anything:

```
.venv/bin/python graph.py "print page 1 of the attention is all you need paper"
```

```
'the attention is all you need paper' is not in your Downloads. Found on arXiv:
  1) Attention Is All You Need - Ashish Vaswani, Noam Shazeer et al. (2017)
  2) Not All Attention Is All You Need - Hongqiu Wu, Hai Zhao et al. (2021)
  3) Tensor Product Attention Is All You Need - Yifan Zhang, Yifeng Liu et al. (2025)
Download one into Downloads? Type its number, or no
```

Type a number to download that paper into `~/Downloads`. Then you get the normal print
order for your original request (here: page 1) and must say `yes` again before anything
prints. Type `no` to stop. You can also give the arXiv number, like "print 1706.03762".

Safety rules:
- only arxiv.org is ever contacted (every redirect is checked too)
- nothing is downloaded without your choice, nothing is printed without your `yes`
- the download must be a real PDF and under 30 MB

### Settings

Settings can go in `.env` (once) or in front of a single command (that run only, and it
wins over `.env`). Write them without spaces around `=`.

| Setting | Default | Meaning |
|---|---|---|
| `PRINTER_BACKEND` | `sim` | `real` prints on the Canon, `sim` uses the simulated printer |
| `FINDER_DIR` | `~/Downloads` | where to look for documents (the examples use `test_docs`) |
| `PLANNER_MODEL` | `nvidia/nemotron-3-super-120b-a12b:free` | the OpenRouter model of the planner |
| `SIM_FAULT` | none | simulator only: `fail` or `stuck` |
| `SIM_POWERED`, `SIM_ON_AFTER` | `1`, none | simulator only: start switched off, switch on after N seconds |

For example, to always print on the real printer, add `PRINTER_BACKEND=real` to `.env`.

### Run the evals

```
.venv/bin/python evals/run_evals.py           # all test requests
.venv/bin/python evals/run_evals.py typo-1    # one of them
```

Each request in `evals/cases.json` runs through the whole agent on the simulator, every
question is answered "yes" automatically, and the result is compared with the expected
answer. Results are saved in `evals/results_*.json`. Each request uses one call to the
free model, so mind the limit of about 50 a day.

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
