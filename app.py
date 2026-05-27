import uuid
import os
import json
from flask import Flask, render_template, request, jsonify, abort, session, redirect, url_for

app = Flask(__name__)

app.secret_key = os.urandom(24)

# --- KONFIGURACJA HASŁA ---
TEACHER_PASSWORD = "rabarbar"

# --- KONFIGURACJA ŚCIEŻEK ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TASKS_FILE_PATH = os.path.join(BASE_DIR, 'zadania.txt')
STATE_FILE_PATH = os.path.join(BASE_DIR, 'stan_lekcji.json')  # Plik bazy stanu

# --- KONFIGURACJA STACJI (PULA 192.169.0.0/24) ---
# --- KONFIGURACJA STACJI (AUTOMATYCZNA GENERACJA PULI 192.169.0.0/24) ---

# Automatyczne tworzenie 18 stanowisk od .101 do .118
STUDENTS = {
    f'192.169.0.{i}': f'Stanowisko {i - 100}' for i in range(101, 119)
}

# Ręczne dodanie adresów nauczyciela i środowiska testowego
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

# --- LOGIKA ZAPISU I ODCZYTU STANU ---
def save_state_to_disk():
    """Zapisuje aktualny słownik stanu do pliku JSON."""
    try:
        with open(STATE_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(state, f, ensure_ascii=False, indent=4)
    except Exception as e:
        print(f"[DEBUG] Błąd zapisu stanu: {e}")

def load_state_from_disk():
    """Wczytuje stan z pliku JSON lub tworzy domyślny startowy."""
    if os.path.exists(STATE_FILE_PATH):
        try:
            with open(STATE_FILE_PATH, 'r', encoding='utf-8') as f:
                saved_state = json.load(f)
                # Weryfikacja czy struktura kluczy pasuje do listy stacji
                # (zabezpieczenie na wypadek zmiany listy STUDENTS w locie)
                for key in ["student_tasks", "student_task_ids", "progress", "help_requests", "student_names"]:
                    for ip in STUDENTS:
                        if ip not in saved_state[key]:
                            saved_state[key][ip] = "" if key == "student_names" else (str(uuid.uuid4()) if key == "student_task_ids" else 0 if key == "student_tasks" else False)
                print("[DEBUG] Pomyślnie odtworzono stan lekcji z pliku.")
                return saved_state
        except Exception as e:
            print(f"[DEBUG] Błąd odczytu pliku stanu, tworzę nowy: {e}")
            
    print("[DEBUG] Brak zapisanego stanu. Inicjalizacja nowej lekcji.")
    return {
        "student_tasks": {ip: 0 for ip in STUDENTS},
        "student_task_ids": {ip: str(uuid.uuid4()) for ip in STUDENTS},
        "progress": {ip: False for ip in STUDENTS},
        "help_requests": {ip: False for ip in STUDENTS},
        "student_names": {ip: "" for ip in STUDENTS}
    }

# --- INICJALIZACJA STANU ---
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
    
    task_idx = state["student_tasks"][client_ip]
    current_task_text = tasks_list[task_idx] if task_idx < len(tasks_list) else "Wszystkie zadania wykonane!"
    
    return render_template('student.html', 
                           name=state["student_names"][client_ip], 
                           station=station_name,
                           task=current_task_text, 
                           task_id=state["student_task_ids"][client_ip])

@app.route('/set_name', methods=['POST'])
def set_name():
    check_ip_permission()
    client_ip = request.remote_addr
    name = request.form.get('student_name', '').strip()
    
    if name:
        state["student_names"][client_ip] = name
        save_state_to_disk()  # Zapis po rejestracji ucznia
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    check_ip_permission()
    error = None
    if request.method == 'POST':
        if request.form.get('password') == TEACHER_PASSWORD:
            session['logged_in'] = True
            return redirect(url_for('teacher_view'))
        else:
            error = "Niepoprawne hasło!"
    return render_template('login.html', error=error)

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return "Wylogowano pomyślnie."

@app.route('/next_student_task', methods=['POST'])
def next_student_task():
    check_ip_permission()
    if not is_teacher_logged_in():
        abort(401)
        
    student_ip = request.form.get('ip')
    if student_ip in STUDENTS:
        current_idx = state["student_tasks"][student_ip]
        if current_idx < len(tasks_list) - 1:
            state["student_tasks"][student_ip] += 1
            state["student_task_ids"][student_ip] = str(uuid.uuid4())
            state["progress"][student_ip] = False
            state["help_requests"][student_ip] = False
            save_state_to_disk()  # Zapis po przesłaniu kolejnego zadania
            return jsonify({"success": True})
        return jsonify({"success": False, "message": "To już ostatnie zadanie"})
    return jsonify({"success": False, "message": "Niepoprawne IP"})

@app.route('/restart_tasks', methods=['POST'])
def restart_tasks():
    check_ip_permission()
    if not is_teacher_logged_in():
        abort(401)
        
    for ip in STUDENTS:
        state["student_tasks"][ip] = 0
        state["student_task_ids"][ip] = str(uuid.uuid4())
        state["progress"][ip] = False
        state["help_requests"][ip] = False
        state["student_names"][ip] = ""
    save_state_to_disk()  # Zapis po resecie całej lekcji
    return jsonify({"success": True})

@app.route('/check_updates')
def check_updates():
    client_ip = request.remote_addr
    task_id = state["student_task_ids"].get(client_ip, "")
    return jsonify({"task_id": task_id})

@app.route('/done', methods=['POST'])
def mark_done():
    check_ip_permission()
    client_ip = request.remote_addr
    state["progress"][client_ip] = True
    state["help_requests"][client_ip] = False
    save_state_to_disk()  # Zapis po wykonaniu zadania przez ucznia
    return "OK", 200

@app.route('/need_help', methods=['POST'])
def need_help():
    check_ip_permission()
    client_ip = request.remote_addr
    state["help_requests"][client_ip] = not state["help_requests"][client_ip]
    save_state_to_disk()  # Zapis przy wezwaniu/odwołaniu pomocy
    return jsonify({"is_helping": state["help_requests"][client_ip]}), 200

@app.route('/teacher')
def teacher_view():
    check_ip_permission()
    if not is_teacher_logged_in():
        return redirect(url_for('login'))
        
    return render_template('teacher.html', 
                           students=STUDENTS,
                           total_tasks=len(tasks_list))

@app.route('/status')
def get_status():
    check_ip_permission()
    if not is_teacher_logged_in():
        abort(401)
        
    task_numbers = {ip: idx + 1 for ip, idx in state["student_tasks"].items()}
    return jsonify({
        "progress": state["progress"],
        "help": state["help_requests"],
        "task_numbers": task_numbers,
        "names": state["student_names"]
    })

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)