let currentTaskId = document.body.getAttribute('data-task-id');
let pyodideInstance = null;
let isAlreadyRejected = false; 

// Inicjalizacja środowiska Pyodide w tle po załadowaniu strony
async function initPyodide() {
    const outputBox = document.getElementById('output');
    try {
        pyodideInstance = await loadPyodide();
        outputBox.innerText = "Środowisko Python gotowe do uruchomienia.";
    } catch (err) {
        outputBox.innerText = "Błąd podczas ładowania silnika Python: " + err;
    }
}

// Funkcja wykonująca kod w przeglądarce za pomocą Pyodide
async function runPythonCode() {
    if (!pyodideInstance) {
        alert("Silnik Pythona wciąż się ładuje, poczekaj chwilę...");
        return;
    }

    const code = document.getElementById('studentCode').value;
    const outputBox = document.getElementById('output');
    outputBox.innerText = "Uruchamianie...\n";
    outputBox.style.color = "#fff";

    try {
        pyodideInstance.runPython(`
            import sys
            import io
            sys.stdout = io.StringIO()
        `);

        await pyodideInstance.runPythonAsync(code);

        const stdout = pyodideInstance.runPython("sys.stdout.getvalue()");
        outputBox.innerText = stdout ? stdout : "Program zakończył działanie (brak danych wyjściowych).";
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
        
        // Obsługa przejścia do nowego zadania (akceptacja poprzedniego)
        if (data.task_id !== currentTaskId) {
            currentTaskId = data.task_id;
            document.body.setAttribute('data-task-id', data.task_id);
            taskContainer.innerText = data.task_text;
            studentCode.value = ""; 
            studentCode.disabled = false;
            mainBtn.disabled = false;
            runBtn.disabled = false;
            mainBtn.innerText = "WYŚLIJ DO OCENY";
            helpBtn.style.display = "inline-block";
            bannerContainer.innerHTML = "";
            document.getElementById('output').innerText = "Środowisko Python gotowe do uruchomienia.";
            isAlreadyRejected = false; 
            return;
        }

        // Oczekiwanie na sprawdzenie kodu przez nauczyciela
        if (data.progress === true) {
            studentCode.disabled = true;
            mainBtn.disabled = true;
            runBtn.disabled = true;
            mainBtn.innerText = "OCZEKIWANIE NA OCENĘ";
            helpBtn.style.display = "none";
            bannerContainer.innerHTML = "";
            isAlreadyRejected = false; 
        } 
        // Zadanie odrzucone - wstrzyknięcie poprawek nauczyciela
        else if (data.progress === false && data.rejection_msg !== "") {
            studentCode.disabled = false;
            mainBtn.disabled = false;
            runBtn.disabled = false;
            mainBtn.innerText = "WYŚLIJ POPRAWIONY KOD";
            helpBtn.style.display = "inline-block";
            
            // Bezpieczne łączenie stringów bez używania `${}`
            bannerContainer.innerHTML = 
                '<div class="rejection-banner">' +
                    '<strong>Zadanie zwrócone do poprawy:</strong><br>' +
                    data.rejection_msg +
                '</div>';

            // Nadpisanie kodu wersją nauczyciela (wykonuje się tylko RAZ przy zmianie stanu)
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
        if(data.is_helping) {
            btn.innerText = "CZEKAJ";
            btn.classList.add('active');
        } else {
            btn.innerText = "POMOC";
            btn.classList.remove('active');
        }
    });
}

function sendDone() {
    const studentCodeElement = document.getElementById('studentCode');
    const codeValue = studentCodeElement.value.trim();
    if(!codeValue) {
        alert("Nie możesz wysłać pustego pola tekstowego!");
        return;
    }

    if(confirm("Czy na pewno chcesz wysłać ten kod do oceny?")) {
        const body = new URLSearchParams();
        body.append('code', codeValue);

        fetch('/done', { method: 'POST', body: body }).then(res => {
            if(res.ok) {
                studentCodeElement.disabled = true;
                document.getElementById('mainBtn').disabled = true;
                document.getElementById('mainBtn').innerText = "OCZEKIWANIE NA OCENĘ";
                document.getElementById('runBtn').disabled = true;
                document.getElementById('helpBtn').style.display = "none";
            }
        });
    }
}

// Uruchomienie procedur po załadowaniu skryptu
initPyodide();
setInterval(fetchStatus, 2000);
