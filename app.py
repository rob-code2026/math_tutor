import time
import json
import database as db
import math_verifier as verifier
import streamlit as st
import tutor_engine as engine

st.set_page_config(page_title="MathOS AI Tutor", page_icon="🧮", layout="wide")
db.init_db()

# --- CUSTOM CSS ---
st.markdown(
    """
  <style>
  .stApp { background-color: #0F172A; color: #F8FAFC; }
  div[data-testid="stSidebar"] { background-color: #1E293B !important; }
  .exam-paper { background-color: #1E293B; padding: 20px; border-radius: 12px; border: 2px solid #334155; }
  .term-card { background-color: #1E293B; border-radius: 8px; padding: 12px; margin-bottom: 10px; border-left: 5px solid #3B82F6; }

  .focus-banner {
      background: linear-gradient(90deg, #1E293B 0%, #0F172A 100%);
      border: 1px solid #3B82F6;
      border-radius: 10px;
      padding: 12px 20px;
      margin-bottom: 20px;
      display: flex;
      align-items: center;
      justify-content: space-between;
  }
  .focus-banner-title {
      color: #94A3B8;
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      margin: 0;
  }
  .focus-banner-topic {
      color: #38BDF8;
      font-size: 1.25rem;
      font-weight: 700;
      margin: 0;
  }
  </style>
""",
    unsafe_allow_html=True,
)

# --- SESSION STATES ---
if "selected_subtopic" not in st.session_state:
    st.session_state.selected_subtopic = "L1_1"

if "active_workspace" not in st.session_state:
    st.session_state.active_workspace = None

if "active_terminologies" not in st.session_state:
    st.session_state.active_terminologies = []

if "pending_user_input" not in st.session_state:
    st.session_state.pending_user_input = None

if "ai_mode" not in st.session_state:
    st.session_state.ai_mode = "Online (Groq Free)"

if "groq_api_key" not in st.session_state:
    st.session_state.groq_api_key = ""

if "gemini_api_key" not in st.session_state:
    st.session_state.gemini_api_key = ""

if "is_generating" not in st.session_state:
    st.session_state.is_generating = False


def render_cooldown_banner(seconds: int = 15):
    """Displays a dynamic progress bar and visual countdown banner when rate limited."""
    status_box = st.empty()
    progress_bar = st.progress(1.0)

    for remaining in range(seconds, 0, -1):
        status_box.warning(
            f"⏳ **Rate limit reached:** Please wait **{remaining}s** before sending your next request."
        )
        progress_bar.progress(remaining / seconds)
        time.sleep(1)

    status_box.success("✅ Cooldown complete! You can continue now.")
    progress_bar.empty()
    time.sleep(1)
    status_box.empty()


# --- HELPER TO RESOLVE API KEY ---
def get_active_api_key(mode: str) -> str:
    """Returns the API key for the selected engine, checking secrets.toml first."""
    if mode == "Online (Groq Free)":
        if "GROQ_API_KEY" in st.secrets and st.secrets["GROQ_API_KEY"].strip():
            return st.secrets["GROQ_API_KEY"].strip()
        return st.session_state.groq_api_key.strip()
    elif mode == "Online (Gemini Free)":
        if "GEMINI_API_KEY" in st.secrets and st.secrets["GEMINI_API_KEY"].strip():
            return st.secrets["GEMINI_API_KEY"].strip()
        return st.session_state.gemini_api_key.strip()
    return ""


# --- SIDEBAR: STUDENT SELECTION & SETTINGS ---
st.sidebar.title("🧮 MathOS Tutor")
existing_students = db.get_student_list()
selected_student_name = st.sidebar.selectbox(
    "Select Student:",
    ["-- Create New --"] + existing_students
    if existing_students
    else ["-- Create New --"],
)

if selected_student_name == "-- Create New --":
    new_name = st.sidebar.text_input("Enter Name:")
    if (
        st.sidebar.button("Start Learning", use_container_width=True)
        and new_name.strip()
    ):
        student = db.get_or_create_student(new_name.strip())
        st.session_state["student"] = student
        st.session_state.active_workspace = None
        st.session_state.active_terminologies = []
        st.rerun()
