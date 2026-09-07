from datetime import datetime, timedelta
from html import escape

from sqlalchemy import func
from sqlalchemy.orm import Session

from profesor_oak_ai.db.models import Conversation

NOT_JUDGED_LABEL = "Not judged"
NOT_TRACKED_LABEL = "Not tracked"


def get_summary(session: Session) -> dict:
    total_conversations = session.query(func.count(Conversation.conversation_id)).scalar() or 0
    total_cost = session.query(func.coalesce(func.sum(Conversation.cost), 0.0)).scalar()
    avg_total_tokens = session.query(func.avg(Conversation.total_tokens)).scalar()

    return {
        "total_conversations": total_conversations,
        "total_cost": total_cost or 0.0,
        "avg_total_tokens": avg_total_tokens or 0.0,
    }


def get_relevance_breakdown(session: Session) -> list[tuple[str, int]]:
    label = func.coalesce(Conversation.relevance, NOT_JUDGED_LABEL)
    rows = session.query(label, func.count(Conversation.conversation_id)).group_by(label).all()
    return sorted(rows, key=lambda row: -row[1])


def get_grounding_breakdown(session: Session) -> list[tuple[str, int]]:
    """How answers' subjects got confirmed real: "context" (baseline retrieval),
    "tool" (a name-resolving tool call), or "none" (never grounded -- worth checking
    these for hallucinated/invented subjects slipping past rule 3 in the system
    prompt)."""
    label = func.coalesce(Conversation.grounding_source, NOT_TRACKED_LABEL)
    rows = session.query(label, func.count(Conversation.conversation_id)).group_by(label).all()
    return sorted(rows, key=lambda row: -row[1])


def get_daily_stats(session: Session, days: int = 14) -> list[dict]:
    cutoff = datetime.now() - timedelta(days=days)
    day = func.date(Conversation.created_at)
    rows = (
        session.query(day.label("day"), func.count(Conversation.conversation_id), func.coalesce(func.sum(Conversation.cost), 0.0))
        .filter(Conversation.created_at >= cutoff)
        .group_by("day")
        .order_by("day")
        .all()
    )
    return [{"day": day_str, "count": count, "cost": cost} for day_str, count, cost in rows]


def get_recent_conversations(session: Session, limit: int = 20) -> list[dict]:
    rows = (
        session.query(Conversation)
        .order_by(Conversation.created_at.desc())
        .limit(limit)
        .all()
    )

    return [
        {
            "question": conversation.question,
            "relevance": conversation.relevance or NOT_JUDGED_LABEL,
            "grounding_source": conversation.grounding_source or NOT_TRACKED_LABEL,
            "cost": conversation.cost,
            "created_at": conversation.created_at,
        }
        for conversation in rows
    ]


def _bar_chart(rows: list[tuple[str, int]]) -> str:
    if not rows:
        return "<p>No data yet.</p>"
    max_count = max(count for _, count in rows)
    bars = []
    for label, count in rows:
        pct = round(100 * count / max_count) if max_count else 0
        bars.append(
            f'<div class="bar-row">'
            f'<span class="bar-label">{escape(label)}</span>'
            f'<div class="bar-track"><div class="bar-fill" style="width:{pct}%"></div></div>'
            f'<span class="bar-count">{count}</span>'
            f"</div>"
        )
    return "".join(bars)


def _recent_table(rows: list[dict]) -> str:
    if not rows:
        return "<p>No conversations yet.</p>"
    body = []
    for row in rows:
        cost = f"${row['cost']:.5f}" if row["cost"] is not None else "—"
        body.append(
            "<tr>"
            f"<td>{escape(str(row['created_at']))}</td>"
            f"<td>{escape(row['question'])}</td>"
            f"<td>{escape(row['relevance'])}</td>"
            f"<td>{escape(row['grounding_source'])}</td>"
            f"<td>{cost}</td>"
            "</tr>"
        )
    return (
        "<table><thead><tr><th>Time</th><th>Question</th><th>Relevance</th>"
        "<th>Grounded via</th><th>Cost</th></tr></thead><tbody>"
        + "".join(body)
        + "</tbody></table>"
    )


def render_dashboard_html(session: Session) -> str:
    summary = get_summary(session)
    relevance_rows = get_relevance_breakdown(session)
    grounding_rows = get_grounding_breakdown(session)
    daily_stats = get_daily_stats(session)
    recent = get_recent_conversations(session)

    daily_rows = "".join(
        f"<tr><td>{escape(day['day'])}</td><td>{day['count']}</td><td>${day['cost']:.5f}</td></tr>"
        for day in daily_stats
    )

    return f"""
<style>
  body {{ font-family: -apple-system, sans-serif; margin: 2rem; color: #1a1a1a; }}
  h1 {{ margin-bottom: 0.25rem; }}
  h2 {{ margin-top: 2.5rem; }}
  .cards {{ display: flex; gap: 1rem; flex-wrap: wrap; }}
  .card {{ background: #f4f4f5; border-radius: 8px; padding: 1rem 1.5rem; min-width: 140px; }}
  .card .value {{ font-size: 1.6rem; font-weight: 700; }}
  .card .label {{ font-size: 0.85rem; color: #555; }}
  .bar-row {{ display: flex; align-items: center; gap: 0.75rem; margin: 0.4rem 0; }}
  .bar-label {{ width: 140px; font-size: 0.9rem; }}
  .bar-track {{ flex: 1; background: #e5e5e5; border-radius: 4px; height: 14px; }}
  .bar-fill {{ background: #10a37f; height: 100%; border-radius: 4px; }}
  .bar-count {{ width: 40px; text-align: right; font-size: 0.9rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #e5e5e5; font-size: 0.9rem; }}
  th {{ color: #555; }}
</style>
<h1>Professor Oak AI -- Monitoring</h1>
<p>Live stats from the <code>conversations</code> table.</p>

<div class="cards">
  <div class="card"><div class="value">{summary['total_conversations']}</div><div class="label">Conversations</div></div>
  <div class="card"><div class="value">${summary['total_cost']:.4f}</div><div class="label">Total cost (USD)</div></div>
  <div class="card"><div class="value">{summary['avg_total_tokens']:.0f}</div><div class="label">Avg tokens/conversation</div></div>
</div>

<h2>Relevance breakdown</h2>
{_bar_chart(relevance_rows)}

<h2>Grounding breakdown</h2>
<p>How answers' subjects got confirmed real -- watch the "{NOT_TRACKED_LABEL}" bucket for
pre-migration rows and "none" for possible ungrounded/hallucinated answers.</p>
{_bar_chart(grounding_rows)}

<h2>Daily activity (last 14 days)</h2>
<table><thead><tr><th>Day</th><th>Conversations</th><th>Cost</th></tr></thead><tbody>{daily_rows or '<tr><td colspan="3">No data yet.</td></tr>'}</tbody></table>

<h2>Recent conversations</h2>
{_recent_table(recent)}
"""
