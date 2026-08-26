import sys

from profesor_oak_ai.agent import conversations
from profesor_oak_ai.db.engine import get_engine, get_session


def main() -> None:
    session = get_session(get_engine())

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        answer, _ = conversations.ask_and_log(session, query)
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

            answer, conversation_id = conversations.ask_and_log(session, query)
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
