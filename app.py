import os
import sqlite3
from flask import Flask, render_template, request, jsonify, abort, session, redirect, url_for

app = Flask(__name__)
app.secret_key = "super_tajny_klucz_sieciowy_do_sesji"
DB_PATH = "classroom.db"

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def check_ip_permission():
    pass

def is_teacher_logged_in():
    return session.get("teacher_logged") is True

@app.route('/')
def index():
    return redirect(url_for('student_view'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        password = request.form.get('password')
        if password == "nauczyciel123":
            session["teacher_logged"] = True
            return redirect(url_for('teacher_view'))
        return "Błędne hasło!", 403
    return '''
        <form method="post" style="margin:50px; font-family:sans-serif;">
            <h2>Logowanie do Panelu Nauczyciela</h2>
            <input type="password" name="password" placeholder="Hasło" required style="padding:8px;"><br><br>
            <button type="submit" style="padding:8px 15px;">Zaloguj</button>
        </form>
    '''

@app.route('/logout')
def logout():
    session.pop("teacher_logged", None)
    return redirect(url_for('login'))

@app.route('/student')
def student_view():
    ip = request.remote_addr
    with get_db() as conn:
        student = conn.execute("SELECT * FROM student_state WHERE ip = ?", (ip,)).fetchone()
        lesson_started = conn.execute("SELECT value FROM lesson_config WHERE key = 'lesson_started'").fetchone()['value'] == '1'
    
    if not student:
        return '''
            <form action="/register" method="post" style="margin:50px; font-family:sans-serif;">
                <h2>Rejestracja Stanowiska Ucznia</h2>
                <p>Twój adres IP: <strong>{}</strong></p>
                <input type="text" name="student_name" placeholder="Imię i Nazwisko" required style="padding:8px; width:250px;"><br><br>
                <button type="submit" style="padding:8px 15px;">Wejdź do lekcji</button>
            </form>
        '''.format(ip)

    if not lesson_started:
        return render_template("student.html", name=student['student_name'], station=f"IP: {ip}", task="Lekcja jeszcze się nie rozpoczęła. Poczekaj na nauczyciela.", task_id="lock", rejection_msg="")

    task_map = [x for x in student['task_map'].split(',') if x.strip()]
    current_step = student['current_step']

    if current_step >= len(task_map):
        return render_template("student.html", name=student['student_name'], station=f"IP: {ip}", task="Gratulacje! Wszystkie zadania na tę lekcję zostały ukończone i zaliczone.", task_id="finished", rejection_msg="")

    task_id = task_map[current_step]
    with get_db() as conn:
        task_data = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()

    return render_template("student.html", 
                           name=student['student_name'], 
                           station=f"IP: {ip}", 
                           task=task_data['task_text'] if task_data else "Brak treści zadania", 
                           task_id=task_id, 
                           rejection_msg=student['rejection_msg'])

@app.route('/register', methods=['POST'])
def register_student():
    ip = request.remote_addr
    name = request.form.get('student_name', '').strip()
    if not name: return "Imię nie może być puste", 400
    
    with get_db() as conn:
        lesson_started = conn.execute("SELECT value FROM lesson_config WHERE key = 'lesson_started'").fetchone()['value'] == '1'
        active_map_row = conn.execute("SELECT value FROM lesson_config WHERE key = 'active_task_map'").fetchone()
        active_map = active_map_row['value'] if (lesson_started and active_map_row) else ""

        exists = conn.execute("SELECT 1 FROM student_state WHERE ip = ?", (ip,)).fetchone()
        if exists:
            conn.execute("UPDATE student_state SET student_name = ?, task_map = ? WHERE ip = ?", (name, active_map, ip))
        else:
            conn.execute("INSERT INTO student_state (ip, student_name, current_step, task_map, progress, help_requested, submitted_code, rejection_msg) VALUES (?, ?, 0, ?, 0, 0, '', '')", (ip, name, active_map))
        conn.commit()
    return redirect(url_for('student_view'))

@app.route('/student_status')
def student_status():
    ip = request.remote_addr
    with get_db() as conn:
        lesson_started = conn.execute("SELECT value FROM lesson_config WHERE key = 'lesson_started'").fetchone()['value'] == '1'
        submissions_allowed = conn.execute("SELECT value FROM lesson_config WHERE key = 'submissions_allowed'").fetchone()['value'] == '1'
        student = conn.execute("SELECT * FROM student_state WHERE ip = ?", (ip,)).fetchone()

    if not student:
        return jsonify({"task_id": "lock", "task_text": "Brak rejestracji stanowiska."})

    if not lesson_started:
        return jsonify({
            "task_id": "lock",
            "task_text": "Lekcja została zatrzymana lub nie została jeszcze uruchomiona.",
            "submissions_allowed": False
        })

    task_map = [x for x in student['task_map'].split(',') if x.strip()]
    current_step = student['current_step']

    if current_step >= len(task_map):
        return jsonify({
            "task_id": "finished",
            "task_text": "Gratulacje! Wszystkie zadania na tę lekcję zostały ukończone i zaliczone.",
            "submissions_allowed": False
        })

    task_id = task_map[current_step]
    with get_db() as conn:
        task_data = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()

    return jsonify({
        "task_id": task_id,
        "task_text": task_data['task_text'] if task_data else "Brak treści zadania",
        "progress": bool(student['progress']),
        "rejection_msg": student['rejection_msg'],
        "code": student['submitted_code'],
        "submissions_allowed": submissions_allowed
    })

@app.route('/done', methods=['POST'])
def student_submit():
    ip = request.remote_addr
    code = request.form.get('code', '')
    
    with get_db() as conn:
        submissions_allowed = conn.execute("SELECT value FROM lesson_config WHERE key = 'submissions_allowed'").fetchone()['value'] == '1'
        if not submissions_allowed:
            return "Przyjmowanie rozwiązań jest zablokowane!", 403
            
        conn.execute("UPDATE student_state SET submitted_code = ?, progress = 1, help_requested = 0, rejection_msg = '' WHERE ip = ?", (code, ip))
        conn.commit()
    return jsonify({"status": "submitted"})

@app.route('/need_help', methods=['POST'])
def student_help():
    ip = request.remote_addr
    with get_db() as conn:
        current = conn.execute("SELECT help_requested FROM student_state WHERE ip = ?", (ip,)).fetchone()
        if current:
            new_state = 0 if current['help_requested'] else 1
            conn.execute("UPDATE student_state SET help_requested = ? WHERE ip = ?", (new_state, ip))
            conn.commit()
            return jsonify({"is_helping": bool(new_state)})
    return jsonify({"is_helping": False})

@app.route('/teacher')
def teacher_view():
    if not is_teacher_logged_in(): return redirect(url_for('login'))
    
    with get_db() as conn:
        students_list = conn.execute("SELECT ip, student_name FROM student_state ORDER BY student_name").fetchall()
        tags_list = conn.execute("SELECT DISTINCT tag_name FROM task_tags ORDER BY tag_name").fetchall()
        total_tasks = conn.execute("SELECT COUNT(*) FROM tasks").fetchone()[0]

    students_dict = {row['ip']: row['student_name'] for row in students_list}
    return render_template("teacher.html", students=students_dict, tags=tags_list, total_tasks=total_tasks)

@app.route('/status')
def get_status():
    check_ip_permission()
    if not is_teacher_logged_in(): abort(401)
    
    with get_db() as conn:
        lesson_started = conn.execute("SELECT value FROM lesson_config WHERE key = 'lesson_started'").fetchone()['value'] == '1'
        submissions_allowed = conn.execute("SELECT value FROM lesson_config WHERE key = 'submissions_allowed'").fetchone()['value'] == '1'
        current_total_row = conn.execute("SELECT value FROM lesson_config WHERE key = 'current_total_tasks'").fetchone()
        dynamic_total_tasks = int(current_total_row['value']) if current_total_row else 1
        students_data = conn.execute("SELECT * FROM student_state").fetchall()
        
    progress_dict = {}
    help_dict = {}
    task_numbers = {}
    names_dict = {}
    codes_dict = {}
    
    for row in students_data:
        ip = row['ip']
        progress_dict[ip] = bool(row['progress'])
        help_dict[ip] = bool(row['help_requested'])
        task_numbers[ip] = row['current_step'] + 1
        names_dict[ip] = row['student_name']
        codes_dict[ip] = row['submitted_code']

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

@app.route('/start_lesson', methods=['POST'])
def start_lesson():
    if not is_teacher_logged_in(): abort(401)
    tag = request.form.get('tag', '').strip()
    shuffle_mode = request.form.get('shuffle', 'false') == 'true'
    
    with get_db() as conn:
        if tag:
            query = "SELECT id FROM tasks WHERE id IN (SELECT task_id FROM task_tags WHERE tag_name = ?) ORDER BY id"
            tasks_rows = conn.execute(query, (tag,)).fetchall()
        else:
            tasks_rows = conn.execute("SELECT id FROM tasks ORDER BY id").fetchall()
            
        task_ids = [str(r['id']) for r in tasks_rows]
        
        if not task_ids:
            return jsonify({"status": "error", "message": "Brak zadań dla wybranego kryterium!"}), 400
            
        if shuffle_mode:
            import random
            random.shuffle(task_ids)
            
        map_str = ",".join(task_ids)
        
        conn.execute("UPDATE student_state SET task_map = ?, current_step = 0, progress = 0, help_requested = 0, submitted_code = '', rejection_msg = ''")
        conn.execute("UPDATE lesson_config SET value = '1' WHERE key = 'lesson_started'")
        conn.execute("UPDATE lesson_config SET value = '1' WHERE key = 'submissions_allowed'")
        conn.execute("INSERT OR REPLACE INTO lesson_config (key, value) VALUES ('current_total_tasks', ?)", (str(len(task_ids)),))
        conn.execute("INSERT OR REPLACE INTO lesson_config (key, value) VALUES ('active_task_map', ?)", (map_str,))
        conn.commit()
        
    return jsonify({"status": "started", "total_tasks": len(task_ids)})

@app.route('/stop_lesson', methods=['POST'])
def stop_lesson():
    if not is_teacher_logged_in(): abort(401)
    with get_db() as conn:
        conn.execute("UPDATE lesson_config SET value = '0' WHERE key = 'submissions_allowed'")
        conn.commit()
    return jsonify({"status": "stopped"})

@app.route('/restart_all', methods=['POST'])
def restart_all():
    if not is_teacher_logged_in(): abort(401)
    with get_db() as conn:
        conn.execute("UPDATE student_state SET task_map = '', current_step = 0, progress = 0, help_requested = 0, submitted_code = '', rejection_msg = ''")
        conn.execute("UPDATE lesson_config SET value = '0' WHERE key = 'lesson_started'")
        conn.execute("UPDATE lesson_config SET value = '0' WHERE key = 'submissions_allowed'")
        conn.execute("INSERT OR REPLACE INTO lesson_config (key, value) VALUES ('current_total_tasks', '1')")
        conn.execute("INSERT OR REPLACE INTO lesson_config (key, value) VALUES ('active_task_map', '')")
        conn.commit()
    return jsonify({"status": "reset"})

@app.route('/accept', methods=['POST'])
def accept():
    if not is_teacher_logged_in(): abort(401)
    student_ip = request.form.get('ip')
    
    with get_db() as conn:
        student = conn.execute("SELECT current_step, task_map FROM student_state WHERE ip = ?", (student_ip,)).fetchone()
        if student:
            new_step = student['current_step'] + 1
            conn.execute("UPDATE student_state SET current_step = ?, progress = 0, help_requested = 0, rejection_msg = '' WHERE ip = ?", (new_step, student_ip))
            conn.commit()
    return jsonify({"status": "accepted"})

@app.route('/reject', methods=['POST'])
def reject():
    if not is_teacher_logged_in(): abort(401)
    student_ip = request.form.get('ip')
    msg = request.form.get('msg', '').strip()
    
    with get_db() as conn:
        conn.execute("UPDATE student_state SET progress = 0, help_requested = 0, rejection_msg = ? WHERE ip = ?", (msg, student_ip))
        conn.commit()
    return jsonify({"status": "rejected"})

if __name__ == '__main__':
    if not os.path.exists(DB_PATH):
        db = sqlite3.connect(DB_PATH)
        db.execute("CREATE TABLE lesson_config (key TEXT PRIMARY KEY, value TEXT)")
        db.execute("INSERT INTO lesson_config VALUES ('lesson_started', '0'), ('submissions_allowed', '0'), ('current_total_tasks', '1'), ('active_task_map', '')")
        db.execute("CREATE TABLE tasks (id INTEGER PRIMARY KEY AUTOINCREMENT, task_text TEXT)")
        db.execute("INSERT INTO tasks (task_text) VALUES ('Zadanie 1: Napisz program wyświetlający napis Hello World.'), ('Zadanie 2: Oblicz sumę liczb od 1 do 10.'), ('Zadanie 3: Stwórz listę kwadratów liczb parzystych.')")
        db.execute("CREATE TABLE task_tags (task_id INTEGER, tag_name TEXT)")
        db.execute("INSERT INTO task_tags VALUES (1, 'Podstawy'), (2, 'Pętle'), (3, 'Zaawansowane')")
        db.execute("CREATE TABLE student_state (ip TEXT PRIMARY KEY, student_name TEXT, current_step INTEGER, task_map TEXT, progress INTEGER, help_requested INTEGER, submitted_code TEXT, rejection_msg TEXT)")
        db.commit()
        db.close()
        
    app.run(host='0.0.0.0', port=5000, debug=True)
