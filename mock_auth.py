from fastapi import FastAPI, Request
import json, sys

app = FastAPI()

@app.post("/block-user")
async def block_user(req: Request):
    payload = await req.json()
    print("<<< bloqueo recibido >>>", json.dumps(payload), file=sys.stderr)
    return {"ok": True}
