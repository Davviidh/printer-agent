"""Planner: turns a plain-language print request into a print order.

It has no printer tools. It only reads the sentence and fills in an
order form. If something needed is missing (like which file), it says
so in 'questions' instead of guessing.
"""

import logging
import os
import sys
from pathlib import Path
from typing import Literal

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

ROOT = Path(__file__).parent
load_dotenv(ROOT / ".env")

(ROOT / "logs").mkdir(exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    handlers=[logging.StreamHandler(),
              logging.FileHandler(ROOT / "logs" / "agent.log")],
)
log = logging.getLogger("planner")

# Free model on OpenRouter (50 free requests a day). Change it here.
MODEL = os.environ.get("PLANNER_MODEL", "nvidia/nemotron-3-super-120b-a12b:free")


class Order(BaseModel):
    """The print order the planner fills in."""
    file: str | None = Field(None, description='The words the user used to name the document, e.g. "lecture 6" or "alice.pdf". None if not given.')
    page_ranges: str | None = Field(None, pattern=r"^\d+(-\d+)?(,\d+(-\d+)?)*$",
                                    description='Page numbers only, like "2-5" or "1,3,5-7". None means all pages.')
    page_set: Literal["odd", "even"] | None = Field(None, description="Only odd or only even pages.")
    reverse: bool = Field(False, description="Print in reverse order (last page first).")
    # no upper limit here on purpose: the model must copy the user's number,
    # and the printer side refuses more than 5
    copies: int = Field(1, ge=1, description="Exactly the number of copies the user asked for.")
    number_up: Literal[1, 2, 4] = Field(1, description="Pages per sheet.")
    toner_density: int = Field(4, ge=1, le=16, description="1 lightest, 16 darkest, 4 normal.")
    toner_save: bool = Field(False, description="Toner save (draft) mode.")
    questions: list[str] = Field(default_factory=list, description="What is missing or unclear and must be asked before printing.")
    summary: str = Field(description="One plain sentence describing the order for the user.")


PROMPT = """You plan print jobs for a Canon laser printer (black and white, A4, no duplex).
Turn the user's request into an order. Rules:
- The document can be named loosely ("lecture 6", "the alice book", "report.pdf"):
  copy those words into file; a search tool finds the real file later.
  Words like "from my downloads folder" are not part of the name.
  Never invent a name. If no document is named, leave file empty and ask.
- "page 3" means page_ranges "3". page_set is ONLY for the words odd/even.
- "light" or "light toner" means toner_density 2. "very light" means 1. "dark" means 7.
- "save toner" or "draft" means toner_save true.
- Only use what the user said; leave everything else at its default
  (toner_density stays 4 unless the user talks about light or dark).
- "odd pages" / "even pages" go in page_set, never in page_ranges.
- "reverse order", "backwards" or "last page first" means reverse true.
- If the request is unclear or not about printing, put a question in 'questions'.
- Never change what the user asked for. If they ask for something over a limit
  (more than 5 copies), write their number exactly and add a question in
  'questions' saying it is over the limit and asking what they want instead.

Request: {request}"""


def plan(request: str) -> Order:
    log.info(f"request: {request!r}")
    # max_retries=1: each retry costs one of the free requests per day
    llm = ChatOpenAI(model=MODEL, base_url="https://openrouter.ai/api/v1",
                     api_key=os.environ["OPENROUTER_API_KEY"],
                     temperature=0, max_retries=1, timeout=90)
    order = llm.with_structured_output(Order).invoke(PROMPT.format(request=request))
    if order is None:
        log.error("model returned no order")
        raise RuntimeError("planner: model returned no order")
    log.info(f"order: {order.model_dump()}")
    return order


if __name__ == "__main__":
    plan(" ".join(sys.argv[1:]))
