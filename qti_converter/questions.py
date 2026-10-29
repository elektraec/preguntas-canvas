"""Shared CSV validation for both QTI export formats."""
from __future__ import annotations

import csv
import io
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path

SUPPORTED_TYPES = {"mc", "ma", "tf", "short", "blank", "essay"}
REQUIRED_HEADERS = {"pregunta", "correcta"}
OPTION_KEYS = ("a", "b", "c", "d")
FEEDBACK_KEYS = ("feedback", "feedback_correcta", "feedback_incorrecta", *(f"feedback_{k}" for k in OPTION_KEYS))


class ValidationError(Exception):
    """The input cannot be represented by the supported QTI profiles."""


@dataclass
class Question:
    identifier: str
    title: str
    tipo: str
    text: str
    options: dict[str, str]
    answers: list[str]
    points: float
    feedback: dict[str, str]


def infer_type(row: dict[str, str]) -> str:
    return row.get("tipo", "").strip().lower() or (
        "mc" if any(row.get(k, "").strip() for k in OPTION_KEYS) else "short"
    )


def normalize_correct_answers(tipo: str, correcta: str) -> list[str]:
    if tipo == "essay":
        return []
    if tipo in {"short", "blank"}:
        return [correcta.strip()] if correcta.strip() else []
    values = [v.strip().lower() for v in correcta.split(",") if v.strip()]
    if tipo == "tf":
        mapping = {"verdadero": "a", "true": "a", "v": "a", "falso": "b", "false": "b", "f": "b"}
        values = [mapping.get(v, v) for v in values]
    return values


def validate_headers(headers: list[str]) -> dict[str, str]:
    normalized = [(h or "").strip().lower() for h in headers]
    if any(not h for h in normalized):
        raise ValidationError("El CSV contiene columnas sin encabezado.")
    if len(set(normalized)) != len(normalized):
        raise ValidationError("El CSV contiene encabezados duplicados.")
    missing = sorted(REQUIRED_HEADERS - set(normalized))
    if missing:
        raise ValidationError("Faltan columnas obligatorias en el CSV: " + ", ".join(missing))
    return dict(zip(normalized, headers))


def read_questions(path: Path) -> list[Question]:
    try:
        text = path.read_text(encoding="utf-8-sig")
    except UnicodeError as exc:
        raise ValidationError("El CSV debe guardarse con codificación UTF-8.") from exc
    except OSError as exc:
        raise ValidationError(f"No se pudo leer el CSV: {exc}") from exc
    if not text.strip():
        raise ValidationError("El CSV no contiene encabezados.")
    # Choose from the actual header, not punctuation inside question text.
    delimiter = ","
    for candidate in (",", ";"):
        header = next(csv.reader(io.StringIO(text), delimiter=candidate), [])
        if REQUIRED_HEADERS <= {h.strip().lower() for h in header}:
            delimiter = candidate
            break
    reader = csv.DictReader(io.StringIO(text, newline=""), delimiter=delimiter, strict=True)
    questions: list[Question] = []
    identifiers: set[str] = set()
    try:
        validate_headers(reader.fieldnames or [])
        for raw in reader:
            line = reader.line_num
            if None in raw:
                raise ValidationError(f"La fila que termina en la línea {line} tiene columnas de más; revisa las comillas.")
            row = {k.strip().lower(): (v or "").strip() for k, v in raw.items()}
            if not any(row.values()):
                continue
            if any(v is None for v in raw.values()):
                raise ValidationError(f"La fila que termina en la línea {line} tiene columnas de menos.")
            try:
                question = validate_question(row, len(questions) + 1)
                if question.identifier in identifiers:
                    raise ValidationError(f"El id '{question.identifier}' está duplicado.")
            except ValidationError as exc:
                raise ValidationError(f"Fila (línea final {line}): {exc}") from exc
            identifiers.add(question.identifier)
            questions.append(question)
    except csv.Error as exc:
        raise ValidationError(f"CSV mal formado cerca de la línea {reader.line_num}: {exc}") from exc
    if not questions:
        raise ValidationError("El CSV no contiene preguntas válidas para exportar.")
    return questions


