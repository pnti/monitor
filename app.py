import uuid
import os
import json
import random
import sqlite3
from datetime import datetime
from flask import Flask, render_template, request, jsonify, abort, session, redirect, url_for

app = Flask(__name__)
app.secret_key = os.urandom(24)

TEACHER_PASSWORD = "rabarbar"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, 'lekcja.db')

STUDENTS = {
    f'192.169.0.{i}': f'Stanowisko {i - 100}' for i in range(101, 119)
}
STUDENTS['192.169.0.224'] = 'Nauczyciel (Lokalnie)'
STUDENTS['127.0.0.1'] = 'Nauczyciel (Test)'

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    """Inicjalizuje strukturę relacyjną bazy danych i dodaje dane startowe."""
    with get_db() as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS allowed_users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name TEXT NOT NULL,
                alias TEXT UNIQUE
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_text TEXT NOT NULL
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS tags (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tag_name TEXT NOT NULL UNIQUE
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS task_tags (
                task_id INTEGER,
                tag_id INTEGER,
                PRIMARY KEY (task_id, tag_id),
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY (tag_id) REFERENCES tags(id) ON DELETE CASCADE
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS lesson_config (
                key TEXT PRIMARY KEY, 
                value TEXT
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS student_state (
                ip TEXT PRIMARY KEY,
                student_name TEXT DEFAULT '',
                current_step INTEGER DEFAULT 0,
                task_uuid TEXT NOT NULL,
                progress BOOLEAN DEFAULT 0,
                help_requested BOOLEAN DEFAULT 0,
                submitted_code TEXT DEFAULT '',
                rejection_message TEXT DEFAULT '',
                task_map TEXT DEFAULT ''
            )
        ''')
        
        conn.execute('''
            CREATE TABLE IF NOT EXISTS submitted_solutions_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name TEXT NOT NULL,
                ip TEXT NOT NULL,
                task_id INTEGER NOT NULL,
                task_text TEXT NOT NULL,
                accepted_code TEXT NOT NULL,
                submitted_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (task_id) REFERENCES tasks(id)
            )
        ''')

        conn.execute('''
            CREATE TABLE IF NOT EXISTS lesson_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        conn.execute('''
            CREATE TABLE IF NOT EXISTS lesson_history_states (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                lesson_id INTEGER,
                ip TEXT NOT NULL,
                student_name TEXT NOT NULL,
                current_step INTEGER NOT NULL,
                task_uuid TEXT NOT NULL,
                progress BOOLEAN NOT NULL,
                help_requested BOOLEAN NOT NULL,
                submitted_code TEXT NOT NULL,
                rejection_message TEXT NOT NULL,
                task_map TEXT NOT NULL,
                FOREIGN KEY (lesson_id) REFERENCES lesson_history(id) ON DELETE CASCADE
            )
        ''')
        
        conn.execute("INSERT OR IGNORE INTO lesson_config (key, value) VALUES ('lesson_started', '0')")
        conn.execute("INSERT OR IGNORE INTO lesson_config (key, value) VALUES ('submissions_allowed', '1')")
        conn.execute("INSERT OR IGNORE INTO lesson_config (key, value) VALUES ('active_task_map', '')")
        
        if conn.execute("SELECT COUNT(*) FROM allowed_users").fetchone()[0] == 0:
            conn.execute("INSERT INTO allowed_users (full_name, alias) VALUES ('Jan Kowalski', 'jkowal')")
            conn.execute("INSERT INTO allowed_users (full_name, alias) VALUES ('Anna Nowak', 'anowak')")
        
        if conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0] == 0:
            cursor = conn.execute("INSERT INTO tags (tag_name) VALUES ('podstawy')")
            id_podstawy = cursor.lastrowid
            
            cursor = conn.execute("INSERT INTO tags (tag_name) VALUES ('pętle')")
            id_petle = cursor.lastrowid
            
            cursor = conn.execute("INSERT INTO tags (tag_name) VALUES ('funkcje')")
            id_funkcje = cursor.lastrowid
            
            cursor = conn.execute("INSERT INTO tasks (task_text) VALUES ('Zadanie 1: Napisz program w Pythonie, który wypisze na ekranie tekst Hello World.')")
            id_zad1 = cursor.lastrowid
            
            cursor = conn.execute("INSERT INTO tasks (task_text) VALUES ('Zadanie 2: Napisz pętlę for wyświetlającą liczby od 1 do 10.')")
            id_zad2 = cursor.lastrowid
            
            cursor = conn.execute("INSERT INTO tasks (task_text) VALUES ('Zadanie 3: Stwórz funkcję obliczającą pole trójkąta.')")
            id_zad3 = cursor.lastrowid
            
            conn.execute("INSERT INTO task_tags (task_id, tag_id) VALUES (?, ?)", (id_zad1, id_podstawy))
            conn.execute("INSERT INTO task_tags (task_id, tag_id) VALUES (?, ?)", (id_zad2, id_petle))
            conn.execute("INSERT INTO task_tags (task_id, tag_id) VALUES (?, ?)", (id_zad3, id_funkcje))
            conn.execute("INSERT INTO task_tags (task_id, tag_id) VALUES (?, ?)", (id_zad3, id_podstawy))
            
        # Zrezygnowano z pre-alokacji bazy na starcie, aby wyświetlali się tylko zalogowani uczniowie.

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
    error_msg = request.args.get('error', '')
    
    with get_db() as conn:
        student = conn.execute("SELECT * FROM student_state WHERE ip = ?", (client_ip,)).fetchone()
        lesson_started = conn.execute("SELECT value FROM lesson_config WHERE key = 'lesson_started'").fetchone()['value'] == '1'
        
        if not student or not student['student_name']:
            return render_template('register.html', station=station_name, error=error_msg)
        
        if not lesson_started:
            return render_template('student.html', 
                                   name=student['student_name'], 
                                   station=station_name,
                                   task="Oczekiwanie na rozpoczęcie lekcji przez nauczyciela...", 
                                   task_id="lock",
                                   rejection_msg="")
        
        task_step = student['current_step']
        task_map_str = student['task_map']
        
        if task_map_str:
            task_ids = [int(x) for x in task_map_str.split(',')]
            
            if task_step < len(task_ids):
                actual_task_id = task_ids[task_step]
                task_row = conn.execute("SELECT task_text FROM tasks WHERE id = ?", (actual_task_id,)).fetchone()
                current_task_text = task_row['task_text'] if task_row else "Błąd: Nie znaleziono zadania w bazie."
                current_task_id = student['task_uuid']
            else:
                current_task_text = "Gratulacje! Wszystkie zadania z tego bloku zostały wykonane."
                current_task_id = "finished"
        else:
            current_task_text = "Brak przydzielonych zadań dla tej lekcji."
            current_task_id = "lock"

        return render_template('student.html', 
                               name=student['student_name'], 
                               station=station_name,
                               task=current_task_text, 
                               task_id=current_task_id,
                               rejection_msg=student['rejection_message'])

@app.route('/set_name', methods=['POST'])
def set_name():
    check_ip_permission()
    client_ip = request.remote_addr
    entered_name = request.form.get('student_name', '').strip()
    
    if not entered_name:
        return redirect(url_for('index', error="Pole z nazwą nie może być puste."))
        
    with get_db() as conn:
        query = '''
            SELECT full_name FROM allowed_users 
            WHERE LOWER(full_name) = LOWER(?) OR (alias IS NOT NULL AND LOWER(alias) = LOWER(?))
        '''
        user_row = conn.execute(query, (entered_name, entered_name)).fetchone()
        
        if user_row:
            lesson_started = conn.execute("SELECT value FROM lesson_config WHERE key = 'lesson_started'").fetchone()['value'] == '1'
            active_map_row = conn.execute("SELECT value FROM lesson_config WHERE key = 'active_task_map'").fetchone()
            active_map = active_map_row['value'] if (lesson_started and active_map_row) else ""

            exists = conn.execute("SELECT 1 FROM student_state WHERE ip = ?", (client_ip,)).fetchone()
            if exists:
                conn.execute("UPDATE student_state SET student_name = ?, task_map = ? WHERE ip = ?", (user_row['full_name'], active_map, client_ip))
            else:
                conn.execute("INSERT INTO student_state (ip, student_name, task_uuid, task_map) VALUES (?, ?, ?, ?)", (client_ip, user_row['full_name'], str(uuid.uuid4()), active_map))
            
            return redirect(url_for('index'))
        else:
            return redirect(url_for('index', error="Nie odnaleziono podanego imienia/nazwiska ani aliasu na liście uprawnionych."))

@app.route('/student_status')
def student_status():
    check_ip_permission()
    client_ip = request.remote_addr
    
    with get_db() as conn:
        lesson_started = conn.execute("SELECT value FROM lesson_config WHERE key = 'lesson_started'").fetchone()['value'] == '1'
        submissions_allowed = conn.execute("SELECT value FROM lesson_config WHERE key = 'submissions_allowed'").fetchone()['value'] == '1'
        student = conn.execute("SELECT * FROM student_state WHERE ip = ?", (client_ip,)).fetchone()
        
        if not student:
            return jsonify({"task_id": "lock", "task_text": "Brak rejestracji stanowiska.", "progress": False})
            
        if not lesson_started:
            return jsonify({
                "task_id": "lock",
                "task_text": "Oczekiwanie na rozpoczęcie lekcji przez nauczyciela...",
                "progress": False,
                "rejection_msg": "",
                "code": ""
            })
            
        task_step = student['current_step']
        task_map_str = student['task_map']
        
        if task_map_str:
            task_ids = [int(x) for x in task_map_str.split(',')]
            
            if task_step < len(task_ids):
                actual_task_id = task_ids[task_step]
                task_row = conn.execute("SELECT task_text FROM tasks WHERE id = ?", (actual_task_id,)).fetchone()
                return jsonify({
                    "task_id": student['task_uuid'],
                    "task_text": task_row['task_text'] if task_row else "Błąd: Zadanie usunięte.",
                    "progress": bool(student['progress']),
                    "rejection_msg": student['rejection_message'],
                    "code": student['submitted_code'],
                    "submissions_allowed": submissions_allowed
                })
            else:
                return jsonify({
                    "task_id": "finished",
                    "task_text": "Wszystkie zadania wykonane! Możesz odpocząć.",
                    "progress": False,
                    "submissions_allowed": False
                })
        
        return jsonify({"task_id": "lock", "task_text": "Brak przydzielonych zadań.", "progress": False})

@app.route('/start_lesson', methods=['POST'])
def start_lesson():
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    
    req_data = request.json if request.is_json else {}
    should_shuffle = req_data.get('shuffle', False)
    selected_tag = req_data.get('tag', '').strip()
    
    with get_db() as conn:
        lesson_already_started = conn.execute("SELECT value FROM lesson_config WHERE key = 'lesson_started'").fetchone()['value'] == '1'
        
        if lesson_already_started:
            conn.execute("UPDATE lesson_config SET value = '1' WHERE key = 'submissions_allowed'")
            conn.commit()
            return jsonify({"success": True})

        if selected_tag:
            cursor = conn.execute('''
                SELECT t.id FROM tasks t
                JOIN task_tags tt ON t.id = tt.task_id
                JOIN tags tg ON tt.tag_id = tg.id
                WHERE tg.tag_name = ?
                ORDER BY t.id ASC
            ''', (selected_tag,))
        else:
            cursor = conn.execute("SELECT id FROM tasks ORDER BY id ASC")
            
        task_ids = [row['id'] for row in cursor.fetchall()]
        
        if not task_ids:
            return jsonify({"success": False, "message": f"Brak zadań przypisanych do tagu: '{selected_tag}'"}), 400
            
        conn.execute("UPDATE lesson_config SET value = '1' WHERE key = 'lesson_started'")
        conn.execute("UPDATE lesson_config SET value = '1' WHERE key = 'submissions_allowed'")
        
        # Pętla aktualizująca tylko uczniów, którzy są fizycznie w bazie
        active_students = conn.execute("SELECT ip FROM student_state").fetchall()
        
        for st in active_students:
            ip = st['ip']
            current_set = list(task_ids)
            if should_shuffle:
                random.shuffle(current_set)
            
            student_task_map = ",".join(map(str, current_set))
            
            conn.execute('''
                UPDATE student_state 
                SET task_map = ?, current_step = 0, task_uuid = ?, progress = 0, rejection_message = ''
                WHERE ip = ?
            ''', (student_task_map, str(uuid.uuid4()), ip))
            
            # Zapisanie mapy, by opóźnieni uczniowie mogli ją pobrać
            conn.execute("INSERT OR REPLACE INTO lesson_config (key, value) VALUES ('active_task_map', ?)", (student_task_map,))
            
    return jsonify({"success": True, "total_tasks": len(task_ids)})

@app.route('/stop_lesson', methods=['POST'])
def stop_lesson():
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    with get_db() as conn:
        conn.execute("UPDATE lesson_config SET value = '0' WHERE key = 'submissions_allowed'")
        conn.commit()
    return jsonify({"success": True})

@app.route('/done', methods=['POST'])
def mark_done():
    check_ip_permission()
    client_ip = request.remote_addr
    code_submission = request.form.get('code', '').strip()
    
    with get_db() as conn:
        lesson_started = conn.execute("SELECT value FROM lesson_config WHERE key = 'lesson_started'").fetchone()['value'] == '1'
        submissions_allowed = conn.execute("SELECT value FROM lesson_config WHERE key = 'submissions_allowed'").fetchone()['value'] == '1'
        
        if not lesson_started: abort(400)
        if not submissions_allowed: abort(403)
        
        conn.execute('''
            UPDATE student_state 
            SET progress = 1, help_requested = 0, submitted_code = ?, rejection_message = '' 
            WHERE ip = ?
        ''', (code_submission, client_ip))
        
    return "OK", 200

@app.route('/need_help', methods=['POST'])
def need_help():
    check_ip_permission()
    client_ip = request.remote_addr
    
    with get_db() as conn:
        lesson_started = conn.execute("SELECT value FROM lesson_config WHERE key = 'lesson_started'").fetchone()['value'] == '1'
        if not lesson_started: abort(400)
        
        conn.execute('''
            UPDATE student_state 
            SET help_requested = NOT help_requested 
            WHERE ip = ?
        ''', (client_ip,))
        
        status = conn.execute("SELECT help_requested FROM student_state WHERE ip = ?", (client_ip,)).fetchone()['help_requested']
        
    return jsonify({"is_helping": bool(status)}), 200

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
    
    with get_db() as conn:
        all_tags = conn.execute("SELECT tag_name FROM tags ORDER BY tag_name ASC").fetchall()
        
        students_list = conn.execute("SELECT ip, student_name FROM student_state ORDER BY student_name").fetchall()
        students_dict = {row['ip']: row['student_name'] for row in students_list}

    return render_template('teacher.html', students=students_dict, tags=all_tags)

@app.route('/status')
def get_status():
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    
    with get_db() as conn:
        lesson_started = conn.execute("SELECT value FROM lesson_config WHERE key = 'lesson_started'").fetchone()['value'] == '1'
        submissions_allowed = conn.execute("SELECT value FROM lesson_config WHERE key = 'submissions_allowed'").fetchone()['value'] == '1'
        students_data = conn.execute("SELECT * FROM student_state").fetchall()
        
    progress_dict = {}
    help_dict = {}
    task_numbers = {}
    names_dict = {}
    codes_dict = {}
    
    dynamic_total_tasks = 0
    
    for row in students_data:
        ip = row['ip']
        progress_dict[ip] = bool(row['progress'])
        help_dict[ip] = bool(row['help_requested'])
        task_numbers[ip] = row['current_step'] + 1
        names_dict[ip] = row['student_name']
        codes_dict[ip] = row['submitted_code']
        
        if row['task_map'] and dynamic_total_tasks == 0:
            dynamic_total_tasks = len([x for x in row['task_map'].split(',') if x.strip()])
            
    if dynamic_total_tasks == 0:
        dynamic_total_tasks = 1

    return jsonify({
        "lesson_started": lesson_started,
        "submissions_allowed": submissions_allowed,
        "progress": progress_dict,
        "help": help_dict,
        "task_numbers": task_numbers,
        "names": names_dict,
        "codes": codes_dict,
        "total_tasks": dynamic_total_tasks
    })

@app.route('/accept_task', methods=['POST'])
def accept_task():
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    student_ip = request.form.get('ip')
    
    with get_db() as conn:
        student = conn.execute("SELECT * FROM student_state WHERE ip = ?", (student_ip,)).fetchone()
        if not student: return jsonify({"success": False, "message": "Niepoprawne IP"})
        
        task_map_str = student['task_map']
        task_ids = [int(x) for x in task_map_str.split(',')] if task_map_str else []
        current_idx = student['current_step']
        
        if current_idx < len(task_ids):
            actual_task_id = task_ids[current_idx]
            
            task_row = conn.execute("SELECT task_text FROM tasks WHERE id = ?", (actual_task_id,)).fetchone()
            task_text = task_row['task_text'] if task_row else "Nieznane zadanie"
            
            conn.execute('''
                INSERT INTO submitted_solutions_history (student_name, ip, task_id, task_text, accepted_code, submitted_at)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                student['student_name'],
                student_ip,
                actual_task_id,
                task_text,
                student['submitted_code'],
                datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            ))
            
            conn.execute('''
                UPDATE student_state 
                SET current_step = current_step + 1, task_uuid = ?, progress = 0, 
                    help_requested = 0, submitted_code = '', rejection_message = '' 
                WHERE ip = ?
            ''', (str(uuid.uuid4()), student_ip))
            
            return jsonify({"success": True})
            
        return jsonify({"success": False, "message": "Uczeń zakończył już cały dostępny kurs."})

@app.route('/reject_task', methods=['POST'])
def reject_task():
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    
    student_ip = request.form.get('ip')
    reason = request.form.get('reason', '').strip()
    edited_code = request.form.get('code', '')
    
    msg = reason if reason else "Twój kod wymaga poprawek."
    
    with get_db() as conn:
        if edited_code:
            conn.execute('''
                UPDATE student_state 
                SET progress = 0, rejection_message = ?, submitted_code = ? 
                WHERE ip = ?
            ''', (msg, edited_code, student_ip))
        else:
            conn.execute('''
                UPDATE student_state 
                SET progress = 0, rejection_message = ? 
                WHERE ip = ?
            ''', (msg, student_ip))
            
    return jsonify({"success": True})

@app.route('/restart_tasks', methods=['POST'])
def restart_tasks():
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    
    with get_db() as conn:
        conn.execute("UPDATE lesson_config SET value = '0' WHERE key = 'lesson_started'")
        conn.execute("UPDATE lesson_config SET value = '1' WHERE key = 'submissions_allowed'")
        conn.execute("INSERT OR REPLACE INTO lesson_config (key, value) VALUES ('active_task_map', '')")
        conn.execute('''
            UPDATE student_state 
            SET current_step = 0, task_uuid = ?, progress = 0, help_requested = 0, 
                submitted_code = '', rejection_message = '', task_map = ''
        ''', (str(uuid.uuid4()),))
        
    return jsonify({"success": True})


# ==========================================
# SEKCJA ADMINISTRACYJNA - ZARZĄDZANIE UCZNIAMI
# ==========================================

@app.route('/admin/users')
def admin_users():
    check_ip_permission()
    if not is_teacher_logged_in(): return redirect(url_for('login'))
    
    with get_db() as conn:
        all_users = conn.execute("SELECT id, full_name, alias FROM allowed_users ORDER BY full_name ASC").fetchall()
        
    return render_template('admin_users.html', users=all_users)

@app.route('/admin/add_user', methods=['POST'])
def admin_add_user():
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    
    user_id = request.form.get('user_id', '').strip()
    full_name = request.form.get('full_name', '').strip()
    alias = request.form.get('alias', '').strip()
    if not alias: alias = None
    
    if not full_name:
        return redirect(url_for('admin_users'))
        
    with get_db() as conn:
        if user_id:
            conn.execute('''
                UPDATE allowed_users 
                SET full_name = ?, alias = ? 
                WHERE id = ?
            ''', (full_name, alias, user_id))
        else:
            conn.execute('''
                INSERT INTO allowed_users (full_name, alias) 
                VALUES (?, ?)
            ''', (full_name, alias))
            
    return redirect(url_for('admin_users'))

@app.route('/admin/delete_user/<int:user_id>', methods=['POST'])
def admin_delete_user(user_id):
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    
    with get_db() as conn:
        conn.execute("DELETE FROM allowed_users WHERE id = ?", (user_id,))
        
    return redirect(url_for('admin_users'))


# ==========================================
# SEKCJA ADMINISTRACYJNA - BANK ZADAŃ I TAGÓW
# ==========================================

@app.route('/admin/tasks')
def admin_tasks():
    check_ip_permission()
    if not is_teacher_logged_in(): return redirect(url_for('login'))
    
    with get_db() as conn:
        query = '''
            SELECT t.id, t.task_text, GROUP_CONCAT(tg.tag_name) as tag_list
            FROM tasks t
            LEFT JOIN task_tags tt ON t.id = tt.task_id
            LEFT JOIN tags tg ON tt.tag_id = tg.id
            GROUP BY t.id
            ORDER BY t.id DESC
        '''
        all_tasks = conn.execute(query).fetchall()
        
    return render_template('admin_tasks.html', tasks=all_tasks)

@app.route('/admin/add_task', methods=['POST'])
def admin_add_task():
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    
    task_text = request.form.get('task_text', '').strip()
    raw_tags = request.form.get('tags', '').strip()
    
    if not task_text:
        return redirect(url_for('admin_tasks'))
        
    with get_db() as conn:
        cursor = conn.execute("INSERT INTO tasks (task_text) VALUES (?)", (task_text,))
        new_task_id = cursor.lastrowid
        
        if raw_tags:
            tag_names = list(set([t.strip().lower() for t in raw_tags.split(',') if t.strip()]))
            
            for name in tag_names:
                conn.execute("INSERT OR IGNORE INTO tags (tag_name) VALUES (?)", (name,))
                tag_row = conn.execute("SELECT id FROM tags WHERE tag_name = ?", (name,)).fetchone()
                if tag_row:
                    conn.execute("INSERT OR IGNORE INTO task_tags (task_id, tag_id) VALUES (?, ?)", 
                                 (new_task_id, tag_row['id']))
                                 
    return redirect(url_for('admin_tasks'))

@app.route('/admin/delete_task/<int:task_id>', methods=['POST'])
def admin_delete_task(task_id):
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    
    with get_db() as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        conn.execute('DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM task_tags)')
        
    return redirect(url_for('admin_tasks'))


# ==========================================
# SEKCJA ADMINISTRACYJNA - ARCHIWUM ROZWIĄZAŃ
# ==========================================

@app.route('/admin/history')
def admin_history():
    check_ip_permission()
    if not is_teacher_logged_in(): return redirect(url_for('login'))
    
    with get_db() as conn:
        query = '''
            SELECT DISTINCT student_name 
            FROM submitted_solutions_history 
            ORDER BY student_name ASC
        '''
        all_students = conn.execute(query).fetchall()
        
    return render_template('admin_history.html', students=all_students)

@app.route('/admin/get_history')
def admin_get_history():
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    
    student_name = request.args.get('name', '').strip()
    if not student_name:
        return jsonify([])
        
    with get_db() as conn:
        query = '''
            SELECT task_id, task_text, accepted_code, ip, submitted_at 
            FROM submitted_solutions_history 
            WHERE student_name = ? 
            ORDER BY id DESC
        '''
        cursor = conn.execute(query, (student_name,))
        
        history_list = []
        for row in cursor.fetchall():
            history_list.append({
                "task_id": row["task_id"],
                "task_text": row["task_text"],
                "accepted_code": row["accepted_code"],
                "ip": row["ip"],
                "submitted_at": row["submitted_at"]
            })
            
    return jsonify(history_list)


# ==========================================
# SEKCJA ADMINISTRACYJNA - HISTORIA LEKCJI
# ==========================================

@app.route('/admin/lessons')
def admin_lessons():
    check_ip_permission()
    if not is_teacher_logged_in(): return redirect(url_for('login'))
    
    with get_db() as conn:
        lesson_started = conn.execute("SELECT value FROM lesson_config WHERE key = 'lesson_started'").fetchone()['value'] == '1'
        submissions_allowed = conn.execute("SELECT value FROM lesson_config WHERE key = 'submissions_allowed'").fetchone()['value'] == '1'
        if lesson_started and submissions_allowed:
            abort(403)

        all_lessons = conn.execute("SELECT * FROM lesson_history ORDER BY id DESC").fetchall()
        
    return render_template('admin_lessons.html', lessons=all_lessons)

@app.route('/admin/save_lesson', methods=['POST'])
def admin_save_lesson():
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    
    lesson_name = request.form.get('lesson_name', '').strip()
    if not lesson_name:
        return redirect(url_for('admin_lessons'))
        
    with get_db() as conn:
        cursor = conn.execute("INSERT INTO lesson_history (name) VALUES (?)", (lesson_name,))
        lesson_id = cursor.lastrowid
        
        students_state = conn.execute("SELECT * FROM student_state").fetchall()
        
        for s in students_state:
            conn.execute('''
                INSERT INTO lesson_history_states 
                (lesson_id, ip, student_name, current_step, task_uuid, progress, help_requested, submitted_code, rejection_message, task_map)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                lesson_id, s['ip'], s['student_name'], s['current_step'], s['task_uuid'],
                s['progress'], s['help_requested'], s['submitted_code'], s['rejection_message'], s['task_map']
            ))
            
    return redirect(url_for('admin_lessons'))

