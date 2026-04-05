import os
import json
import asyncio
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from agent.graph import coding_agent
from agent.states import AppState

app = FastAPI(title="AI Coding Agent by Atharva Gai")

# Create static directory if it doesn't exist
os.makedirs("static", exist_ok=True)

# Mount static folder
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def read_root():
    with open("static/index.html", "r") as f:
        return HTMLResponse(content=f.read())

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    
    # Receive the initial task payload
    data = await websocket.receive_text()
    payload = json.loads(data)
    user_prompt = payload.get("prompt", "")
    api_key = payload.get("api_key", "")
    
    if not user_prompt or not api_key:
        await websocket.send_json({"type": "log", "message": "API Key and Prompt are required!"})
        await websocket.close()
        return

    # Initialize State
    state = AppState(user_prompt=user_prompt, api_key=api_key)
    
    await websocket.send_json({"type": "log", "message": f"Starting run for prompt: {user_prompt}"})
    await websocket.send_json({"type": "graph", "currentNode": "planner"})
    
    try:
        # Stream events from LangGraph
        async for s in coding_agent.astream(state):
            # s is a dict of {node_name: new_state}
            for node, current_state in s.items():
                await websocket.send_json({"type": "graph", "currentNode": node})
                
                if current_state:
                    # fetch latest log
                    if current_state.logs:
                        latest_log = current_state.logs[-1]
                        await websocket.send_json({"type": "log", "message": latest_log})
            
            # Let other tasks run
            await asyncio.sleep(0.1)

        await websocket.send_json({"type": "graph", "currentNode": "END"})
        await websocket.send_json({"type": "log", "message": "Build Complete! Check generated_project directory."})
    except Exception as e:
        await websocket.send_json({"type": "log", "message": f"Error: {str(e)}"})
    finally:
        await websocket.close()

if __name__ == "__main__":
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
