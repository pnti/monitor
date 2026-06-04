let currentTaskId = null; 
let pyodideInstance = null;
let isAlreadyRejected = false; 

async function initPyodide() {
    const outputBox = document.getElementById('output');
    try {
        pyodideInstance = await loadPyodide();
        outputBox.innerText = "Środowisko Python gotowe.";
    } catch (err) {
        outputBox.innerText = "Błąd silnika: " + err;
    }
}

async function runPythonCode() {
    if (!pyodideInstance) { alert("Ładowanie Pythona..."); return; }
    const code = document.getElementById('studentCode').value;
    const outputBox = document.getElementById('output');
    outputBox.innerText = "Uruchamianie...\n";
    try {
        pyodideInstance.runPython(`import sys, io; sys.stdout = io.StringIO()`);
        await pyodideInstance.runPythonAsync(code);
        const stdout = pyodideInstance.runPython("sys.stdout.getvalue()");
        outputBox.innerText = stdout ? stdout : "Program zakończył działanie poprawnie.";
        outputBox.style.color = "#fff";
    } catch (err) {
        outputBox.innerText = err.message;
        outputBox.style.color = "#ff6b6b";
    }
}

function fetchStatus() {
    fetch('/student_status')
    .then(res => res.json())
    .then(data => {
        const mainBtn = document.getElementById('mainBtn');
        const helpBtn = document.getElementById('helpBtn');
        const runBtn = document.getElementById('runBtn');
        const studentCode = document.getElementById('studentCode');
        const taskContainer = document.querySelector('.task-container');
        const bannerContainer = document.getElementById('rejectionBannerContainer');
        const workspace = document.getElementById('workspace');

        // 1. Obsługa pełnego zakończenia lekcji (brak kolejnych zadań w tagu)
        if (data.task_id === "finished") {
            currentTaskId = "finished";
            taskContainer.innerText = data.task_text;
            taskContainer.style.background = "#d4edda"; 
            taskContainer.style.color = "#155724";
            taskContainer.style.borderLeftColor = "#28a745";
            if (workspace) workspace.classList.add('hidden');
            if (bannerContainer) bannerContainer.innerHTML = "";
            return;
        }

        // 2. Obsługa blokady ekranu
        if (data.task_id === "lock") {
            currentTaskId = "lock";
            taskContainer.innerText = data.task_text;
            taskContainer.style.background = "#fff";
            taskContainer.style.color = "#333";
            taskContainer.style.borderLeftColor = "#dc3545";
            if (workspace) workspace.classList.add('hidden');
            if (bannerContainer) bannerContainer.innerHTML = "";
            return;
        }

        // 3. Detekcja zmiany zadania
        if (data.task_id !== currentTaskId) {
            currentTaskId = data.task_id;
            document.body.setAttribute('data-task-id', data.task_id);
            
            taskContainer.innerText = data.task_text;
            taskContainer.style.background = "#fff"; // Poprawiono niefortunny zapis
            taskContainer.style.color = "#333";
            taskContainer.style.borderLeftColor = "#007bff";
            
            if (workspace) {
                workspace.classList.remove('hidden');
            }
            
            studentCode.value = ""; 
            studentCode.disabled = false;
            mainBtn.disabled = !data.submissions_allowed;
            runBtn.disabled = false;
            mainBtn.innerText = data.submissions_allowed ? "WYŚLIJ DO OCENY" : "PRZYJMOWANIE ZABLOKOWANE";
            
            if (helpBtn) {
                helpBtn.classList.remove('hidden');
                helpBtn.innerText = "POMOC";
                helpBtn.classList.remove('active');
            }
            bannerContainer.innerHTML = "";
            isAlreadyRejected = false; 
            return;
        }

        // 4. Stały monitoring stanu obecnego zadania
        if (data.progress === true) {
            studentCode.disabled = true;
            mainBtn.disabled = true;
            runBtn.disabled = true;
            mainBtn.innerText = "OCZEKIWANIE NA OCENĘ";
            if (helpBtn) helpBtn.classList.add('hidden');
            bannerContainer.innerHTML = "";
            isAlreadyRejected = false; 
        } 
        else if (data.progress === false && data.rejection_msg !== "") {
            studentCode.disabled = false;
            runBtn.disabled = false;
            mainBtn.disabled = !data.submissions_allowed;
            mainBtn.innerText = data.submissions_allowed ? "WYŚLIJ POPRAWIONY KOD" : "PRZYJMOWANIE ZABLOKOWANE";
            if (helpBtn) helpBtn.classList.remove('hidden');
            
            bannerContainer.innerHTML = `<div class="rejection-banner"><strong>Do poprawy:</strong><br>${data.rejection_msg}</div>`;

            if (!isAlreadyRejected) {
                if (data.code && studentCode.value !== data.code) {
                    studentCode.value = data.code;
                }
                isAlreadyRejected = true; 
            }
        }
    });
}

function askHelp() {
    fetch('/need_help', { method: 'POST' }).then(res => res.json()).then(data => {
        const btn = document.getElementById('helpBtn');
        if (!btn) return;
        btn.innerText = data.is_helping ? "CZEKAJ" : "POMOC";
        data.is_helping ? btn.classList.add('active') : btn.classList.remove('active');
    });
}

function sendDone() {
    const codeValue = document.getElementById('studentCode').value.trim();
    if(!codeValue) { alert("Pole nie może być puste!"); return; }

    if(confirm("Wysłać kod do oceny?")) {
        const body = new URLSearchParams();
        body.append('code', codeValue);
        fetch('/done', { method: 'POST', body: body }).then(res => {
            if (res.status === 403) alert("Przyjmowanie zablokowane!");
            fetchStatus();
        });
    }
}

initPyodide();
setInterval(fetchStatus, 1000);
