import json
import re
import time
import requests
from google import genai
from google.genai import types
from google.genai.errors import APIError
from groq import Groq


def get_groq_client(api_key):
    """Initializes and returns a Groq client with sanitized API key."""
    clean_key = api_key.strip() if api_key else ""
    if not clean_key:
        raise ValueError("Groq API Key is missing or empty.")
    return Groq(api_key=clean_key)


OLLAMA_URL = "http://127.0.0.1:11434/api/generate"
MODEL_NAME = "qwen2-math:7b"

# Minimum delay between consecutive API calls (in seconds)
MIN_REQUEST_INTERVAL = 4.0
_last_request_time = 0.0

SYSTEM_INSTRUCTION = """You are MathOS Tutor, an empathetic and highly effective AI math teacher.
You drive an interactive learning UI with three main panels:
1. Exam Workspace (Shows active problem, instructions, and step-by-step solution when needed)
2. Terminology Cards (Key terms related strictly to the active problem)
3. Chat Facilitator (Your conversation with the student)

STRICT RULE ENFORCEMENT:

1. LATEX & MATH FORMATTING (STRICT RULES):
   - ALWAYS use single dollar signs for math (e.g., $x + 2 = 5$).
   - ALWAYS leave a space between a whole number and \frac for mixed fractions:
     * CORRECT: "$3 \frac{1}{4}$"
     * FORBIDDEN: "$3\frac{1}{4}$"

   - EXAMPLES:
     ❌ BAD:  "The answer is 3\frac{1}{4}."
     ❌ BAD:  "The answer is 3\\frac{1}{4}."
     ✅ GOOD: "The answer is $3 \frac{1}{4}$."

     ❌ BAD:  "Add 5\frac{2}{3} to 1\frac{1}{3}."
     ✅ GOOD: "Add $5 \frac{2}{3}$ to $1 \frac{1}{3}$."
     
2. BANNED PHRASES:
   - NEVER, UNDER ANY CIRCUMSTANCES, SAY "You're welcome!".
   - NEVER say "Here's your first problem on..." unless 'Recent Chat History' is completely empty.

3. WHEN STUDENT SOLVES A PROBLEM CORRECTLY (`Verification Status on Previous Attempt: True`):
   - Acknowledge their correct answer directly in 'chat_response'.
   - You MUST generate a BRAND NEW problem in 'workspace' that is DIFFERENT from the old problem.
   - Do NOT repeat equations or numbers from previous turns.
   - Set 'solution_steps' in 'workspace' to null or an empty list for the new problem.

4. WHEN STUDENT IS STUCK, WRONG (`Verification Status on Previous Attempt: False`), OR ASKS FOR THE SOLUTION/HINT:
   - Provide a helpful response in 'chat_response'.
   - Keep the exact same active problem in 'workspace'.
   - Populate 'solution_steps' in 'workspace' with clear, ordered step-by-step explanations on how to solve the problem.

JSON SCHEMA:
{
  "chat_response": "Direct praise, guidance, or brief summary without greeting filler.",
  "workspace": {
    "title": "Title of problem",
    "instructions": "Instructions for solving",
    "color_coded_html": "Problem statement styled in HTML",
    "expected_answer": "Canonical exact math answer",
    "solution_steps": [
      "Step 1: Explain the first action...",
      "Step 2: Show intermediate calculation...",
      "Step 3: State final solution..."
    ]
  },
  "terminologies": [
    {
      "term": "Term Name",
      "color": "#3B82F6",
      "definition": "Definition"
    }
  ]
}"""


def _clean_json_response(raw_text):
    """Strips markdown code blocks or extra whitespace from model output."""
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()


