import requests
import json
import re

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2-math:7b"

TOPICS = {
    "L1_NUMBERS": "Basic Counting, Number Line & Negative Numbers",
    "L2_FRACTIONS": "Visual Fractions, Parts of Whole & Denominators",
    "L3_OPERATIONS": "Order of Operations & Basic Expressions",
    "L4_EQUATIONS": "Simple Unknowns & Balancing Equations",
    "L5_ALGEBRA": "Algebra 1: Slope & Linear Functions",
    "L6_GEOMETRY": "Geometry: Shapes, Angles & Proofs",
    "L7_ALGEBRA2": "Algebra 2: Quadratics, Exponents & Logarithms",
    "L8_PRECALC": "Pre-Calculus: Advanced Functions & Limits",
    "L9_CALCULUS": "Calculus: Derivatives & Integrals"
}

SYSTEM_PROMPT_TEMPLATE = """
You are an expert, encouraging, Socratic AI Math Tutor for a teenage student building foundational math skills.

CURRENT STUDENT STATE:
- Student Name: {student_name}
- Current Active Topic: {topic_description}
- Mastery Level: {mastery_score}%
- Consecutive Errors on Current Concept: {consecutive_errors}

PEDAGOGICAL INSTRUCTIONS:
1. Micro-Step Facilitation: Keep explanations brief (3-4 sentences max). End EVERY response with ONE clear question.
2. Active Facilitation: Always push the lesson forward. If the student asks a side-question, answer concisely, then bring focus back to the math topic.
3. Remediation Strategy based on Consecutive Errors ({consecutive_errors}):
   - If 0-1 errors: Give a gentle hint pointing out the specific rule.
   - If 2 errors: Use an ELI5 (Explain Like I'm 5) analogy (e.g. money, games, pizza). Include a Mermaid diagram block if visual aid helps.
   - If 3+ errors: Pause the main question. Step down to an even simpler elementary sub-concept (e.g., counting on a number line or balance scale).
4. Diagram Generation: When explaining visual concepts, output a Mermaid.js diagram inside ```mermaid ... ``` code block.

Format math nicely using LaTeX like $x + 2 = 5$.
"""


def query_ollama(prompt, system_prompt):
  payload = {
    "model": MODEL_NAME,
    "prompt": prompt,
    "system": system_prompt,
    "stream": False
  }
  try:
    response = requests.post(OLLAMA_URL, json=payload, timeout=30)
    if response.status_code == 200:
      return response.json().get("response", "Error getting response from local Ollama.")
    else:
      return f"[Offline Fallback] Ollama not responding on {OLLAMA_URL}. Ensure Ollama is running 'ollama run qwen2.5-math:7b'."
  except Exception:
    return "[System Note]: Local Ollama model is offline. (Run 'ollama serve' & 'ollama pull qwen2.5-math:7b' locally to activate)."


def get_tutor_response(student_name, topic_id, mastery_score, consecutive_errors, chat_history, user_message):
  topic_desc = TOPICS.get(topic_id, "Foundational Math")
  system_prompt = SYSTEM_PROMPT_TEMPLATE.format(
    student_name=student_name,
    topic_description=topic_desc,
    mastery_score=mastery_score,
    consecutive_errors=consecutive_errors
  )

  context = ""
  for msg in chat_history[-6:]:
    context += f"\n{msg['role'].upper()}: {msg['message']}"

  full_prompt = f"{context}\nUSER: {user_message}\nASSISTANT:"

  return query_ollama(full_prompt, system_prompt)
