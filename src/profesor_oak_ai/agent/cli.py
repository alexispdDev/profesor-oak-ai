import argparse

from profesor_oak_ai.agent import conversations
from profesor_oak_ai.db.engine import get_engine, get_session


def main() -> None:
    parser = argparse.ArgumentParser(prog="profesor-oak-ai")
    parser.add_argument(
        "--debug", action="store_true", help="show tool calls and their results as they happen"
    )
    parser.add_argument("query", nargs="*", help="question to ask; omit to start interactive mode")
    args = parser.parse_args()

    session = get_session(get_engine())

    if args.query:
        query = " ".join(args.query)
        answer, _, _ = conversations.ask_and_log(session, query, debug=args.debug)
        print(answer)
        session.close()
        return

    print("Professor Oak AI -- ask a question about Gen 1 Pokémon (Ctrl+C or 'exit' to quit).")
    # One REPL session is one continuous conversation thread -- thread_id starts
    # unset (a fresh thread) and is carried forward from each call's return value,
    # so a follow-up question has the prior turns to make sense of.
    thread_id = None
    try:
        while True:
            query = input("\n> ").strip()
            if not query:
                continue
            if query.lower() in {"exit", "quit"}:
                break

            answer, _, thread_id = conversations.ask_and_log(
                session, query, thread_id=thread_id, debug=args.debug
            )
            print(answer)
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        session.close()


if __name__ == "__main__":
    main()
