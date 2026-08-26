import sys

from sqlalchemy.orm import Session

from profesor_oak_ai.agent import conversations
from profesor_oak_ai.agent.llm import calculate_cost, evaluate_relevance, run_conversation
from profesor_oak_ai.db.engine import get_engine, get_session


def _answer_and_log(session: Session, query: str) -> tuple[str, str]:
    """Runs a conversation, judges it, tracks cost, and persists it. Returns
    (answer, conversation_id)."""
    result = run_conversation(session, query)
    relevance_result = evaluate_relevance(query, result.answer)
    cost = calculate_cost(
        result.prompt_tokens, result.completion_tokens, result.cached_tokens
    ) + calculate_cost(
        relevance_result.prompt_tokens, relevance_result.completion_tokens, relevance_result.cached_tokens
    )
    conversation_id = conversations.save_conversation(
        session,
        query,
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


def main() -> None:
    session = get_session(get_engine())

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        answer, _ = _answer_and_log(session, query)
        print(answer)
        session.close()
        return

    print("Professor Oak AI -- ask a question about Gen 1 Pokémon (Ctrl+C or 'exit' to quit).")
    try:
        while True:
            query = input("\n> ").strip()
            if not query:
                continue
            if query.lower() in {"exit", "quit"}:
                break

            answer, conversation_id = _answer_and_log(session, query)
            print(answer)

            rating_input = input("Rate this answer (+1/-1, Enter to skip): ").strip()
            if rating_input in {"+1", "1", "-1"}:
                conversations.save_feedback(session, conversation_id, int(rating_input))
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        session.close()


if __name__ == "__main__":
    main()
