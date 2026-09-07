import json
import os
from dataclasses import dataclass

from dotenv import load_dotenv
from ollama._utils import convert_function_to_tool
from openai import OpenAI
from sqlalchemy.orm import Session

from profesor_oak_ai.agent.prompts import SYSTEM_PROMPT
from profesor_oak_ai.agent.retrieval import retrieve_context
from profesor_oak_ai.agent.tools import NON_GROUNDING_TOOLS, TOOLS, is_failure

# Loads OPENAI_API_KEY (and optionally OPENAI_MODEL) from a .env file if present, without
# overriding any already-exported real environment variable.
load_dotenv()

MAX_TOOL_ITERATIONS = 5

# Model names/pricing shift fast -- kept as an overridable constant/env var rather than
# hardcoded deep in the request logic.
MODEL = os.environ.get("OPENAI_MODEL", "gpt-5.4-mini")

NO_INFO_RESPONSE = "My current Pokédex records do not have sufficient information on that topic."

# Real pricing for the configured model, provided by the user (USD per 1M tokens) --
# not fabricated. Update these if OPENAI_MODEL changes to a different model's pricing.
PRICE_PER_MILLION_INPUT_TOKENS = 0.75
PRICE_PER_MILLION_CACHED_INPUT_TOKENS = 0.075
PRICE_PER_MILLION_OUTPUT_TOKENS = 4.50


def calculate_cost(prompt_tokens: int, completion_tokens: int, cached_tokens: int = 0) -> float:
    billable_prompt_tokens = prompt_tokens - cached_tokens
    return (
        billable_prompt_tokens * PRICE_PER_MILLION_INPUT_TOKENS
        + cached_tokens * PRICE_PER_MILLION_CACHED_INPUT_TOKENS
        + completion_tokens * PRICE_PER_MILLION_OUTPUT_TOKENS
    ) / 1_000_000


def _usage_totals(response) -> tuple[int, int, int, int]:
    """Extracts (prompt_tokens, completion_tokens, total_tokens, cached_tokens) from an
    OpenAI response, reading cached_tokens defensively since not every SDK/model
    combination reports prompt_tokens_details."""
    usage = response.usage
    cached_tokens = getattr(getattr(usage, "prompt_tokens_details", None), "cached_tokens", 0) or 0
    return usage.prompt_tokens, usage.completion_tokens, usage.total_tokens, cached_tokens


@dataclass
class ConversationResult:
    answer: str
    tools_called: list[str]
    # How the answer's subject was confirmed real, for debugging/audit purposes:
    # "tool" (a name-resolving tool call confirmed it) or "none" (never grounded -- the
    # answer is either the "insufficient information" fallback or, if the model ignored
    # rule 3, ungrounded). "context" can still appear on rows persisted before baseline
    # retrieval stopped pre-fetching species data; the current code never produces it.
    grounding_source: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int


@dataclass
class RelevanceResult:
    relevance: str
    explanation: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cached_tokens: int

TOOLS_BY_NAME = {tool.__name__: tool for tool in TOOLS}

# OpenAI's tools= param needs explicit JSON-schema tool definitions -- it doesn't
# auto-convert raw Python functions the way Ollama's client does. Reusing Ollama's own
# docstring parser (kept as a dependency solely for this) instead of writing a new
# one: it already produces output in OpenAI's {"type": "function", "function": {...}}
# shape. Relies on an underscore-prefixed (unofficial) ollama API, acceptable given the
# exact version pin.
OPENAI_TOOLS = [convert_function_to_tool(tool).model_dump(exclude_none=True) for tool in TOOLS]


