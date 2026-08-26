from typing import Literal

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from profesor_oak_ai.agent import conversations
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


class QuestionResponse(BaseModel):
    conversation_id: str
    answer: str


class FeedbackRequest(BaseModel):
    conversation_id: str
    feedback: Literal[-1, 1]


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/question", response_model=QuestionResponse)
def ask_question(request: QuestionRequest, session: Session = Depends(get_db)):
    if not request.question.strip():
        raise HTTPException(status_code=422, detail="question must not be empty")
    answer, conversation_id = conversations.ask_and_log(session, request.question)
    return QuestionResponse(conversation_id=conversation_id, answer=answer)


@app.post("/feedback", status_code=204)
def submit_feedback(request: FeedbackRequest, session: Session = Depends(get_db)):
    conversations.save_feedback(session, request.conversation_id, request.feedback)


def main() -> None:
    import uvicorn

    uvicorn.run("profesor_oak_ai.agent.api:app", host="0.0.0.0", port=8000)


if __name__ == "__main__":
    main()
