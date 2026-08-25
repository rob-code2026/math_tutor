import sqlite3

DB_FILE = "math_tutor.db"

CURRICULUM_TREE = {
    "L1": {
        "title": "Level 1: Basic Arithmetic & Foundations",
        "subtopics": {
            "L1_1": "Integer Operations",
            "L1_2": "Fractions & Decimals",
            "L1_3": "Order of Operations (PEMDAS)",
        },
    },
    "L2": {
        "title": "Level 2: Introductory Algebra",
        "subtopics": {
            "L2_1": "Linear Equations in One Variable",
            "L2_2": "Evaluating Algebraic Expressions",
            "L2_3": "Basic Inequalities",
        },
    },
    "L3": {
        "title": "Level 3: Polynomials & Factoring",
        "subtopics": {
            "L3_1": "Expanding Expressions & Distributive Law",
            "L3_2": "Factoring Quadratic Polynomials",
            "L3_3": "Simplifying Algebraic Fractions",
        },
    },
    "L4": {
        "title": "Level 4: Exponents & Radicals",
        "subtopics": {
            "L4_1": "Exponent Rules & Scientific Notation",
            "L4_2": "Simplifying Radical Expressions",
            "L4_3": "Fractional Exponents",
        },
    },
    "L5": {
        "title": "Level 5: Functions & Graphs",
        "subtopics": {
            "L5_1": "Linear Functions & Slope-Intercept Form",
            "L5_2": "Quadratic Functions & Parabolas",
            "L5_3": "Domain and Range Analysis",
        },
    },
    "L6": {
        "title": "Level 6: Systems of Equations & Inequalities",
        "subtopics": {
            "L6_1": "Solving Systems by Substitution",
            "L6_2": "Solving Systems by Elimination",
            "L6_3": "Systems of Linear Inequalities",
        },
    },
    "L7": {
        "title": "Level 7: Trigonometry",
        "subtopics": {
            "L7_1": "Right Triangle Trigonometry (Sine, Cosine, Tangent)",
            "L7_2": "The Unit Circle & Radian Measure",
            "L7_3": "Trigonometric Identities",
        },
    },
    "L8": {
        "title": "Level 8: Exponential & Logarithmic Functions",
        "subtopics": {
            "L8_1": "Logarithm Rules & Properties",
            "L8_2": "Exponential Equations",
            "L8_3": "Logarithmic Equations",
        },
    },
    "L9": {
        "title": "Level 9: Differential Calculus",
        "subtopics": {
            "L9_1": "Limits & Continuity",
            "L9_2": "Power Rule & Basic Derivatives",
            "L9_3": "Product, Quotient, and Chain Rules",
        },
    },
    "L10": {
        "title": "Level 10: Integral Calculus",
        "subtopics": {
            "L10_1": "Antiderivatives & Indefinite Integrals",
            "L10_2": "Definite Integrals & Fundamental Theorem of Calculus",
            "L10_3": "Integration by Substitution (u-Substitution)",
        },
    },
}


def init_db():
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("""CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL
    )""")
  cursor.execute("""CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, role TEXT, message TEXT
    )""")
  conn.commit()
  conn.close()


def get_student_list():
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("SELECT name FROM students")
  rows = cursor.fetchall()
  conn.close()
  return [r[0] for r in rows]


def get_or_create_student(name):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("SELECT id, name FROM students WHERE name = ?", (name,))
  row = cursor.fetchone()
  if not row:
    cursor.execute("INSERT INTO students (name) VALUES (?)", (name,))
    conn.commit()
    sid = cursor.lastrowid
    conn.close()
    return {"id": sid, "name": name}
  conn.close()
  return {"id": row[0], "name": row[1]}


def save_chat(student_id, role, message):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute(
      "INSERT INTO chat_history (student_id, role, message) VALUES (?, ?, ?)",
      (student_id, role, message),
  )
  conn.commit()
  conn.close()


def load_chat_history(student_id):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute(
      "SELECT role, message FROM chat_history WHERE student_id = ? ORDER BY id"
      " ASC",
      (student_id,),
  )
  rows = cursor.fetchall()
  conn.close()
  return [{"role": r[0], "message": r[1]} for r in rows]

def init_db():
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("""CREATE TABLE IF NOT EXISTS students (
        id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL
    )""")
  cursor.execute("""CREATE TABLE IF NOT EXISTS topic_progress (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        student_id INTEGER,
        subtopic_id TEXT,
        correct_count INTEGER DEFAULT 0,
        UNIQUE(student_id, subtopic_id)
    )""")
  cursor.execute("""CREATE TABLE IF NOT EXISTS chat_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT, student_id INTEGER, role TEXT, message TEXT
    )""")
  conn.commit()
  conn.close()


def increment_topic_progress(student_id, subtopic_id):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute(
      """
        INSERT INTO topic_progress (student_id, subtopic_id, correct_count)
        VALUES (?, ?, 1)
        ON CONFLICT(student_id, subtopic_id) DO UPDATE SET
        correct_count = correct_count + 1
    """,
      (student_id, subtopic_id),
  )
  conn.commit()
  conn.close()


def get_all_student_progress(student_id):
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute(
      """
        SELECT subtopic_id, correct_count FROM topic_progress
        WHERE student_id = ?
    """,
      (student_id,),
  )
  rows = cursor.fetchall()
  conn.close()
  return {row[0]: row[1] for row in rows}

def clear_student_chat_history(student_id: int):
  """Deletes all saved chat messages for a given student."""
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("DELETE FROM chat_history WHERE student_id = ?", (student_id,))
  conn.commit()
  conn.close()


def delete_student_record(student_id: int):
  """Completely removes a student along with their chat history and progress."""
  conn = sqlite3.connect(DB_FILE)
  cursor = conn.cursor()
  cursor.execute("DELETE FROM chat_history WHERE student_id = ?", (student_id,))
  cursor.execute("DELETE FROM progress WHERE student_id = ?", (student_id,))
  cursor.execute("DELETE FROM students WHERE id = ?", (student_id,))
  conn.commit()
  conn.close()