def run_conversation(
    session: Session,
    user_query: str,
    model: str = MODEL,
    *,
    debug: bool = False,
    history: list[dict] | None = None,
) -> ConversationResult:
    """Runs the tool-calling loop and returns a ConversationResult (answer,
    tool_names_called_in_order, and token usage) -- the tool names are exposed for the
    evaluation harness (profesor_oak_ai.evaluation), which needs to check whether the
    expected tool was actually invoked. ask() below is the plain-answer wrapper every
    other caller (CLI, future API) should keep using. Pass debug=True to print each
    step's tool calls and results as they happen.

    history, if given, is prior turns as plain {"role": "user"|"assistant", "content":
    str} pairs (see conversations.load_thread_history), inserted between the system
    prompt and the current question -- NOT the raw tool_calls/tool messages from those
    turns. The assistant's own prior answer already carries the essential grounded
    facts in prose, so this is enough for a follow-up question to make sense of,
    without the growing token cost of replaying every prior tool
    call's full output on every subsequent turn. Omit (the default) for a single-turn
    question with no prior context -- every existing caller of this function relies on
    that default and needs no changes."""
    tools_called: list[str] = []
    prompt_tokens = completion_tokens = total_tokens = cached_tokens = 0

    if not os.environ.get("OPENAI_API_KEY"):
        return ConversationResult(
            "OPENAI_API_KEY environment variable is not set -- cannot reach the OpenAI API.",
            tools_called,
            "none",
            prompt_tokens,
            completion_tokens,
            total_tokens,
            cached_tokens,
        )

    client = OpenAI()

    context = retrieve_context(session, user_query)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        *(history or []),
        {"role": "user", "content": f"Pokédex Context:\n{context}\n\nUser Question: {user_query}"},
    ]

    # Tracks whether the question was ever answered from real data. retrieve_context()
    # deliberately never pre-fetches species data, so this can only become True via a
    # successful call to a tool not in NON_GROUNDING_TOOLS -- a bare type-name mention
    # or a get_type_effectiveness call doesn't count, since neither proves the thing the
    # user asked about exists (e.g. "Bo Jackson" isn't a Pokémon even though "Ground" is
    # a real type). If a tool was tried and nothing ever grounded the answer, the model
    # tends to answer from its own pretrained knowledge instead of admitting it doesn't
    # know -- override that instead of trusting it.
    grounded = False
    grounding_source = "none"
    tool_attempted = False

    for step in range(1, MAX_TOOL_ITERATIONS + 1):
        response = client.chat.completions.create(model=model, messages=messages, tools=OPENAI_TOOLS)
        step_prompt, step_completion, step_total, step_cached = _usage_totals(response)
        prompt_tokens += step_prompt
        completion_tokens += step_completion
        total_tokens += step_total
        cached_tokens += step_cached
        message = response.choices[0].message

        if not message.tool_calls:
            messages.append({"role": "assistant", "content": message.content})
            answer = NO_INFO_RESPONSE if (tool_attempted and not grounded) else (message.content or "")
            return ConversationResult(
                answer,
                tools_called,
                grounding_source,
                prompt_tokens,
                completion_tokens,
                total_tokens,
                cached_tokens,
            )

        tool_attempted = True
        messages.append(
            {
                "role": "assistant",
                "content": message.content,
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": call.function.name, "arguments": call.function.arguments},
                    }
                    for call in message.tool_calls
                ],
            }
        )

        if debug:
            print(f"[step {step}] model requested {len(message.tool_calls)} tool call(s):")
        for call in message.tool_calls:
            name = call.function.name
            tools_called.append(name)
            try:
                arguments = json.loads(call.function.arguments)
            except json.JSONDecodeError:
                # The model doesn't always generate valid JSON for arguments -- treat as
                # a failed call rather than crashing the whole turn.
                arguments = {}

            tool = TOOLS_BY_NAME.get(name)
            result = str(tool(**arguments)) if tool else f"Unknown tool: {name}"
            if tool and name not in NON_GROUNDING_TOOLS and not is_failure(result):
                if not grounded:
                    grounding_source = "tool"
                grounded = True
            if debug:
                print(f"  -> {name}({arguments})")
                print(f"  <- {result}")
            messages.append({"role": "tool", "tool_call_id": call.id, "content": result})

    return ConversationResult(
        "I wasn't able to reach a final answer in time. Please try rephrasing your question.",
        tools_called,
        grounding_source,
        prompt_tokens,
        completion_tokens,
        total_tokens,
        cached_tokens,
    )


def ask(session: Session, user_query: str, model: str = MODEL) -> str:
    return run_conversation(session, user_query, model).answer


EVALUATION_PROMPT_TEMPLATE = """
You are an expert evaluator for a RAG system.
Your task is to analyze the relevance of the generated answer to the given question.
Based on the relevance of the generated answer, you will classify it
as "NON_RELEVANT", "PARTLY_RELEVANT", or "RELEVANT".

Here is the data for evaluation:

Question: {question}
Generated Answer: {answer}

Please analyze the content and context of the generated answer in relation to the question
and provide your evaluation in parsable JSON without using code blocks:

{{
  "Relevance": "NON_RELEVANT" | "PARTLY_RELEVANT" | "RELEVANT",
  "Explanation": "[Provide a brief explanation for your evaluation]"
}}
""".strip()


def evaluate_relevance(question: str, answer: str, model: str = MODEL) -> RelevanceResult:
    client = OpenAI()
    prompt = EVALUATION_PROMPT_TEMPLATE.format(question=question, answer=answer)
    response = client.chat.completions.create(model=model, messages=[{"role": "user", "content": prompt}])
    prompt_tokens, completion_tokens, total_tokens, cached_tokens = _usage_totals(response)
    raw = response.choices[0].message.content or ""

    try:
        parsed = json.loads(raw)
        relevance, explanation = parsed.get("Relevance", "UNKNOWN"), parsed.get("Explanation", "")
    except json.JSONDecodeError:
        relevance, explanation = "UNKNOWN", "Failed to parse evaluation"

    return RelevanceResult(relevance, explanation, prompt_tokens, completion_tokens, total_tokens, cached_tokens)
