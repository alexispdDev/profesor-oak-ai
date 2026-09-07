from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from profesor_oak_ai.agent import conversations, dashboard
from profesor_oak_ai.db.engine import get_engine, get_session

engine = get_engine()


def get_db():
    session = get_session(engine)
    try:
        yield session
    finally:
        session.close()


app = FastAPI(title="Professor Oak AI")


class QuestionRequest(BaseModel):
    question: str
    # Omit to start a new conversation thread. Pass the thread_id a previous
    # /question response returned to continue that thread as a follow-up.
    thread_id: str | None = None


class QuestionResponse(BaseModel):
    conversation_id: str
    thread_id: str
    answer: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/question", response_model=QuestionResponse)
def ask_question(request: QuestionRequest, session: Session = Depends(get_db)):
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    answer, conversation_id, thread_id = conversations.ask_and_log(
        session, request.question, thread_id=request.thread_id
    )
    return QuestionResponse(conversation_id=conversation_id, thread_id=thread_id, answer=answer)


@app.get("/dashboard", response_class=HTMLResponse)
def get_dashboard(session: Session = Depends(get_db)):
    return dashboard.render_dashboard_html(session)


def main() -> None:
    import uvicorn

    uvicorn.run("profesor_oak_ai.agent.api:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
