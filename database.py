import sqlite3
import json
from datetime import datetime

DB_FILE = "math_tutor.db"


def init_db():
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()

  # Students table
  cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            current_topic_id TEXT DEFAULT 'L1_NUMBERS',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_active TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')

  # Topic Mastery table
  cursor.execute('''
        CREATE TABLE IF NOT EXISTS progress (
            student_id INTEGER,
            topic_id TEXT,
            mastery_score INTEGER DEFAULT 0,
            consecutive_errors INTEGER DEFAULT 0,
            PRIMARY KEY (student_id, topic_id),
            FOREIGN KEY (student_id) REFERENCES students (id)
        )
    ''')

  # Chat History table
  cursor.execute('''
        CREATE TABLE IF NOT EXISTS chat_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER,
            role TEXT,
            message TEXT,
            visual_type TEXT DEFAULT 'none',
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES students (id)
        )
    ''')

  conn.commit()
  conn.close()


def get_or_create_student(name):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()

  cursor.execute("SELECT id, name, current_topic_id FROM students WHERE name = ?", (name,))
  row = cursor.fetchone()

  if row:
    student = {"id": row[0], "name": row[1], "current_topic_id": row[2]}
    cursor.execute("UPDATE students SET last_active = ? WHERE id = ?", (datetime.now(), student["id"]))
    conn.commit()
  else:
    cursor.execute("INSERT INTO students (name) VALUES (?)", (name,))
    student_id = cursor.lastrowid

    # Initialize default topic levels for new student
    topics = ['L1_NUMBERS', 'L2_FRACTIONS', 'L3_OPERATIONS', 'L4_EQUATIONS', 'L5_ALGEBRA']
    for t in topics:
      cursor.execute("INSERT INTO progress (student_id, topic_id, mastery_score) VALUES (?, ?, 0)", (student_id, t))

    conn.commit()
    student = {"id": student_id, "name": name, "current_topic_id": "L1_NUMBERS"}

  conn.close()
  return student


def get_student_list():
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("SELECT name FROM students ORDER BY last_active DESC")
  names = [row[0] for row in cursor.fetchall()]
  conn.close()
  return names


def get_student_progress(student_id, topic_id):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("SELECT mastery_score, consecutive_errors FROM progress WHERE student_id = ? AND topic_id = ?",
                 (student_id, topic_id))
  row = cursor.fetchone()
  conn.close()
  if row:
    return {"mastery_score": row[0], "consecutive_errors": row[1]}
  return {"mastery_score": 0, "consecutive_errors": 0}


def update_progress(student_id, topic_id, is_correct):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()

  prog = get_student_progress(student_id, topic_id)
  mastery = prog["mastery_score"]
  errors = prog["consecutive_errors"]

  if is_correct:
    mastery = min(100, mastery + 15)
    errors = 0
  else:
    errors += 1
    mastery = max(0, mastery - 5)

  cursor.execute('''
        INSERT INTO progress (student_id, topic_id, mastery_score, consecutive_errors)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(student_id, topic_id) DO UPDATE SET
            mastery_score = excluded.mastery_score,
            consecutive_errors = excluded.consecutive_errors
    ''', (student_id, topic_id, mastery, errors))

  conn.commit()
  conn.close()
  return {"mastery_score": mastery, "consecutive_errors": errors}


def evaluate_readiness(student_id):
  """Calculates overall readiness status for Grade 9 / Algebra 1."""
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("SELECT topic_id, mastery_score FROM progress WHERE student_id = ?", (student_id,))
  rows = cursor.fetchall()
  conn.close()

  mastery_dict = {row[0]: row[1] for row in rows}

  # Prerequisite topics needed for Grade 9 readiness
  prereqs = {
    "L1_NUMBERS": "Integer Rules",
    "L2_FRACTIONS": "Visual Fractions",
    "L3_OPERATIONS": "Order of Operations",
    "L4_EQUATIONS": "Linear Equations & Variable Balancing"
  }

  mastered_skills = []
  for topic_code, label in prereqs.items():
    if mastery_dict.get(topic_code, 0) >= 80:
      mastered_skills.append(label)

  total_prereqs = len(prereqs)
  readiness_percentage = int((len(mastered_skills) / total_prereqs) * 100)

  is_unlocked = readiness_percentage >= 100

  return {
    "readiness_percentage": readiness_percentage,
    "is_unlocked": is_unlocked,
    "mastered_skills": mastered_skills,
    "target_grade": "Grade 9 / Algebra 1"
  }


def save_chat(student_id, role, message, visual_type='none'):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("INSERT INTO chat_history (student_id, role, message, visual_type) VALUES (?, ?, ?, ?)",
                 (student_id, role, message, visual_type))
  conn.commit()
  conn.close()


def load_chat_history(student_id):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("SELECT role, message, visual_type FROM chat_history WHERE student_id = ? ORDER BY id ASC",
                 (student_id,))
  rows = cursor.fetchall()
  conn.close()
  return [{"role": r[0], "message": r[1], "visual_type": r[2]} for r in rows]