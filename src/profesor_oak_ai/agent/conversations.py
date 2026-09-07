import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from profesor_oak_ai.agent.llm import calculate_cost, evaluate_relevance, run_conversation
from profesor_oak_ai.db.models import Conversation


def save_conversation(
    session: Session,
    question: str,
    answer: str,
    *,
    thread_id: str,
    conversation_id: str | None = None,
    relevance: str | None = None,
    relevance_explanation: str | None = None,
    prompt_tokens: int | None = None,
    completion_tokens: int | None = None,
    total_tokens: int | None = None,
    cached_tokens: int | None = None,
    eval_prompt_tokens: int | None = None,
    eval_completion_tokens: int | None = None,
    eval_total_tokens: int | None = None,
    cost: float | None = None,
    grounding_source: str | None = None,
) -> str:
    conversation_id = conversation_id or str(uuid.uuid4())
    session.add(
        Conversation(
            conversation_id=conversation_id,
            question=question,
            answer=answer,
            thread_id=thread_id,
            relevance=relevance,
            relevance_explanation=relevance_explanation,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            cached_tokens=cached_tokens,
            eval_prompt_tokens=eval_prompt_tokens,
            eval_completion_tokens=eval_completion_tokens,
            eval_total_tokens=eval_total_tokens,
            cost=cost,
            grounding_source=grounding_source,
        )
    )
    session.commit()
    return conversation_id


def load_thread_history(session: Session, thread_id: str) -> list[dict]:
    """Every prior turn of thread_id, oldest first, flattened into plain
    {"role": "user"|"assistant", "content": str} pairs -- see run_conversation's
    history parameter for why this is text-only, not the raw tool-call trace."""
    rows = session.execute(
        select(Conversation.question, Conversation.answer)
        .where(Conversation.thread_id == thread_id)
        .order_by(Conversation.created_at)
    ).all()
    history: list[dict] = []
    for question, answer in rows:
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": answer})
    return history


def ask_and_log(
    session: Session, question: str, *, thread_id: str | None = None, debug: bool = False
) -> tuple[str, str, str]:
    """Runs a conversation, judges relevance, tracks cost, and persists it.
    Returns (answer, conversation_id, thread_id). Shared by the CLI and the HTTP API.

    thread_id: omit (the default) to start a NEW conversation thread -- a fresh id is
    generated and there's no prior history. Pass a thread_id previously returned by
    this function to CONTINUE that thread: prior turns are loaded and given to
    run_conversation as history, so e.g. rule 17's team-building judgment-call
    questions can be answered in a follow-up call and actually make sense to the
    model. The returned thread_id is always the one to pass back for the next turn,
    whether this call started a new thread or continued an existing one."""
    history = load_thread_history(session, thread_id) if thread_id is not None else None
    result = run_conversation(session, question, debug=debug, history=history)
    relevance_result = evaluate_relevance(question, result.answer)
    cost = calculate_cost(
        result.prompt_tokens, result.completion_tokens, result.cached_tokens
    ) + calculate_cost(
        relevance_result.prompt_tokens, relevance_result.completion_tokens, relevance_result.cached_tokens
    )
    # A brand-new thread's first row is its own root (thread_id == conversation_id),
    # so the id is generated up front rather than inside save_conversation, letting
    # both columns be set correctly in the single insert below.
    is_new_thread = thread_id is None
    conversation_id = str(uuid.uuid4())
    resolved_thread_id = thread_id if not is_new_thread else conversation_id
    save_conversation(
        session,
        question,
        result.answer,
        thread_id=resolved_thread_id,
        conversation_id=conversation_id,
        relevance=relevance_result.relevance,
        relevance_explanation=relevance_result.explanation,
        prompt_tokens=result.prompt_tokens,
        completion_tokens=result.completion_tokens,
        total_tokens=result.total_tokens,
        cached_tokens=result.cached_tokens,
        eval_prompt_tokens=relevance_result.prompt_tokens,
        eval_completion_tokens=relevance_result.completion_tokens,
        eval_total_tokens=relevance_result.total_tokens,
        cost=cost,
        grounding_source=result.grounding_source,
    )
    return result.answer, conversation_id, resolved_thread_id
