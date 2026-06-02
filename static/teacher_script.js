let selectedStudentIp = null;
let globalStateCache = {};
let pyodideTeacherInstance = null;
let isCodeEdited = false;

// Pobranie łącznej liczby zadań osadzonej w atrybucie kontenera głównego
const totalTasks = document.getElementById('dashboardContainer').getAttribute('data-total-tasks');

// Inicjalizacja Pyodide w przeglądarce nauczyciela
async function initTeacherPyodide() {
    try {
        pyodideTeacherInstance = await loadPyodide();
        document.getElementById('teacherTerminal').innerText = "Środowisko testowe Python zainicjalizowane poprawnie.";
    } catch (err) {
        document.getElementById('teacherTerminal').innerText = "Błąd inicjalizacji silnika: " + err;
    }
}

// Wykrycie zmian w polu edytora – blokada automatycznego odświeżania tekstu
document.getElementById('globalCodePreview').addEventListener('input', () => {
    isCodeEdited = true;
});

// Uruchamianie kodu w lokalnym sandboksie Pyodide
async function runStudentCode() {
    if (!pyodideTeacherInstance) {
        alert("Silnik Pythona wciąż się ładuje...");
        return;
    }

    const code = document.getElementById('globalCodePreview').value;
    const terminal = document.getElementById('teacherTerminal');
    
    if (code.startsWith("# Uczeń nie przesłał") || code.startsWith("# Brak kodu") || code.trim() === "") {
        alert("Brak kodu do uruchomienia.");
        return;
    }

    terminal.innerText = "Uruchamianie kodu...\n";
    terminal.style.color = "#00ff00";

    try {
        pyodideTeacherInstance.runPython(`
            import sys
            import io
            sys.stdout = io.StringIO()
        `);

        await pyodideTeacherInstance.runPythonAsync(code);

        const stdout = pyodideTeacherInstance.runPython("sys.stdout.getvalue()");
        terminal.innerText = stdout ? stdout : "Program zakończył działanie poprawnie (brak danych wyjściowych).";
        terminal.style.color = "#ffffff";
    } catch (err) {
        terminal.innerText = err.message;
        terminal.style.color = "#ff6b6b";
    }
}

function selectStudent(ip) {
    selectedStudentIp = ip;
    isCodeEdited = false;
    
    document.getElementById('codeViewerPlaceholder').style.display = 'none';
    document.getElementById('codeViewerContent').style.display = 'flex';
    
    document.querySelectorAll('.student-bar').forEach(el => el.classList.remove('selected-bar'));
    const activeBar = document.getElementById('box-' + ip.replace(/\./g, '-'));
    if (activeBar) activeBar.classList.add('selected-bar');

    document.getElementById('teacherTerminal').innerText = "Oczekiwanie na uruchomienie kodu...";
    document.getElementById('teacherTerminal').style.color = "#ffffff";

    updateRightPanel(true);
}

function updateRightPanel(forceLoad = false) {
    if (!selectedStudentIp || !globalStateCache.progress) return;

    const ip = selectedStudentIp;
    const name = globalStateCache.names[ip] || "Stanowisko";
    const code = globalStateCache.codes[ip] || "# Uczeń nie przesłał jeszcze żadnego kodu dla tego zadania.";
    const isDone = globalStateCache.progress[ip];

    document.getElementById('viewedStudentName').innerText = "Uczeń: " + name;
    document.getElementById('viewedStudentIp').innerText = "Adres IP: " + ip + " | Zadanie: " + globalStateCache.task_numbers[ip] + " / " + totalTasks;
    
    const codeBox = document.getElementById('globalCodePreview');
    
    if (!isCodeEdited || forceLoad) {
        if (codeBox.value !== code) {
            codeBox.value = code;
        }
    }

    const actionsBlock = document.getElementById('viewerActions');
    if (isDone && globalStateCache.task_numbers[ip] <= totalTasks) {
        actionsBlock.style.display = 'flex';
    } else {
        actionsBlock.style.display = 'none';
    }
}

function startLesson() {
    const isShuffleChecked = document.getElementById('shuffleCheck').checked;

    fetch('/start_lesson', { 
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ shuffle: isShuffleChecked })
    })
    .then(res => res.json()).then(data => {
        if(data.success) {
            document.getElementById('startLessonBtn').style.display = 'none';
            document.getElementById('shuffleOptionWrapper').style.display = 'none';
        }
    });
}

function acceptSelected() {
    if (!selectedStudentIp) return;
    const body = new URLSearchParams();
    body.append('ip', selectedStudentIp);

    fetch('/accept_task', { method: 'POST', body: body })
    .then(res => res.json()).then(data => {
        if(!data.success) alert(data.message);
    });
}

function rejectSelected() {
    if (!selectedStudentIp) return;
    
    const reason = prompt("Wpisz wskazówkę dla ucznia dlaczego zadanie zostało odrzucone:");
    if (reason === null) return;

    const currentEditedCode = document.getElementById('globalCodePreview').value;

    const body = new URLSearchParams();
    body.append('ip', selectedStudentIp);
    body.append('reason', reason);
    body.append('code', currentEditedCode);

    fetch('/reject_task', { method: 'POST', body: body })
    .then(res => res.json()).then(data => {
        if(!data.success) alert(data.message);
    });
}

function restartAll() {
    if(confirm("Czy na pewno chcesz zresetować wszystkich uczniów, ich kody oraz zamknąć dostęp do zadań (wymagany będzie ponowny START)?")) {
        fetch('/restart_tasks', { method: 'POST' }).then(() => location.reload());
    }
}

function refreshStatus() {
    fetch('/status').then(res => res.json()).then(data => {
        globalStateCache = data;
        
        const startBtn = document.getElementById('startLessonBtn');
        const shuffleWrap = document.getElementById('shuffleOptionWrapper');
        if (data.lesson_started) {
            startBtn.style.display = 'none';
            shuffleWrap.style.display = 'none';
        } else {
            startBtn.style.display = 'inline-block';
            shuffleWrap.style.display = 'block';
        }
        
        for (let ip in data.progress) {
            const id = 'box-' + ip.replace(/\./g, '-');
            const el = document.getElementById(id);
            if (!el) continue;
            
            const statusTxt = el.querySelector('.status-text');
            const taskNumTxt = el.querySelector('.task-num-text');
            const nameEl = el.querySelector('.student-name-text');
            
            if (data.names[ip]) nameEl.innerText = data.names[ip];
            taskNumTxt.innerText = data.task_numbers[ip];
            
            let baseClass = 'student-bar ';
            if (ip === selectedStudentIp) baseClass += 'selected-bar ';

            if (data.help[ip]) {
                el.className = baseClass + 'need-help';
                statusTxt.innerText = "POMOC";
            } else if (data.progress[ip]) {
                el.className = baseClass + 'done';
                statusTxt.innerText = "OCENA";
            } else {
                el.className = baseClass + 'pending';
                statusTxt.innerText = data.lesson_started ? "Praca" : "Blokada";
            }
        }
        updateRightPanel(false);
    });
}

// Inicjalizacja skryptu
initTeacherPyodide();
setInterval(refreshStatus, 2000);