else:
    student = db.get_or_create_student(selected_student_name)
    st.session_state["student"] = student

# --- SIDEBAR: AI ENGINE CONFIGURATION ---
st.sidebar.markdown("---")
with st.sidebar.expander("🤖 AI Engine Settings", expanded=True):
    modes_list = ["Online (Groq Free)", "Online (Gemini Free)", "Local Model (Ollama)"]
    default_idx = modes_list.index(st.session_state.ai_mode) if st.session_state.ai_mode in modes_list else 0

    ai_mode = st.radio(
        "Choose Model Backend:",
        modes_list,
        index=default_idx,
    )
    st.session_state.ai_mode = ai_mode

    if ai_mode == "Online (Groq Free)":
        if "GROQ_API_KEY" in st.secrets and st.secrets["GROQ_API_KEY"].strip():
            st.session_state.groq_api_key = st.secrets["GROQ_API_KEY"].strip()
            st.success("🔒 Groq API Key loaded from secrets.toml")
        else:
            groq_key_input = st.text_input(
                "Groq API Key:",
                value=st.session_state.groq_api_key,
                type="password",
                help="Get a free key at https://console.groq.com/ or set GROQ_API_KEY in .streamlit/secrets.toml",
            )
            st.session_state.groq_api_key = groq_key_input

    elif ai_mode == "Online (Gemini Free)":
        if "GEMINI_API_KEY" in st.secrets and st.secrets["GEMINI_API_KEY"].strip():
            st.session_state.gemini_api_key = st.secrets["GEMINI_API_KEY"].strip()
            st.success("🔒 Gemini API Key loaded from secrets.toml")
        else:
            gemini_key_input = st.text_input(
                "Gemini API Key:",
                value=st.session_state.gemini_api_key,
                type="password",
                help="Get a free key at https://aistudio.google.com/ or set GEMINI_API_KEY in .streamlit/secrets.toml",
            )
            st.session_state.gemini_api_key = gemini_key_input
    else:
        st.caption("🌐 Connects to local endpoint: `http://localhost:11434`")

