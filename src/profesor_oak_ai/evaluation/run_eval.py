import csv
import json
from pathlib import Path

from sqlalchemy.orm import Session

from profesor_oak_ai.agent.llm import evaluate_relevance, run_conversation
from profesor_oak_ai.db.engine import get_engine, get_session

GROUND_TRUTH_PATH = Path("evaluation/ground_truth.jsonl")
RESULTS_PATH = Path("evaluation/results.csv")


def load_ground_truth() -> list[dict]:
    rows = []
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        for line in f:
            rows.append(json.loads(line))
    return rows


def write_results_csv(results: list[dict]) -> None:
    with open(RESULTS_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "question",
                "expected_tool",
                "tools_called",
                "tool_match",
                "relevance",
                "relevance_explanation",
            ],
        )
        writer.writeheader()
        writer.writerows(results)


def print_summary(results: list[dict]) -> None:
    retrieval_rows = [r for r in results if r["tool_match"] is not None]
    retrieval_hits = sum(1 for r in retrieval_rows if r["tool_match"])

    relevance_counts: dict[str, int] = {}
    for r in results:
        relevance_counts[r["relevance"]] = relevance_counts.get(r["relevance"], 0) + 1

    print("\n=== Summary ===")
    if retrieval_rows:
        print(
            f"Retrieval accuracy: {retrieval_hits}/{len(retrieval_rows)} "
            f"({100 * retrieval_hits / len(retrieval_rows):.0f}%)"
        )
    print("Relevance breakdown:")
    for relevance, count in sorted(relevance_counts.items(), key=lambda kv: -kv[1]):
        print(f"  {relevance}: {count}/{len(results)} ({100 * count / len(results):.0f}%)")


def run_eval(session: Session) -> None:
    rows = load_ground_truth()
    results = []

    for i, row in enumerate(rows, 1):
        result = run_conversation(session, row["question"])

        expected_tool = row["expected_tool"]
        tool_match = expected_tool in result.tools_called if expected_tool else None

        relevance_result = evaluate_relevance(row["question"], result.answer)

        results.append(
            {
                "question": row["question"],
                "expected_tool": expected_tool or "",
                "tools_called": ";".join(result.tools_called),
                "tool_match": tool_match,
                "relevance": relevance_result.relevance,
                "relevance_explanation": relevance_result.explanation,
            }
        )
        print(
            f"[{i}/{len(rows)}] {row['question'][:50]!r} "
            f"tool_match={tool_match} relevance={relevance_result.relevance}"
        )

    write_results_csv(results)
    print_summary(results)


def main() -> None:
    session = get_session(get_engine())
    try:
        run_eval(session)
    finally:
        session.close()


if __name__ == "__main__":
    main()
