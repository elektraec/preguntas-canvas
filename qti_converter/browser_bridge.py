"""JSON boundary shared by the browser worker and native regression checks."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

from qti_converter.qti_builder import build_qti_package, suggest_title_from_path
from qti_converter.questions import read_questions


def handle_request(request_json: str) -> str:
    request = json.loads(request_json)
    csv_path = Path(request["input_path"])
    if request["action"] == "analyze":
        questions = read_questions(csv_path)
        result = {
            "count": len(questions),
            "points": sum(q.points for q in questions),
            "types": dict(Counter(q.tipo for q in questions)),
            "suggested_title": suggest_title_from_path(Path(request["filename"])),
            "questions": [
                {"title": q.title, "text": q.text, "tipo": q.tipo,
                 "points": q.points, "answers": q.answers,
                 "feedback_count": sum(bool(v) for v in q.feedback.values())}
                for q in questions[:100]
            ],
        }
    elif request["action"] == "generate":
        package = build_qti_package(csv_path, request["title"], Path(request["destination"]), request["format"])
        result = {"path": str(package.zip_path), "filename": package.zip_path.name,
                  "count": package.item_count, "warnings": package.warnings}
    else:
        raise ValueError("Acción no reconocida.")
    return json.dumps(result, ensure_ascii=False)
