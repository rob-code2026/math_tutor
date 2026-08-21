import re
import sympy as sp


def verify_math_expression(expr_str):
  """Uses SymPy to evaluate raw expressions safely."""
  try:
    clean_expr = expr_str.replace("=", "==").strip()
    parsed = sp.sympify(clean_expr)
    return str(parsed)
  except Exception:
    return None


def check_calculus_answer(student_input, expected_expr, variable='x'):
  """Checks symbolic mathematical equivalence for calculus expressions."""
  try:
    var = sp.Symbol(variable)

    # Parse student input and expected solution into SymPy mathematical objects
    s_expr = sp.sympify(student_input)
    e_expr = sp.sympify(expected_expr)

    # Simplify the difference between student answer and expected solution
    # If (student_answer - expected_answer) simplifies to 0, they are mathematically identical
    difference = sp.simplify(s_expr - e_expr)

    return difference == 0
  except Exception:
    # Fallback to normalized text comparison
    return student_input.strip().lower() == expected_expr.strip().lower()


def check_student_answer(student_input, expected_expr, is_calculus=False, variable='x'):
  """Evaluates student answers. Automatically routes calculus expressions when flagged."""
  if is_calculus:
    return check_calculus_answer(student_input, expected_expr, variable)

  try:
    s_val = sp.sympify(student_input.strip())
    e_val = sp.sympify(expected_expr.strip())
    return sp.simplify(s_val - e_val) == 0
  except Exception:
    return student_input.strip().lower() == expected_expr.strip().lower()
