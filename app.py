import uuid
import os
import json
import random
from flask import Flask, render_template, request, jsonify, abort, session, redirect, url_for

app = Flask(__name__)
# Bezpieczny klucz sesji dla ciasteczek logowania nauczyciela
app.secret_key = os.urandom(24)

# Hasło dostępowe do panelu nauczyciela (/login)
TEACHER_PASSWORD = "rabarbar"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_FILE_PATH = os.path.join(BASE_DIR, 'zadania.txt')
STATE_FILE_PATH = os.path.join(BASE_DIR, 'stan_lekcji.json')

# Pula autoryzowanych adresów IP w pracowni dla 18 stanowisk
STUDENTS = {
    f'192.169.0.{i}': f'Stanowisko {i - 100}' for i in range(101, 119)
}
# Dodatkowe IP do testów lokalnych i administracji
STUDENTS['192.169.0.224'] = 'Nauczyciel (Lokalnie)'
STUDENTS['127.0.0.1'] = 'Nauczyciel (Test)'

def load_tasks():
    """Wczytuje listę zadań z pliku tekstowego."""
    if not os.path.exists(TASKS_FILE_PATH):
        return ["Błąd: Nie znaleziono pliku zadania.txt"]
    try:
        with open(TASKS_FILE_PATH, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
            return lines if lines else ["Błąd: Plik zadania.txt jest pusty"]
    except Exception as e:
        return [f"Błąd odczytu pliku: {e}"]

def save_state_to_disk():
    """Zapisuje aktualny stan całej lekcji do pliku JSON."""
    try:
        with open(STATE_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[DEBUG] Błąd zapisu stanu: {e}")

def load_state_from_disk():
    """Wczytuje stan lekcji z dysku lub inicjalizuje strukturę startową."""
    keys = ["student_tasks", "student_task_ids", "progress", "help_requests", "student_names", "student_codes", "rejection_messages", "student_task_maps"]
    if os.path.exists(STATE_FILE_PATH):
        try:
            with open(STATE_FILE_PATH, 'r', encoding='utf-8') as f:
                saved_state = json.load(f)
                if "lesson_started" not in saved_state: saved_state["lesson_started"] = False
                for key in keys:
                    if key not in saved_state: saved_state[key] = {}
                    for ip in STUDENTS:
                        if ip not in saved_state[key]:
                            if key == "student_tasks": saved_state[key][ip] = 0
                            elif key == "student_task_ids": saved_state[key][ip] = str(uuid.uuid4())
                            elif key == "student_task_maps": saved_state[key][ip] = list(range(len(tasks_list)))
                            elif key in ["progress", "help_requests"]: saved_state[key][ip] = False
                            else: saved_state[key][ip] = ""
                return saved_state
        except Exception as e:
            print(f"[DEBUG] Błąd odczytu stanu: {e}")
            
    return {
        "lesson_started": False,
        "student_tasks": {ip: 0 for ip in STUDENTS},
        "student_task_ids": {ip: str(uuid.uuid4()) for ip in STUDENTS},
        "student_task_maps": {ip: list(range(len(tasks_list))) for ip in STUDENTS},
        "progress": {ip: False for ip in STUDENTS},
        "help_requests": {ip: False for ip in STUDENTS},
        "student_names": {ip: "" for ip in STUDENTS},
        "student_codes": {ip: "" for ip in STUDENTS},
        "rejection_messages": {ip: "" for ip in STUDENTS}
    }

tasks_list = load_tasks()
state = load_state_from_disk()

def check_ip_permission():
    """Weryfikuje, czy klient łączy się z dozwolonego IP z puli szkolnej."""
    client_ip = request.remote_addr
    if client_ip not in STUDENTS:
        abort(403)

def is_teacher_logged_in():
    """Sprawdza stan sesji logowania nauczyciela."""
    return session.get('logged_in') is True

@app.route('/')
def index():
    check_ip_permission()
    client_ip = request.remote_addr
    station_name = STUDENTS.get(client_ip)
    
    # Wymuszenie wpisania imienia na starcie
    if not state["student_names"][client_ip]:
        return render_template('register.html', station=station_name)
    
    # Blokada zadań przed uruchomieniem lekcji zielonym przyciskiem START
    if not state["lesson_started"]:
        return render_template('student.html', 
                               name=state["student_names"][client_ip], 
                               station=station_name,
                               task="Oczekiwanie na rozpoczęcie lekcji przez nauczyciela...", 
                               task_id="lock",
                               rejection_msg="")
    
    task_step = state["student_tasks"][client_ip]
    task_map = state["student_task_maps"].get(client_ip, list(range(len(tasks_list))))
    
    if task_step < len(task_map):
        actual_task_idx = task_map[task_step]
        current_task_text = tasks_list[actual_task_idx]
    else:
        current_task_text = "Wszystkie zadania wykonane!"
    
    return render_template('student.html', 
                           name=state["student_names"][client_ip], 
                           station=station_name,
                           task=current_task_text, 
                           task_id=state["student_task_ids"][client_ip],
                           rejection_msg=state["rejection_messages"][client_ip])

@app.route('/set_name', methods=['POST'])
def set_name():
    check_ip_permission()
    client_ip = request.remote_addr
    name = request.form.get('student_name', '').strip()
    if name:
        state["student_names"][client_ip] = name
        save_state_to_disk()
    return redirect(url_for('index'))

@app.route('/student_status')
def student_status():
    """Zwraca aktualny stan zadania wraz z kodem dla pętli odświeżającej interfejs ucznia."""
    check_ip_permission()
    client_ip = request.remote_addr
    
    if not state["lesson_started"]:
        return jsonify({
            "task_id": "lock",
            "task_text": "Oczekiwanie na rozpoczęcie lekcji przez nauczyciela...",
            "progress": False,
            "rejection_msg": "",
            "code": ""
        })
        
    task_step = state["student_tasks"][client_ip]
    task_map = state["student_task_maps"].get(client_ip, list(range(len(tasks_list))))
    
    if task_step < len(task_map):
        actual_task_idx = task_map[task_step]
        current_task_text = tasks_list[actual_task_idx]
    else:
        current_task_text = "Wszystkie zadania wykonane!"
    
    return jsonify({
        "task_id": state["student_task_ids"].get(client_ip, ""),
        "task_text": current_task_text,
        "progress": state["progress"][client_ip],
        "rejection_msg": state["rejection_messages"][client_ip],
        "code": state["student_codes"].get(client_ip, "")
    })

@app.route('/start_lesson', methods=['POST'])
def start_lesson():
    """Uruchamia lekcję i generuje mapy kolejności zadań (opcjonalne mieszanie)."""
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    
    should_shuffle = request.json.get('shuffle', False) if request.is_json else False
    
    state["lesson_started"] = True
    
    for ip in STUDENTS:
        task_indices = list(range(len(tasks_list)))
        if should_shuffle:
            random.shuffle(task_indices)
            
        state["student_task_maps"][ip] = task_indices
        state["student_tasks"][ip] = 0
        state["student_task_ids"][ip] = str(uuid.uuid4())
        
    save_state_to_disk()
    return jsonify({"success": True})

@app.route('/done', methods=['POST'])
def mark_done():
    """Odbiera przesłany przez ucznia kod źródłowy i zmienia status na OCENA."""
    check_ip_permission()
    if not state["lesson_started"]: abort(400)
    client_ip = request.remote_addr
    code_submission = request.form.get('code', '').strip()
    
    state["progress"][client_ip] = True
    state["help_requests"][client_ip] = False
    state["student_codes"][client_ip] = code_submission
    state["rejection_messages"][client_ip] = ""
    save_state_to_disk()
    return "OK", 200

@app.route('/need_help', methods=['POST'])
def need_help():
    check_ip_permission()
    if not state["lesson_started"]: abort(400)
    client_ip = request.remote_addr
    state["help_requests"][client_ip] = not state["help_requests"][client_ip]
    save_state_to_disk()
    return jsonify({"is_helping": state["help_requests"][client_ip]}), 200

@app.route('/login', methods=['GET', 'POST'])
def login():
    check_ip_permission()
    error = None
    if request.method == 'POST':
        if request.form.get('password') == TEACHER_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('teacher_view'))
        else: error = "Niepoprawne hasło!"
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return "Wylogowano pomyślnie."

@app.route('/teacher')
def teacher_view():
    check_ip_permission()
    if not is_teacher_logged_in(): return redirect(url_for('login'))
    return render_template('teacher.html', students=STUDENTS, total_tasks=len(tasks_list))

@app.route('/status')
def get_status():
    """Zwraca zbiorczy stan całej klasy do dashboardu nauczyciela."""
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    task_numbers = {ip: idx + 1 for ip, idx in state["student_tasks"].items()}
    return jsonify({
        "lesson_started": state["lesson_started"],
        "progress": state["progress"],
        "help": state["help_requests"],
        "task_numbers": task_numbers,
        "names": state["student_names"],
        "codes": state["student_codes"]
    })

@app.route('/accept_task', methods=['POST'])
def accept_task():
    """Zalicza aktualne zadanie i generuje nowy identyfikator kroku dla ucznia."""
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    student_ip = request.form.get('ip')
    if student_ip in STUDENTS:
        current_idx = state["student_tasks"][student_ip]
        task_map = state["student_task_maps"].get(student_ip, [])
        
        if current_idx < len(task_map) - 1:
            state["student_tasks"][student_ip] += 1
            state["student_task_ids"][student_ip] = str(uuid.uuid4())
            state["progress"][student_ip] = False
            state["help_requests"][student_ip] = False
            state["student_codes"][student_ip] = ""
            state["rejection_messages"][student_ip] = ""
            save_state_to_disk()
            return jsonify({"success": True})
        elif current_idx == len(task_map) - 1:
            state["student_tasks"][student_ip] += 1
            state["student_task_ids"][student_ip] = str(uuid.uuid4())
            state["progress"][student_ip] = False
            state["help_requests"][student_ip] = False
            state["student_codes"][student_ip] = ""
            state["rejection_messages"][student_ip] = ""
            save_state_to_disk()
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "Uczeń zakończył już cały kurs."})
    return jsonify({"success": False, "message": "Niepoprawne IP"})

