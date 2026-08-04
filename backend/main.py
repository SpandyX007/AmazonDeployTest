from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from backend.providers.groq import GPTresponse

app = FastAPI(title="LLM API Service")


class Query(BaseModel):
    query: str


class Answer(BaseModel):
    response: str


@app.get('/')
async def index():
    return {"status": "The service is live"}


@app.post('/response', response_model=Answer)
def get_response(payload: Query):
    try:
        answer = GPTresponse(payload.query)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LLM request failed: {exc}")
    return Answer(response=answer)
