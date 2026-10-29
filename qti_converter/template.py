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
        "titulo": "Ejemplo respuesta corta",
        "tipo": "short",
        "pregunta": "Escribe la palabra hola.",
        "a": "",
        "b": "",
        "c": "",
        "d": "",
        "correcta": "hola",
        "feedback": "La respuesta esperada es hola.",
    },
    {
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
        "titulo": "Ejemplo ensayo",
        "tipo": "essay",
        "pregunta": "Explica con tus palabras que es la fotosintesis.",
        "a": "",
        "b": "",
        "c": "",
        "d": "",
        "correcta": "",
        "feedback": "Respuesta abierta para revision manual.",
    }
]


def write_template(destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    with destination.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=TEMPLATE_HEADERS)
        writer.writeheader()
        writer.writerows(TEMPLATE_ROWS)
    return destination
