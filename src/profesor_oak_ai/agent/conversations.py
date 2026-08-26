import uuid

from sqlalchemy.orm import Session

from profesor_oak_ai.agent.llm import calculate_cost, evaluate_relevance, run_conversation
from profesor_oak_ai.db.models import Conversation, Feedback


def save_conversation(
    session: Session,
    question: str,
    answer: str,
    *,
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
) -> str:
    conversation_id = str(uuid.uuid4())
    session.add(
        Conversation(
            conversation_id=conversation_id,
            question=question,
            answer=answer,
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
        )
    )
    session.commit()
    return conversation_id


def save_feedback(session: Session, conversation_id: str, rating: int) -> None:
    session.add(Feedback(conversation_id=conversation_id, rating=rating))
    session.commit()


def ask_and_log(session: Session, question: str) -> tuple[str, str]:
    """Runs a conversation, judges relevance, tracks cost, and persists it.
    Returns (answer, conversation_id). Shared by the CLI and the HTTP API."""
    result = run_conversation(session, question)
    relevance_result = evaluate_relevance(question, result.answer)
    cost = calculate_cost(
        result.prompt_tokens, result.completion_tokens, result.cached_tokens
    ) + calculate_cost(
        relevance_result.prompt_tokens, relevance_result.completion_tokens, relevance_result.cached_tokens
    )
    conversation_id = save_conversation(
        session,
        question,
        result.answer,
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
    )
    return result.answer, conversation_id