def sanitize_math_output(json_data: dict) -> dict:
    """Fixes Streamlit KaTeX and HTML rendering errors for mixed numbers and fractions."""
    if not isinstance(json_data, dict):
        return json_data

    def clean_markdown_text(text):
        if not isinstance(text, str):
            return text

        # 1. Fix Python control character / form-feed corruption (\x0c or \f -> \frac)
        text = text.replace('\x0c', r'\frac').replace('\f', r'\frac')

        # 2. Collapse double backslashes before 'frac' into a single backslash for raw LaTeX
        text = re.sub(r'\\+frac', r'\\frac', text)

        # 3. Ensure a space between any digit and \frac (e.g. "3\frac" -> "3 \frac")
        text = re.sub(r'(\d)\s*\\frac', r'\1 \\frac', text)

        return text

    def clean_html_text(text):
        if not isinstance(text, str):
            return text

        # Clean standard backslashes first
        text = clean_markdown_text(text)

        # HTML can't process $3 \frac{1}{2}$ automatically.
        # Convert LaTeX fractions in HTML fields to standard fraction format (e.g., 3 1/2 or <sup>1</sup>/<sub>2</sub>)
        text = re.sub(r'\$(\d+)\s*\\frac\{(\d+)\}\{(\d+)\}\$', r'\1 <sup>\2</sup>&frasl;<sub>\3</sub>', text)
        text = re.sub(r'\$\\frac\{(\d+)\}\{(\d+)\}\$', r'<sup>\1</sup>&frasl;<sub>\2</sub>', text)
        text = re.sub(r'(\d+)\s*\\frac\{(\d+)\}\{(\d+)\}', r'\1 <sup>\2</sup>&frasl;<sub>\3</sub>', text)
        text = re.sub(r'\\frac\{(\d+)\}\{(\d+)\}', r'<sup>\1</sup>&frasl;<sub>\2</sub>', text)

        return text

    # Clean chat response
    if "chat_response" in json_data:
        json_data["chat_response"] = clean_markdown_text(json_data["chat_response"])

    # Clean workspace fields (HTML field uses clean_html_text)
    if "workspace" in json_data and isinstance(json_data["workspace"], dict):
        ws = json_data["workspace"]
        if "instructions" in ws:
            ws["instructions"] = clean_markdown_text(ws["instructions"])
        if "color_coded_html" in ws:
            ws["color_coded_html"] = clean_html_text(ws["color_coded_html"])
        if "solution_steps" in ws and isinstance(ws["solution_steps"], list):
            ws["solution_steps"] = [clean_markdown_text(step) for step in ws["solution_steps"]]

    # Clean terminology definitions
    if "terminologies" in json_data and isinstance(json_data["terminologies"], list):
        for term in json_data["terminologies"]:
            if isinstance(term, dict) and "definition" in term:
                term["definition"] = clean_markdown_text(term["definition"])

    return json_data

def _enforce_rate_limit():
    """Ensures requests are spaced at least MIN_REQUEST_INTERVAL seconds apart."""
    global _last_request_time
    now = time.time()
    elapsed = now - _last_request_time
    if elapsed < MIN_REQUEST_INTERVAL:
        time.sleep(MIN_REQUEST_INTERVAL - elapsed)
    _last_request_time = time.time()


