import uuid

from sqlalchemy.orm import Session

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
