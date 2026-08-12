import ollama
from sqlalchemy.orm import Session

from profesor_oak_ai.agent.prompts import SYSTEM_PROMPT
from profesor_oak_ai.agent.retrieval import NO_MATCH_MESSAGE, retrieve_context
from profesor_oak_ai.agent.tools import TOOLS, is_failure

MAX_TOOL_ITERATIONS = 5

NO_INFO_RESPONSE = "My current Pokédex records do not have sufficient information on that topic."

TOOLS_BY_NAME = {tool.__name__: tool for tool in TOOLS}


def ask(session: Session, user_query: str, model: str = "llama3.2") -> str:
    context = retrieve_context(session, user_query)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Pokédex Context:\n{context}\n\nUser Question: {user_query}"},
    ]

    # Tracks whether any real data was actually retrieved this turn (baseline context
    # or a successful tool result). If a tool was tried and every attempt came back
    # empty, the model tends to answer from its own pretrained knowledge instead of
    # admitting it doesn't know -- override that instead of trusting it.
    grounded = context != NO_MATCH_MESSAGE
    tool_attempted = False

    for _ in range(MAX_TOOL_ITERATIONS):
        response = ollama.chat(model=model, messages=messages, tools=TOOLS)
        message = response["message"]
        messages.append(message)

        if not message.get("tool_calls"):
            if tool_attempted and not grounded:
                return NO_INFO_RESPONSE
            return message["content"] or ""

        tool_attempted = True
        for call in message["tool_calls"]:
            name = call["function"]["name"]
            arguments = call["function"]["arguments"]
            tool = TOOLS_BY_NAME.get(name)
            result = str(tool(**arguments)) if tool else f"Unknown tool: {name}"
            if tool and not is_failure(result):
                grounded = True
            print(f"  [tool call] {name}({arguments}) -> {result[:100]}")
            messages.append({"role": "tool", "tool_name": name, "content": result})

    return "I wasn't able to reach a final answer in time. Please try rephrasing your question."