def stream_tutor_payload(
    student_name,
    subtopic_title,
    user_message,
    is_correct_attempt=None,
    active_workspace=None,
    chat_history=None,
    mode="Online (Groq Free)",
    api_key="",
):
    """Yields raw JSON tokens as they stream from Groq, Gemini, or Ollama."""
    context_summary = ""
    if chat_history:
        recent_history = chat_history[-4:]
        context_summary = "\n".join(
            [f"{h['role'].capitalize()}: {h['message']}" for h in recent_history]
        )

    if is_correct_attempt is True:
        input_status = "STUDENT SOLVED IT CORRECTLY -> GENERATE NEW PROBLEM"
    elif is_correct_attempt is False:
        input_status = "STUDENT ANSWER WAS INCORRECT -> PROVIDE HINT, KEEP PROBLEM"
    else:
        input_status = "STUDENT ASKED QUESTION / NEEDS HELP"

    prompt = f"""{SYSTEM_INSTRUCTION}

--- CURRENT CONTEXT ---
Student Name: {student_name}
Topic: {subtopic_title}
Status: {input_status}
Active Problem Before This Message: {json.dumps(active_workspace) if active_workspace else 'None'}

Recent Chat History:
{context_summary}

Student Input: {user_message}

CRITICAL: Do NOT say "You're welcome!". Output strictly valid JSON matching the schema."""

    # --- 1. GROQ BACKEND ---
    if mode == "Online (Groq Free)":
        if isinstance(api_key, str):
            api_key = api_key.strip()

        # Check Streamlit secrets if no key passed in function argument
        if not api_key:
            try:
                import streamlit as st
                api_key = st.secrets.get("GROQ_API_KEY", "").strip()
            except Exception:
                pass

        if not api_key:
            yield json.dumps({
                "chat_response": "⚠️ Groq API Key missing. Please set GROQ_API_KEY in .streamlit/secrets.toml or pass it in settings.",
                "workspace": active_workspace,
                "terminologies": []
            })
            return

        try:
            client = get_groq_client(api_key)
            groq_system = (
                f"{SYSTEM_INSTRUCTION}\n\n"
                "IMPORTANT: You must respond ONLY with a raw, valid JSON object matching the requested schema. "
                "Do NOT include any conversational text outside of JSON."
            )

            messages = [
                {"role": "system", "content": groq_system},
                {"role": "user", "content": prompt},
            ]

            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",
                messages=messages,
                response_format={"type": "json_object"},
                temperature=0.3,
                stream=True,
            )

            for chunk in response:
                if hasattr(chunk, "choices") and chunk.choices:
                    delta = chunk.choices[0].delta.content
                    if delta:
                        yield delta

        except Exception as e:
            err_str = str(e)
            if "429" in err_str:
                yield json.dumps({
                    "chat_response": "Rate limit reached on Groq. Please pause briefly.",
                    "rate_limited": True,
                    "cooldown_seconds": 15,
                })
            else:
                yield json.dumps({
                    "chat_response": f"Groq API Error: {err_str}",
                    "workspace": active_workspace,
                    "terminologies": [],
                })
        return

    # --- 2. ONLINE MODEL (GEMINI FREE API) ---
    elif mode == "Online (Gemini Free)":
        clean_key = api_key.strip() if isinstance(api_key, str) else ""
        if not clean_key:
            yield json.dumps({
                "chat_response": "⚠️ Please enter a valid Gemini API key in the AI Engine Settings.",
                "workspace": active_workspace,
                "terminologies": [],
            })
            return

        client = genai.Client(api_key=clean_key)
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            max_output_tokens=1024,
            temperature=0.3,
        )

        max_retries = 3
        backoff_delay = 2.0

        for attempt in range(max_retries):
            try:
                _enforce_rate_limit()

                response = client.models.generate_content_stream(
                    model="gemini-2.5-flash",
                    contents=prompt,
                    config=config,
                )

                for chunk in response:
                    if chunk.text:
                        yield chunk.text
                return

            except APIError as e:
                if "429" in str(e) or "RESOURCE_EXHAUSTED" in str(e):
                    if attempt < max_retries - 1:
                        time.sleep(backoff_delay)
                        backoff_delay *= 2
                        continue

                    yield json.dumps({
                        "chat_response": "⚠️ Rate limit reached. Please wait for the cooldown before asking another question.",
                        "workspace": active_workspace,
                        "terminologies": [],
                        "rate_limited": True,
                        "cooldown_seconds": 15,
                    })
                    return

                yield json.dumps({
                    "chat_response": f"Gemini API Error: {str(e)}",
                    "workspace": active_workspace,
                    "terminologies": [],
                })
                return
            except Exception as e:
                yield json.dumps({
                    "chat_response": f"Gemini API Error: {str(e)}",
                    "workspace": active_workspace,
                    "terminologies": [],
                })
                return
        return

    # --- 3. LOCAL MODEL (OLLAMA DEFAULT) ---
    try:
        response = requests.post(
            OLLAMA_URL,
            json={
                "model": MODEL_NAME,
                "prompt": prompt,
                "stream": True,
                "format": "json",
                "options": {
                    "temperature": 0.4,
                    "repeat_penalty": 1.2,
                },
            },
            stream=True,
            timeout=(10, 300),
        )
        response.raise_for_status()

        for line in response.iter_lines():
            if line:
                body = json.loads(line.decode("utf-8"))
                token = body.get("response", "")
                yield token

    except requests.exceptions.ConnectionError:
        yield json.dumps({
            "chat_response": (
                "Cannot connect to Ollama at http://127.0.0.1:11434. Please ensure"
                " Ollama is running (`ollama serve`)."
            ),
            "workspace": active_workspace
            or {
                "title": subtopic_title,
                "instructions": "Connection Error",
                "color_coded_html": (
                    "<span style='color:#EF4444;'>Ollama process offline</span>"
                ),
                "expected_answer": "",
            },
            "terminologies": [],
        })
    except requests.exceptions.Timeout:
        yield json.dumps({
            "chat_response": (
                "The request timed out. The local LLM took longer than 5 minutes"
                " to respond."
            ),
            "workspace": active_workspace
            or {
                "title": subtopic_title,
                "instructions": "Timeout Error",
                "color_coded_html": (
                    "<span style='color:#EF4444;'>Response timed out</span>"
                ),
                "expected_answer": "",
            },
            "terminologies": [],
        })
    except Exception as e:
        yield json.dumps({
            "chat_response": f"Unexpected error connecting to local LLM: {str(e)}",
            "workspace": active_workspace
            or {
                "title": subtopic_title,
                "instructions": "System Error",
                "color_coded_html": "Error loading problem.",
                "expected_answer": "",
            },
            "terminologies": [],
        })


def parse_final_payload(full_raw_response, fallback_workspace=None):
    """Parses accumulated streamed text into a validated dictionary and sanitizes LaTeX math formatting."""
    cleaned = _clean_json_response(full_raw_response)
    try:
        parsed_data = json.loads(cleaned)
        return sanitize_math_output(parsed_data)
    except Exception:
        fallback_payload = {
            "chat_response": cleaned,
            "workspace": fallback_workspace
            or {
                "title": "Math Task",
                "instructions": "Solve the problem.",
                "color_coded_html": "Problem state unchanged.",
                "expected_answer": "",
            },
            "terminologies": [],
        }
        return sanitize_math_output(fallback_payload)