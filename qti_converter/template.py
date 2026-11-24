from __future__ import annotations

import csv
from pathlib import Path


TEMPLATE_HEADERS = [
    "id", "titulo", "tipo", "pregunta", "a", "b", "c", "d", "correcta",
    "respuestas_aceptadas", "puntos", "feedback", "feedback_correcta",
    "feedback_incorrecta", "feedback_a", "feedback_b", "feedback_c", "feedback_d",
]

TEMPLATE_ROWS = [
    {
        "id": "PREG001",
        "titulo": "Ejemplo opcion multiple",
        "tipo": "mc",
        "pregunta": "Cual es la capital de Francia?",
        "a": "Paris",
        "b": "Madrid",
        "c": "Roma",
        "d": "Berlin",
        "correcta": "a",
        "puntos": "2",
        "feedback": "París es la capital de Francia.",
        "feedback_correcta": "Has identificado la capital correctamente.",
        "feedback_incorrecta": "Revisa la diferencia entre las capitales europeas.",
        "feedback_b": "Madrid es la capital de España.",
    },
    {
        "id": "PREG002",
        "titulo": "Ejemplo selección múltiple",
        "tipo": "ma",
        "pregunta": "Selecciona todos los números pares.",
        "a": "2", "b": "3", "c": "4", "d": "5",
        "correcta": "a,c",
        "puntos": "2",
        "feedback": "Los números pares son divisibles por 2.",
        "feedback_correcta": "Seleccionaste exactamente 2 y 4.",
        "feedback_incorrecta": "Debes seleccionar todos los pares y ningún impar.",
    },
    {
        "id": "PREG003",
        "titulo": "Ejemplo verdadero falso",
        "tipo": "tf",
        "pregunta": "La Tierra gira alrededor del Sol.",
        "a": "",
        "b": "",
        "c": "",
        "d": "",
        "correcta": "verdadero",
        "feedback": "Es una afirmacion verdadera.",
    },
    {
        "id": "PREG004",
        "titulo": "Ejemplo espacio en blanco",
        "tipo": "blank",
        "pregunta": "La capital de Ecuador es {{respuesta}}.",
        "correcta": "Quito",
        "respuestas_aceptadas": '["San Francisco de Quito"]',
        "puntos": "1",
        "feedback": "Quito es la capital de Ecuador.",
        "feedback_correcta": "Completaste la oración correctamente.",
        "feedback_incorrecta": "Guayaquil es otra ciudad del país; su capital es Quito.",
    },
    {
        "id": "PREG005",
        "titulo": "Ejemplo ensayo",
        "tipo": "essay",
        "pregunta": "Explica con tus palabras que es la fotosintesis.",
        "a": "",
        "b": "",
        "c": "",
        "d": "",
        "correcta": "",
        "feedback": "Respuesta abierta para revision manual.",
    },
    {
        "id": "PREG006",
        "titulo": "Ejemplo con código Python",
        "tipo": "mc",
        "pregunta": "¿Qué muestra el siguiente código?\n```python\nfor numero in range(3):\n    print(numero)\n```",
        "a": "0, 1, 2", "b": "1, 2, 3", "c": "0, 1, 2, 3",
        "correcta": "a", "puntos": "1",
        "feedback": "range(3) produce los números 0, 1 y 2.",
    }
]


def write_template(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=TEMPLATE_HEADERS)
        writer.writeheader()
        writer.writerows(TEMPLATE_ROWS)
    return destination