@app.route('/admin/load_lesson/<int:lesson_id>', methods=['POST'])
def admin_load_lesson(lesson_id):
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    
    with get_db() as conn:
        lesson_started = conn.execute("SELECT value FROM lesson_config WHERE key = 'lesson_started'").fetchone()['value'] == '1'
        submissions_allowed = conn.execute("SELECT value FROM lesson_config WHERE key = 'submissions_allowed'").fetchone()['value'] == '1'
        if lesson_started and submissions_allowed:
            abort(403)
            
        saved_states = conn.execute("SELECT * FROM lesson_history_states WHERE lesson_id = ?", (lesson_id,)).fetchall()
        if not saved_states:
            return redirect(url_for('admin_lessons'))
            
        conn.execute("DELETE FROM student_state")
        
        for s in saved_states:
            conn.execute('''
                INSERT INTO student_state 
                (ip, student_name, current_step, task_uuid, progress, help_requested, submitted_code, rejection_message, task_map)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                s['ip'], s['student_name'], s['current_step'], s['task_uuid'],
                s['progress'], s['help_requested'], s['submitted_code'], s['rejection_message'], s['task_map']
            ))
            
        conn.execute("UPDATE lesson_config SET value = '1' WHERE key = 'lesson_started'")
        conn.execute("UPDATE lesson_config SET value = '0' WHERE key = 'submissions_allowed'")
        conn.commit()
        
    return redirect(url_for('teacher_view'))

@app.route('/admin/delete_lesson/<int:lesson_id>', methods=['POST'])
def admin_delete_lesson(lesson_id):
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    
    with get_db() as conn:
        conn.execute("PRAGMA foreign_keys = ON;")
        conn.execute("DELETE FROM lesson_history WHERE id = ?", (lesson_id,))
        
    return redirect(url_for('admin_lessons'))

init_db()

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
