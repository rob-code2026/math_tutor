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
1. Exam Workspace (Shows active problem, instructions, and step-by-step solution)
2. Terminology Cards (Key terms related strictly to the active problem)
3. Chat Facilitator (Your conversation with the student)

STRICT LATEX & NUMBER FORMATTING RULES:

1. FRACTIONS & MIXED NUMBERS:
   - ALWAYS write fractions as "\\frac{numerator}{denominator}" inside single dollar signs ($...$).
   - Mixed numbers MUST have a space between the whole number and \\frac: "$3 \\frac{1}{2}$".
   - NEVER use Unicode fraction characters like "¾", "½", "3⁄4", or "1⁄2".
   - NEVER omit the backslash or double the word: "\\fracrac" or "\\ffrac" are strictly forbidden.

2. NUMBERS & DOLLAR SIGNS ($...$):
   - Wrap ONLY LaTeX formulas, equations, fractions, and math variables in dollar signs ($...$).
   - DO NOT wrap plain numbers, decimals, or whole integers in dollar signs when they appear in normal sentences.
     * CORRECT: "The answer is 0.75." or "Calculate $x = \\frac{3}{4}$."
     * INCORRECT: "The answer is $0.75$."

3. BANNED PHRASES & GREETINGS:
   - NEVER, UNDER ANY CIRCUMSTANCES, SAY "You're welcome!".
   - NEVER say "Here's your first problem on..." unless 'Recent Chat History' is completely empty.

4. STATE MANAGEMENT:
   - WHEN STUDENT SOLVES A PROBLEM CORRECTLY: Acknowledge answer in 'chat_response'. Generate a BRAND NEW problem in 'workspace'. Set 'solution_steps' to null or [].
   - WHEN STUDENT IS STUCK/INCORRECT: Keep exact same 'workspace'. Populate 'solution_steps' with clear, ordered step-by-step math explanations.

JSON OUTPUT SCHEMA (RESPOND ONLY WITH VALID JSON):
{
  "chat_response": "Direct guidance or feedback.",
  "workspace": {
    "title": "Title of problem",
    "instructions": "Instructions for solving",
    "color_coded_html": "Problem statement with LaTeX math like $\\frac{3}{4}$",
    "expected_answer": "0.75",
    "solution_steps": [
      "Step 1: Divide 3 by 4.",
      "Step 2: $3 \\div 4 = 0.75$."
    ]
  },
  "terminologies": [
    {
      "term": "Numerator",
      "color": "#3B82F6",
      "definition": "The top number in a fraction."
    }
  ]
}"""


def _clean_json_response(raw_text):
    """Strips markdown code blocks or extra whitespace from model output."""
    cleaned = raw_text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned, flags=re.MULTILINE)
    cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
    return cleaned.strip()


def sanitize_math_output(json_data):
    """Fixes KaTeX rendering errors for mixed numbers, missing backslashes, and fractions."""
    if not json_data:
        return json_data

    def clean_markdown_text(text):
        if not isinstance(text, str):
            return text

        # 1. Fix control character corruption (\x0c or \f -> \frac)
        text = text.replace('\x0c', r'\frac').replace('\f', r'\frac')

        # 2. Correct common typos (\fracrac, \ffrac -> \frac)
        text = re.sub(r'\\+fracrac', r'\\frac', text)
        text = re.sub(r'\\+ffrac', r'\\frac', text)

        # 3. Collapse double backslashes before 'frac' into single raw LaTeX backslash
        text = re.sub(r'\\+frac', r'\\frac', text)

        # 4. Ensure space between whole number and \frac for mixed numbers (e.g., "3\frac" -> "3 \frac")
        text = re.sub(r'(\d)\s*\\frac', r'\1 \\frac', text)

        # 5. Convert literal Unicode fraction characters into standard LaTeX
        unicode_fracs = {
            '½': r'$\frac{1}{2}$', '⅓': r'$\frac{1}{3}$', '⅔': r'$\frac{2}{3}$',
            '¼': r'$\frac{1}{4}$', '¾': r'$\frac{3}{4}$', '⅕': r'$\frac{1}{5}$',
            '⅖': r'$\frac{2}{5}$', '⅗': r'$\frac{3}{5}$', '⅘': r'$\frac{4}{5}$',
            '⅙': r'$\frac{1}{6}$', '⅚': r'$\frac{5}{6}$', '⅛': r'$\frac{1}{8}$',
            '⅜': r'$\frac{3}{8}$', '⅝': r'$\frac{5}{8}$', '⅞': r'$\frac{7}{8}$',
            '⁄': '/'
        }
        for u_char, latex_sub in unicode_fracs.items():
            text = text.replace(u_char, latex_sub)

        return text

    def recursive_sanitize(data):
        if isinstance(data, dict):
            return {k: recursive_sanitize(v) for k, v in data.items()}
        elif isinstance(data, list):
            return [recursive_sanitize(item) for item in data]
        elif isinstance(data, str):
            return clean_markdown_text(data)
        return data

    if isinstance(json_data, dict):
        json_data = recursive_sanitize(json_data)

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
                "IMPORTANT: You must respond ONLY with a raw, valid JSON object matching the requested schema."
            )

            messages = [
                {"role": "system", "content": groq_system},
                {"role": "user", "content": prompt},
            ]

            response = client.chat.completions.create(
                model="openai/gpt-oss-120b",  # Restored exact model name
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
            max_output_tokens=2048,
            temperature=0.3,
        )

        max_retries = 3
        backoff_delay = 2.0

        for attempt in range(max_retries):
            try:
                _enforce_rate_limit()

                response = client.models.generate_content_stream(
                    model="gemini-3.6-flash",
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
                "color_coded_html": "Ollama process offline.",
                "expected_answer": "",
            },
            "terminologies": [],
        })
    except requests.exceptions.Timeout:
        yield json.dumps({
            "chat_response": "The request timed out waiting for local LLM.",
            "workspace": active_workspace,
            "terminologies": [],
        })
    except Exception as e:
        yield json.dumps({
            "chat_response": f"Unexpected error connecting to local LLM: {str(e)}",
            "workspace": active_workspace,
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