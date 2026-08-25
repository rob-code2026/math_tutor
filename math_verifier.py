import sympy as sp
from sympy.parsing.sympy_parser import (
    parse_expr,
    standard_transformations,
    implicit_multiplication_application,
    convert_xor,
)

# Enable implicit multiplication (2x -> 2*x) and XOR powers (x^2 -> x**2)
TRANSFORMATIONS = standard_transformations + (
    implicit_multiplication_application,
    convert_xor,
)

def check_student_answer(student_input, expected_expr):
    """
    Evaluates algebraic/numeric mathematical equivalence using SymPy.
    Handles '3x', 'x^2', fractions, and algebraic expansions.
    """
    if not student_input or not str(student_input).strip():
        return False

    clean_input = str(student_input).strip()
    clean_expected = str(expected_expr).strip()

    # Direct string match shortcut
    if clean_input.lower() == clean_expected.lower():
        return True

    try:
        # Parse expressions safely with flexible math transformations
        s_val = parse_expr(clean_input, transformations=TRANSFORMATIONS)
        e_val = parse_expr(clean_expected, transformations=TRANSFORMATIONS)

        # Check if difference simplifies to zero: (student - expected) == 0
        return sp.simplify(s_val - e_val) == 0
    except Exception:
        return False