@app.route('/reject_task', methods=['POST'])
def reject_task():
    """Odsyła zadanie do poprawy, nadpisując kod ucznia wersją z poprawkami nauczyciela."""
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    
    student_ip = request.form.get('ip')
    reason = request.form.get('reason', '').strip()
    edited_code = request.form.get('code', '')
    
    if student_ip in STUDENTS:
        state["progress"][student_ip] = False
        state["rejection_messages"][student_ip] = reason if reason else "Twój kod wymaga poprawek."
        
        # Zapisujemy kod zawierający modyfikacje dokonane przez nauczyciela
        if edited_code:
            state["student_codes"][student_ip] = edited_code
            
        save_state_to_disk()
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Niepoprawne IP"})

@app.route('/restart_tasks', methods=['POST'])
def restart_tasks():
    """Resetuje stan całej lekcji do ustawień początkowych (czerwony przycisk RESETUJ)."""
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    state["lesson_started"] = False
    for ip in STUDENTS:
        state["student_tasks"][ip] = 0
        state["student_task_ids"][ip] = str(uuid.uuid4())
        state["student_task_maps"][ip] = list(range(len(tasks_list)))
        state["progress"][ip] = False
        state["help_requests"][ip] = False
        state["student_names"][ip] = ""
        state["student_codes"][ip] = ""
        state["rejection_messages"][ip] = ""
    save_state_to_disk()
    return jsonify({"success": True})

if __name__ == '__main__':
    # Uruchomienie serwera na porcie 5000, dostępnego w sieci lokalnej pracowni
    app.run(host='0.0.0.0', port=5000, debug=False)
