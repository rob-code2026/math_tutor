import streamlit as st
import streamlit.components.v1 as components
import re
import sqlite3

import database as db
import tutor_engine as engine
import math_verifier as verifier

# Set Page Configuration
st.set_page_config(page_title="MathOS AI Tutor", page_icon="🧮", layout="wide")

# Initialize DB
db.init_db()

# Custom Dark Mode CSS Injection
st.markdown("""
    <style>
    .stApp {
        background-color: #0F172A;
        color: #F8FAFC;
    }
    div[data-testid="stSidebar"] {
        background-color: #1E293B !important;
        border-right: 1px solid #334155;
    }
    .main-card {
        background-color: #1E293B;
        padding: 20px;
        border-radius: 12px;
        border: 1px solid #334155;
        margin-bottom: 15px;
    }
    .readiness-card {
        background: linear-gradient(135deg, #064E3B 0%, #022C22 100%);
        border: 2px solid #10B981;
        border-radius: 12px;
        padding: 16px;
        margin-bottom: 20px;
        color: #ECFDF5;
    }
    .readiness-title {
        font-size: 1.2rem;
        font-weight: bold;
        color: #34D399;
    }
    </style>
""", unsafe_allow_html=True)


# Helper function to render Mermaid.js diagrams using st.iframe
def render_mermaid(code):
    mermaid_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdn.jsdelivr.net/npm/mermaid/dist/mermaid.min.js"></script>
        <script>mermaid.initialize({{startOnLoad:true, theme:'dark'}});</script>
        <style>
            body {{ background-color: #0F172A; margin: 0; padding: 10px; }}
        </style>
    </head>
    <body>
        <div class="mermaid">
            {code}
        </div>
    </body>
    </html>
    """
    st.iframe(srcdoc=mermaid_html, height=220, scrolling=True)


# Sidebar - Multi-Student Profile
st.sidebar.title("🧮 MathOS Tutor")
st.sidebar.subheader("Student Profile")

existing_students = db.get_student_list()
selected_student_name = st.sidebar.selectbox("Select Student:",
                                             ["-- Create New --"] + existing_students if existing_students else [
                                               "-- Create New --"])

if selected_student_name == "-- Create New --":
  new_name = st.sidebar.text_input("Enter Student Name:")
  if st.sidebar.button("Start Learning") and new_name.strip():
    student = db.get_or_create_student(new_name.strip())
    st.session_state["student"] = student
    st.rerun()
else:
  student = db.get_or_create_student(selected_student_name)
  st.session_state["student"] = student

if "student" in st.session_state:
  current_student = st.session_state["student"]
  student_id = current_student["id"]
  student_name = current_student["name"]
  topic_id = current_student["current_topic_id"]

  prog = db.get_student_progress(student_id, topic_id)
  mastery = prog["mastery_score"]

  # Evaluate Grade Readiness Status
  readiness = db.evaluate_readiness(student_id)

  st.sidebar.markdown("---")
  st.sidebar.write(f"**Current Student:** `{student_name}`")
  st.sidebar.write(f"**Topic:** {engine.TOPICS.get(topic_id, topic_id)}")
  st.sidebar.progress(mastery / 100)
  st.sidebar.caption(f"Topic Mastery: **{mastery}%**")

  # Render Readiness Milestone Card in Sidebar
  st.sidebar.markdown("---")
  st.sidebar.subheader("🎓 Grade Readiness")
  if readiness["is_unlocked"]:
    st.sidebar.success(f"🎉 100% Ready for {readiness['target_grade']}")
  else:
    st.sidebar.info(f"Progress: {readiness['readiness_percentage']}% toward {readiness['target_grade']}")

  if st.sidebar.button("Clear Chat History"):
    conn = sqlite3.connect(db.DB_FILE)
    conn.cursor().execute("DELETE FROM chat_history WHERE student_id = ?", (student_id,))
    conn.commit()
    conn.close()
    st.rerun()

  # Main Layout
  col_vis, col_chat = st.columns([1, 1.2])

  with col_vis:
    # Show Readiness Achievement Banner
    if readiness["is_unlocked"] or readiness["readiness_percentage"] > 0:
      skills_str = ", ".join(readiness["mastered_skills"]) if readiness["mastered_skills"] else "In progress..."
      st.markdown(f"""
                <div class="readiness-card">
                    <div class="readiness-title">🏆 Readiness Achievement Unlocked!</div>
                    <div><b>Student:</b> {student_name}</div>
                    <div><b>Status:</b> {readiness['readiness_percentage']}% Ready for {readiness['target_grade']}</div>
                    <div><b>Has mastered:</b> {skills_str}</div>
                </div>
            """, unsafe_allow_html=True)

    st.markdown('<div class="main-card">', unsafe_allow_html=True)
    st.subheader("📊 Visual Workspace & Concept Board")
    st.info("Visual diagrams, number lines, and step-by-step breakdowns appear here automatically as you learn.")

    chat_logs = db.load_chat_history(student_id)
    latest_mermaid = None
    for msg in reversed(chat_logs):
      if "```mermaid" in msg["message"]:
        match = re.search(r"```mermaid(.*?)```", msg["message"], re.DOTALL)
        if match:
          latest_mermaid = match.group(1).strip()
          break

    if latest_mermaid:
      st.write("**Current Concept Diagram:**")
      render_mermaid(latest_mermaid)
    else:
      render_mermaid("graph LR; A[Elementary Foundations] --> B[Numbers & Line]; B --> C[Fractions]; C --> D[Algebra];")

    st.markdown('</div>', unsafe_allow_html=True)

  with col_chat:
    st.subheader(f"💬 Active Tutor Chat — Welcome, {student_name}!")

    history = db.load_chat_history(student_id)

    if not history:
      initial_greeting = f"Hi {student_name}! I'm your AI Math Coach. Let's start with a quick check: What is $7 - (-3)$? Take a guess or show your steps!"
      db.save_chat(student_id, "assistant", initial_greeting)
      history = db.load_chat_history(student_id)

    chat_container = st.container(height=450)
    with chat_container:
      for msg in history:
        with st.chat_message(msg["role"]):
          clean_text = re.sub(r"```mermaid.*?```", "*(Visual diagram rendered in left board)*", msg["message"],
                              flags=re.DOTALL)
          st.markdown(clean_text)

    if user_input := st.chat_input("Type your answer or ask any math question..."):
      db.save_chat(student_id, "user", user_input)

      # Simple heuristic check to update student progress
      updated_prog = db.update_progress(student_id, topic_id, is_correct=True)

      with st.spinner("AI Tutor is thinking..."):
        ai_response = engine.get_tutor_response(
          student_name=student_name,
          topic_id=topic_id,
          mastery_score=updated_prog["mastery_score"],
          consecutive_errors=updated_prog["consecutive_errors"],
          chat_history=history,
          user_message=user_input
        )

      db.save_chat(student_id, "assistant", ai_response)
      st.rerun()

else:
  st.title("🧮 MathOS AI Agent Tutor")
  st.info("Please select or create a student profile in the sidebar to begin.")