if "student" in st.session_state:
    student_id = st.session_state["student"]["id"]
    student_progress = db.get_all_student_progress(student_id)

    st.sidebar.markdown("---")
    st.sidebar.subheader("📚 Curriculum (L1 to L10)")

    for main_key, main_val in db.CURRICULUM_TREE.items():
        with st.sidebar.expander(main_val["title"]):
            for sub_id, sub_title in main_val["subtopics"].items():
                count = student_progress.get(sub_id, 0)
                badge = f" ✅ {count}" if count > 0 else ""
                button_label = f"📌 {sub_title}{badge}"

                if st.button(button_label, key=sub_id, use_container_width=True):
                    st.session_state.selected_subtopic = sub_id
                    st.session_state.active_workspace = None
                    st.session_state.active_terminologies = []
                    st.rerun()

    # --- SIDEBAR: ACCOUNT & DATA MANAGEMENT ---
    st.sidebar.markdown("---")
    with st.sidebar.expander("⚙️ Account & Data Management"):
        if st.button("🧹 Clear Chat History", use_container_width=True):
            db.clear_student_chat_history(student_id)
            st.toast("Chat history cleared successfully!", icon="🧹")
            st.rerun()

        st.markdown("---")
        st.caption("⚠️ Danger Zone")
        if st.button(
            "🗑️ Delete Student Profile",
            type="primary",
            use_container_width=True,
        ):
            db.delete_student_record(student_id)
            del st.session_state["student"]
            st.session_state.active_workspace = None
            st.session_state.active_terminologies = []
            st.toast("Student profile and data deleted.", icon="🗑️")
            st.rerun()

    subtopic_id = st.session_state.selected_subtopic

    main_category_title = "Math Level"
    subtopic_title = "Math Subtopic"
    for cat in db.CURRICULUM_TREE.values():
        if subtopic_id in cat["subtopics"]:
            main_category_title = cat["title"]
            subtopic_title = cat["subtopics"][subtopic_id]
            break

    # --- INITIALIZE FIRST PROBLEM IF SESSION IS EMPTY ---
    if st.session_state.active_workspace is None:
        active_key = get_active_api_key(st.session_state.ai_mode)

        raw_stream = engine.stream_tutor_payload(
            student_name=st.session_state["student"]["name"],
            subtopic_title=subtopic_title,
            user_message=(
                f"Hello! I am ready to start practicing {subtopic_title}. Please"
                " present my first problem."
            ),
            is_correct_attempt=None,
            active_workspace=None,
            chat_history=[],
            mode=st.session_state.ai_mode,
            api_key=active_key,
        )
        accumulated_json = "".join([token for token in raw_stream])
        payload = engine.parse_final_payload(accumulated_json)

        ws_init = payload.get("workspace") or {}
        ws_init["solution_steps"] = []
        st.session_state.active_workspace = ws_init
        st.session_state.active_terminologies = payload.get("terminologies", [])
        db.save_chat(
            student_id, "assistant", payload.get("chat_response", "Let's begin!")
        )

    # --- ACTIVE TOPIC BANNER ON TOP OF UI ---
    st.markdown(
        f"""
      <div class="focus-banner">
          <div>
              <p class="focus-banner-title">🎯 CURRENT FOCUS LEVEL: <b>{main_category_title}</b></p>
              <p class="focus-banner-topic">📌 {subtopic_title}</p>
          </div>
          <div style="text-align: right; color: #94A3B8; font-size: 0.9rem;">
              Engine: <b style="color: #38BDF8;">{st.session_state.ai_mode}</b> | 
              Student: <b style="color: #F8FAFC;">{st.session_state['student']['name']}</b>
          </div>
      </div>
      """,
        unsafe_allow_html=True,
    )

    # --- MAIN THREE-COLUMN LAYOUT ---
    col_exam, col_terms, col_chat = st.columns([1.2, 1, 1.4])

    ws = st.session_state.active_workspace or {}

    with col_exam:
        st.subheader("📜 Formal Exam Workspace")

        # Outer container card start
        st.markdown('<div class="exam-paper">', unsafe_allow_html=True)

        # Header & Instructions
        st.markdown(f"#### 🎓 {ws.get('title', 'Exam Task')}")
        if ws.get('instructions'):
            st.markdown(f"<p style='color:#94A3B8;'>{ws.get('instructions')}</p>", unsafe_allow_html=True)

        st.markdown("<hr style='border-color:#334155;'>", unsafe_allow_html=True)

        # Problem statement (Rendered via st.markdown so LaTeX $3 \\frac{1}{2}$ formats properly)
        st.markdown("**Problem:**")
        st.markdown(ws.get('color_coded_html', 'No problem active.'))

        # Step-by-step solution steps (Rendered as native Streamlit Markdown to support KaTeX math)
        steps = ws.get("solution_steps") or []
        if steps:
            st.markdown(
                """
                <hr style="border-color:#334155; margin-top: 15px; margin-bottom: 15px;">
                <div style="background-color: #0F172A; padding: 12px; border-radius: 8px; border-left: 4px solid #10B981; margin-bottom: 10px;">
                    <h5 style="color: #10B981; margin-top: 0; margin-bottom: 8px;">💡 Step-by-Step Solution</h5>
                """,
                unsafe_allow_html=True,
            )
            for idx, step in enumerate(steps, 1):
                st.markdown(f"**Step {idx}:** {step}")

            st.markdown("</div>", unsafe_allow_html=True)

        # Outer container card end
        st.markdown("</div>", unsafe_allow_html=True)

    with col_terms:
        st.subheader("📖 Terminology")
        for term in st.session_state.active_terminologies:
            st.markdown(
                f"""
                <div class="term-card" style="border-left-color: {term.get('color', '#3B82F6')};">
                    <span style="color:{term.get('color', '#3B82F6')}; font-weight:bold;">🏷️ {term.get('term', '')}</span>
                    <p style="margin-top:4px; font-size:0.88rem; color:#CBD5E1;">{term.get('definition', '')}</p>
                </div>
            """,
                unsafe_allow_html=True,
            )

    with col_chat:
        st.subheader("💬 AI Tutor Facilitator")

        chat_container = st.container(height=400)
        history = db.load_chat_history(student_id)

        with chat_container:
            for msg in history:
                avatar_icon = "🤖" if msg["role"] == "assistant" else "🧑‍🎓"
                with st.chat_message(msg["role"], avatar=avatar_icon):
                    st.markdown(msg["message"])

        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button(
                "💡 Explain Like I'm 5",
                use_container_width=True,
                disabled=st.session_state.is_generating,
            ):
                st.session_state.pending_user_input = (
                    "I don't understand, please explain it like I'm 5 years old. Use a"
                    " completely different analogy or perspective, and do not repeat"
                    " the previous explanation."
                )
                st.rerun()

        with btn_col2:
            if st.button(
                "➡️ Proceed / Next Problem",
                use_container_width=True,
                disabled=st.session_state.is_generating,
            ):
                st.session_state.pending_user_input = (
                    "OK, I'm ready! Please give me the next problem or move forward."
                )
                st.rerun()

    # --- PROCESS USER INPUT & STREAM AI RESPONSE ---
    chat_input = st.chat_input(
        "Type your answer or ask for help...",
        disabled=st.session_state.is_generating,
    )

    user_input = None
    if st.session_state.pending_user_input:
        user_input = st.session_state.pending_user_input
        st.session_state.pending_user_input = None
    elif chat_input:
        user_input = chat_input

    if user_input:
        st.session_state.is_generating = True
        clean_input = user_input.strip()

        is_math_attempt = any(
            c.isdigit() for c in clean_input
        ) or clean_input.lower() in ["x", "y", "dx", "dt"]

        is_correct = None
        if is_math_attempt and st.session_state.active_workspace:
            expected = st.session_state.active_workspace.get("expected_answer", "")
            if expected:
                is_correct = verifier.check_student_answer(clean_input, expected)
                if is_correct:
                    db.increment_topic_progress(student_id, subtopic_id)

        db.save_chat(student_id, "user", user_input)

        raw_history = db.load_chat_history(student_id)
        recent_history = raw_history[-4:] if raw_history else []

        active_key = get_active_api_key(st.session_state.ai_mode)

        with col_chat:
            with st.chat_message("assistant", avatar="🤖"):
                response_box = st.empty()
                full_raw_stream = ""

                token_generator = engine.stream_tutor_payload(
                    student_name=st.session_state["student"]["name"],
                    subtopic_title=subtopic_title,
                    user_message=user_input,
                    is_correct_attempt=is_correct,
                    active_workspace=st.session_state.active_workspace,
                    chat_history=recent_history,
                    mode=st.session_state.ai_mode,
                    api_key=active_key,
                )

                for token in token_generator:
                    full_raw_stream += token
                    response_box.code(full_raw_stream + "▌", language="json")

        payload = engine.parse_final_payload(
            full_raw_stream, st.session_state.active_workspace
        )

        # Check for rate limits and render visual timer if flagged
        if payload.get("rate_limited"):
            render_cooldown_banner(payload.get("cooldown_seconds", 15))

        if is_correct is True:
            new_workspace = payload.get("workspace") or {}
            new_workspace["solution_steps"] = []
            if (
                new_workspace.get("expected_answer")
                == st.session_state.active_workspace.get("expected_answer")
            ):
                st.session_state.active_workspace = None
            else:
                st.session_state.active_workspace = new_workspace
        else:
            if "workspace" in payload and payload["workspace"]:
                st.session_state.active_workspace = payload["workspace"]

        if "terminologies" in payload and payload["terminologies"]:
            st.session_state.active_terminologies = payload["terminologies"]

        db.save_chat(
            student_id,
            "assistant",
            payload.get("chat_response", "Let's keep going!"),
        )
        st.session_state.is_generating = False
        st.rerun()