def validate_question(row: dict[str, str], index: int) -> Question:
    for value in row.values():
        if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", value):
            raise ValidationError("El contenido incluye caracteres no permitidos en XML.")
    tipo = infer_type(row)
    if tipo not in SUPPORTED_TYPES:
        raise ValidationError(f"Tipo no soportado: {tipo}. Usa mc, ma, tf, short, blank o essay.")
    if not row.get("pregunta"):
        raise ValidationError("Falta el texto de 'pregunta'.")
    if tipo == "blank" and row["pregunta"].count("{{respuesta}}") != 1:
        raise ValidationError("blank requiere exactamente un marcador {{respuesta}} en 'pregunta'.")
    if tipo != "blank" and "{{respuesta}}" in row["pregunta"]:
        raise ValidationError("Usa tipo blank para el marcador {{respuesta}}.")
    identifier = row.get("id") or f"item_{index:04d}"
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", identifier):
        raise ValidationError("El id debe comenzar con una letra o _, y usar letras ASCII, números, _, . o -.")
    try:
        points = float(row.get("puntos") or "1")
        if not math.isfinite(points) or points <= 0:
            raise ValueError
    except ValueError as exc:
        raise ValidationError("'puntos' debe ser un número mayor que cero (decimal con punto).") from exc
    options = {k: row.get(k, "") for k in OPTION_KEYS}
    correcta = row.get("correcta", "")
    answers = normalize_correct_answers(tipo, correcta)
    alternatives = row.get("respuestas_aceptadas", "")
    feedback = {k: row.get(k, "") for k in FEEDBACK_KEYS}
    if alternatives:
        if tipo not in {"short", "blank"}:
            raise ValidationError("'respuestas_aceptadas' solo se utiliza con short o blank.")
        try:
            values = json.loads(alternatives)
        except json.JSONDecodeError as exc:
            raise ValidationError("'respuestas_aceptadas' debe ser una lista JSON de textos.") from exc
        if not isinstance(values, list) or not values or any(not isinstance(v, str) or not v.strip() for v in values):
            raise ValidationError("'respuestas_aceptadas' debe contener textos no vacíos.")
        answers = list(dict.fromkeys(answers + [v.strip() for v in values]))
        for value in answers:
            if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", value):
                raise ValidationError("Una respuesta aceptada incluye caracteres no permitidos en XML.")
    if tipo == "tf":
        if options["c"] or options["d"]:
            raise ValidationError("tf solo admite las opciones a=Verdadero y b=Falso.")
        for key, allowed in (("a", {"verdadero", "true", "v"}), ("b", {"falso", "false", "f"})):
            if options[key] and options[key].lower() not in allowed:
                raise ValidationError("En tf deja las opciones vacías o usa a=Verdadero y b=Falso.")
        options = {"a": "Verdadero", "b": "Falso", "c": "", "d": ""}
    if tipo in {"mc", "ma", "tf"}:
        if sum(bool(v) for v in options.values()) < 2:
            raise ValidationError("Se requieren al menos dos opciones no vacías.")
        if not answers:
            raise ValidationError("Falta al menos una respuesta en 'correcta'.")
        if len(set(answers)) != len(answers):
            raise ValidationError("Hay respuestas correctas repetidas.")
        if tipo in {"mc", "tf"} and len(answers) != 1:
            raise ValidationError("mc y tf requieren una sola respuesta correcta; usa ma para selección múltiple.")
        if any(a not in options or not options[a] for a in answers):
            raise ValidationError("Cada respuesta correcta debe apuntar a una opción no vacía (a, b, c o d).")
    else:
        if any(options.values()):
            raise ValidationError("short, blank y essay no utilizan opciones a, b, c o d.")
        if tipo in {"short", "blank"} and not answers:
            raise ValidationError("short y blank requieren 'correcta' o 'respuestas_aceptadas'.")
        if tipo == "essay" and (correcta or feedback["feedback_correcta"] or feedback["feedback_incorrecta"]):
            raise ValidationError("essay se califica manualmente: deja correcta y feedback de acierto/error vacíos; usa feedback general.")
    for key in OPTION_KEYS:
        if feedback[f"feedback_{key}"] and (tipo not in {"mc", "ma", "tf"} or not options[key]):
            raise ValidationError(f"feedback_{key} requiere una opción {key} existente.")
    return Question(identifier, row.get("titulo") or f"Pregunta {index}", tipo,
                    row["pregunta"], options, answers, points, feedback)
