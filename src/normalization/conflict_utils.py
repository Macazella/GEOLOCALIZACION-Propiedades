"""
Comparación de valores provenientes de distintas fuentes (dato
estructurado vs. texto libre) para detectar contradicciones. Nunca se
resuelve el conflicto "adivinando" cuál es el correcto: se preservan
ambos valores y se marca needs_manual_review.
"""

from typing import Optional


def compare_numbers(a: Optional[str], b: Optional[str]) -> tuple[bool, str]:
    """Compara dos alturas/números de calle. Devuelve (hay_conflicto, detalle)."""
    if a is None or b is None:
        return False, ""
    if str(a).strip() == str(b).strip():
        return False, ""
    return True, f"numero_estructurado={a} vs numero_texto={b}"


def compare_streets(a: Optional[str], b: Optional[str]) -> tuple[bool, str]:
    if not a or not b:
        return False, ""
    norm_a = a.lower().strip().replace("av.", "avenida").replace("  ", " ")
    norm_b = b.lower().strip().replace("av.", "avenida").replace("  ", " ")
    if norm_a == norm_b or norm_a in norm_b or norm_b in norm_a:
        return False, ""
    return True, f"calle_estructurada='{a}' vs calle_texto='{b}'"


def compare_booleans(a: Optional[bool], b: Optional[bool]) -> tuple[bool, str]:
    """a/b: True, False o None (None = "no mencionado", no es un valor real)."""
    if a is None or b is None:
        return False, ""
    if a == b:
        return False, ""
    return True, f"estructurado={a} vs texto={b}"
