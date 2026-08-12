import sys

from profesor_oak_ai.agent.llm import ask
from profesor_oak_ai.db.engine import get_engine, get_session


def main() -> None:
    session = get_session(get_engine())

    if len(sys.argv) > 1:
        query = " ".join(sys.argv[1:])
        print(ask(session, query))
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
            print(ask(session, query))
    except (KeyboardInterrupt, EOFError):
        print()
    finally:
        session.close()


if __name__ == "__main__":
    main()
