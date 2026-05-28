import uuid
import os
import json
from flask import Flask, render_template, request, jsonify, abort, session, redirect, url_for

app = Flask(__name__)
app.secret_key = os.urandom(24)

TEACHER_PASSWORD = "rabarbar"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_FILE_PATH = os.path.join(BASE_DIR, 'zadania.txt')
STATE_FILE_PATH = os.path.join(BASE_DIR, 'stan_lekcji.json')

STUDENTS = {
    f'192.169.0.{i}': f'Stanowisko {i - 100}' for i in range(101, 119)
}
STUDENTS['192.169.0.224'] = 'Nauczyciel (Lokalnie)'
STUDENTS['127.0.0.1'] = 'Nauczyciel (Test)'

def load_tasks():
    if not os.path.exists(TASKS_FILE_PATH):
        return ["Błąd: Nie znaleziono pliku zadania.txt"]
    try:
        with open(TASKS_FILE_PATH, 'r', encoding='utf-8') as f:
            lines = [line.strip() for line in f.readlines() if line.strip()]
            return lines if lines else ["Błąd: Plik zadania.txt jest pusty"]
    except Exception as e:
        return [f"Błąd odczytu pliku: {e}"]

def save_state_to_disk():
    try:
        with open(STATE_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[DEBUG] Błąd zapisu stanu: {e}")

def load_state_from_disk():
    keys = ["student_tasks", "student_task_ids", "progress", "help_requests", "student_names", "student_codes", "rejection_messages"]
    if os.path.exists(STATE_FILE_PATH):
        try:
            with open(STATE_FILE_PATH, 'r', encoding='utf-8') as f:
                saved_state = json.load(f)
                if "lesson_started" not in saved_state:
                    saved_state["lesson_started"] = False
                for key in keys:
                    if key not in saved_state: saved_state[key] = {}
                    for ip in STUDENTS:
                        if ip not in saved_state[key]:
                            if key == "student_tasks": saved_state[key][ip] = 0
                            elif key == "student_task_ids": saved_state[key][ip] = str(uuid.uuid4())
                            elif key in ["progress", "help_requests"]: saved_state[key][ip] = False
                            else: saved_state[key][ip] = ""
                return saved_state
        except Exception as e:
            print(f"[DEBUG] Błąd odczytu stanu: {e}")
            
    return {
        "lesson_started": False,  # Domyślnie lekcja jest zablokowana po restarcie/starcie
        "student_tasks": {ip: 0 for ip in STUDENTS},
        "student_task_ids": {ip: str(uuid.uuid4()) for ip in STUDENTS},
        "progress": {ip: False for ip in STUDENTS},
        "help_requests": {ip: False for ip in STUDENTS},
        "student_names": {ip: "" for ip in STUDENTS},
        "student_codes": {ip: "" for ip in STUDENTS},
        "rejection_messages": {ip: "" for ip in STUDENTS}
    }

tasks_list = load_tasks()
state = load_state_from_disk()

def check_ip_permission():
    client_ip = request.remote_addr
    if client_ip not in STUDENTS:
        abort(403)

def is_teacher_logged_in():
    return session.get('logged_in') is True

@app.route('/')
def index():
    check_ip_permission()
    client_ip = request.remote_addr
    station_name = STUDENTS.get(client_ip)
    
    if not state["student_names"][client_ip]:
        return render_template('register.html', station=station_name)
    
    # Jeśli nauczyciel jeszcze nie wystartował lekcji, uczeń widzi ekran oczekiwania
    if not state["lesson_started"]:
        return render_template('student.html', 
                               name=state["student_names"][client_ip], 
                               station=station_name,
                               task="Oczekiwanie na rozpoczęcie lekcji przez nauczyciela...", 
                               task_id="lock",
                               rejection_msg="")
    
    task_idx = state["student_tasks"][client_ip]
    current_task_text = tasks_list[task_idx] if task_idx < len(tasks_list) else "Wszystkie zadania wykonane!"
    
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
    check_ip_permission()
    client_ip = request.remote_addr
    
    if not state["lesson_started"]:
        return jsonify({
            "task_id": "lock",
            "task_text": "Oczekiwanie na rozpoczęcie lekcji przez nauczyciela...",
            "progress": False,
            "rejection_msg": ""
        })
        
    task_idx = state["student_tasks"][client_ip]
    current_task_text = tasks_list[task_idx] if task_idx < len(tasks_list) else "Wszystkie zadania wykonane!"
    
    return jsonify({
        "task_id": state["student_task_ids"].get(client_ip, ""),
        "task_text": current_task_text,
        "progress": state["progress"][client_ip],
        "rejection_msg": state["rejection_messages"][client_ip]
    })

@app.route('/start_lesson', methods=['POST'])
def start_lesson():
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    state["lesson_started"] = True
    # Odświeżenie ID stacji, by zmusić przeglądarki uczniów do natychmiastowego pobrania zadań
    for ip in STUDENTS:
        state["student_task_ids"][ip] = str(uuid.uuid4())
    save_state_to_disk()
    return jsonify({"success": True})

@app.route('/done', methods=['POST'])
def mark_done():
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
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    student_ip = request.form.get('ip')
    if student_ip in STUDENTS:
        current_idx = state["student_tasks"][student_ip]
        if current_idx < len(tasks_list) - 1:
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
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    student_ip = request.form.get('ip')
    reason = request.form.get('reason', '').strip()
    if student_ip in STUDENTS:
        state["progress"][student_ip] = False
        state["rejection_messages"][student_ip] = reason if reason else "Twój kod wymaga poprawek."
        save_state_to_disk()
        return jsonify({"success": True})
    return jsonify({"success": False, "message": "Niepoprawne IP"})

@app.route('/restart_tasks', methods=['POST'])
def restart_tasks():
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    state["lesson_started"] = False  # Blokada zadań po pełnym resecie lekcji
    for ip in STUDENTS:
        state["student_tasks"][ip] = 0
        state["student_task_ids"][ip] = str(uuid.uuid4())
        state["progress"][ip] = False
        state["help_requests"][ip] = False
        state["student_names"][ip] = ""
        state["student_codes"][ip] = ""
        state["rejection_messages"][ip] = ""
    save_state_to_disk()
    return jsonify({"success": True})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)