let selectedStudentIp = null;
let globalStateCache = null;
let pyodideInstance = null;

async function initTeacherPyodide() {
    const terminal = document.getElementById('teacherTerminal');
    try {
        pyodideInstance = await loadPyodide();
        if (terminal) terminal.innerText = "Wirtualny interpreter Python gotowy do ewaluacji rozwiązań.";
    } catch (err) {
        if (terminal) terminal.innerText = "Błąd inicjalizacji interpretera Pyodide: " + err;
    }
}

async function runStudentCode() {
    if (!pyodideInstance) { alert("Trwa uruchamianie interpretera Pythona. Poczekaj chwilę..."); return; }
    const code = document.getElementById('globalCodePreview').value;
    const terminal = document.getElementById('teacherTerminal');
    
    if (terminal) terminal.innerText = "Uruchamianie kodu ucznia...\n";
    try {
        pyodideInstance.runPython(`import sys, io; sys.stdout = io.StringIO()`);
        await pyodideInstance.runPythonAsync(code);
        const stdout = pyodideInstance.runPython("sys.stdout.getvalue()");
        if (terminal) {
            terminal.innerText = stdout ? stdout : "Program zakończył działanie (brak danych wyjściowych).";
            terminal.style.color = "#00ff00";
        }
    } catch (err) {
        if (terminal) {
            terminal.innerText = err.message;
            terminal.style.color = "#ff6b6b";
        }
    }
}

function selectStudent(ip) {
    selectedStudentIp = ip;
    updateRightPanel(true);
    
    document.querySelectorAll('.student-bar').forEach(el => el.classList.remove('selected-bar'));
    const currentBox = document.getElementById('box-' + ip.replace(/\./g, '-'));
    if (currentBox) currentBox.classList.add('selected-bar');
}

function updateRightPanel(forceCodeReload) {
    if (!selectedStudentIp || !globalStateCache) return;

    const placeholder = document.getElementById('codeViewerPlaceholder');
    const content = document.getElementById('codeViewerContent');
    const nameHeader = document.getElementById('viewedStudentName');
    const ipSub = document.getElementById('viewedStudentIp');
    const previewBox = document.getElementById('globalCodePreview');

    if (placeholder) placeholder.style.display = 'none';
    if (content) content.style.display = 'flex';

    const name = globalStateCache.names[selectedStudentIp] || "Nieznany uczeń";
    if (nameHeader) nameHeader.innerText = "Stanowisko: " + name;
    if (ipSub) ipSub.innerText = "IP ucznia: " + selectedStudentIp;

    if (forceCodeReload) {
        const studentCode = globalStateCache.codes[selectedStudentIp] || "";
        if (previewBox) previewBox.value = studentCode;
        const terminal = document.getElementById('teacherTerminal');
        if (terminal) {
            terminal.innerText = "Wczytano kod stanowiska. Kliknij 'URUCHOM KOD UCZNIA' celem weryfikacji.";
            terminal.style.color = "#ffffff";
        }
    }
}

function refreshStatus() {
    fetch('/status').then(res => res.json()).then(data => {
        globalStateCache = data;
        
        const startBtn = document.getElementById('startLessonBtn');
        const stopBtn = document.getElementById('stopLessonBtn');
        const shuffleWrap = document.getElementById('shuffleOptionWrapper');
        const tagWrap = document.getElementById('tagSelectWrapper');
        const lessonsLink = document.getElementById('historyLessonsLink');
        
        const dashboardContainer = document.getElementById('dashboardContainer');
        if (dashboardContainer && data.total_tasks) {
            dashboardContainer.setAttribute('data-total-tasks', data.total_tasks);
        }
        
        if (data.lesson_started) {
            if (shuffleWrap) shuffleWrap.style.display = 'none';
            if (tagWrap) tagWrap.style.display = 'none';
            
            if (data.submissions_allowed) {
                if (startBtn) startBtn.style.display = 'none';
                if (stopBtn) stopBtn.style.display = 'inline-block';
                if (lessonsLink) lessonsLink.style.display = 'none';
            } else {
                if (startBtn) {
                    startBtn.style.display = 'inline-block';
                    startBtn.innerText = "WZNÓW";
                }
                if (stopBtn) stopBtn.style.display = 'none';
                if (lessonsLink) lessonsLink.style.display = 'inline-block';
            }
        } else {
            if (startBtn) {
                startBtn.style.display = 'inline-block';
                startBtn.innerText = "START";
            }
            if (stopBtn) stopBtn.style.display = 'none';
            if (shuffleWrap) shuffleWrap.style.display = 'block';
            if (tagWrap) tagWrap.style.display = 'block';
            if (lessonsLink) lessonsLink.style.display = 'inline-block';
        }
        
        for (let ip in data.progress) {
            const id = 'box-' + ip.replace(/\./g, '-');
            const el = document.getElementById(id);
            if (!el) continue;
            
            const statusTxt = el.querySelector('.status-text');
            const taskBlock = el.querySelector('.student-task-block');
            const nameEl = el.querySelector('.student-name-text');
            
            if (data.names[ip]) nameEl.innerText = data.names[ip];
            
            // Poprawka: Bezpośrednie nadpisywanie całego kontenera usuwa stare śmieci kodu Jinja
            if (data.lesson_started && data.names[ip]) {
                taskBlock.innerText = "Zad: " + data.task_numbers[ip] + " / " + data.total_tasks;
            } else {
                taskBlock.innerText = "Zad: -";
            }
            
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
    }).catch(err => console.error("Błąd odświeżania dashboardu: ", err));
}

function triggerStartLesson() {
    const tagSelect = document.getElementById('lessonTagSelect');
    const shuffleCheck = document.getElementById('shuffleCheck');
    
    const tagValue = tagSelect ? tagSelect.value : "";
    const shuffleValue = shuffleCheck ? shuffleCheck.checked : false;

    const params = new URLSearchParams();
    params.append('tag', tagValue);
    params.append('shuffle', shuffleValue);

    fetch('/start_lesson', { method: 'POST', body: params })
    .then(res => res.json())
    .then(data => {
        if (data.status === "started") {
            refreshStatus();
        } else {
            alert("Błąd: " + data.message);
        }
    });
}

function triggerStopLesson() {
    fetch('/stop_lesson', { method: 'POST' }).then(() => refreshStatus());
}

function restartAll() {
    if (confirm("Czy na pewno chcesz wyczyścić stan lekcji i zresetować wszystkich uczniów?")) {
        fetch('/restart_all', { method: 'POST' }).then(() => {
            selectedStudentIp = null;
            const placeholder = document.getElementById('codeViewerPlaceholder');
            const content = document.getElementById('codeViewerContent');
            if (placeholder) placeholder.style.display = 'block';
            if (content) content.style.display = 'none';
            refreshStatus();
        });
    }
}

function acceptSelected() {
    if (!selectedStudentIp) return;
    const params = new URLSearchParams();
    params.append('ip', selectedStudentIp);
    
    fetch('/accept', { method: 'POST', body: params }).then(() => {
        const previewBox = document.getElementById('globalCodePreview');
        if (previewBox) previewBox.value = "";
        refreshStatus();
    });
}

function rejectSelected() {
    if (!selectedStudentIp) return;
    const msg = prompt("Wpisz uwagi i wskazówki dla ucznia (co należy poprawić):");
    if (msg === null) return; 

    const params = new URLSearchParams();
    params.append('ip', selectedStudentIp);
    params.append('msg', msg);
    
    fetch('/reject', { method: 'POST', body: params }).then(() => refreshStatus());
}

initTeacherPyodide();
setInterval(refreshStatus, 1000);
