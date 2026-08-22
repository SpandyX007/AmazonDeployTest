import ollama
from fastapi import FastAPI
from pydantic import BaseModel

MODEL = 'qwen:1.8b'

app = FastAPI()


class ChatRequest(BaseModel):
    content: str


@app.get('/')
def index():
    return {'message': 'API is live', 'model': MODEL}


# Sync def, not async def: ollama.chat() blocks, so FastAPI runs this in a
# threadpool instead of stalling the event loop.
@app.post('/chat')
def chat(req: ChatRequest):
    response = ollama.chat(model=MODEL, messages=[
        {
            'role': 'user',
            'content': req.content,
        },
    ])
    return {'response': response['message']['content']}
