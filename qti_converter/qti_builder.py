from __future__ import annotations

import re
import shutil
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

from qti_converter.questions import (
    OPTION_KEYS, REQUIRED_HEADERS, SUPPORTED_TYPES, Question, ValidationError,
    infer_type, normalize_correct_answers, read_questions, validate_headers,
)

QTI_NS = "http://www.imsglobal.org/xsd/imsqti_v2p1"
ET.register_namespace("", QTI_NS)


@dataclass
class BuildResult:
    exam_title: str
    output_dir: Path
    zip_path: Path
    item_count: int
    warnings: list[str]


@dataclass
class CSVAnalysis:
    path: Path
    valid_question_count: int
    suggested_title: str


def sanitize_name(value: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_-]+", "_", value.strip())
    return safe.strip("_") or "examen_sin_titulo"


def suggest_title_from_path(csv_path: Path) -> str:
    base = csv_path.stem.replace("_", " ").replace("-", " ").strip()
    return " ".join(part.capitalize() for part in base.split()) or "Examen"


def analyze_csv(csv_path: Path) -> CSVAnalysis:
    questions = read_questions(csv_path)
    return CSVAnalysis(csv_path, len(questions), suggest_title_from_path(csv_path))


def sub(parent: ET.Element, name: str, text: str | None = None, **attrs: str) -> ET.Element:
    node = ET.SubElement(parent, f"{{{QTI_NS}}}{name}", attrs)
    node.text = text
    return node


def set_outcome(parent: ET.Element, identifier: str, value: str, base_type: str) -> None:
    sub(sub(parent, "setOutcomeValue", identifier=identifier), "baseValue", value, baseType=base_type)


def feedback_definitions(question: Question) -> list[tuple[str, str, str]]:
    """Separate outcomes allow general, result and option feedback together."""
    return [(key.upper(), key.upper() + "_SHOWN", value)
            for key, value in question.feedback.items() if value]


def create_question_xml(question: Question) -> ET.Element:
    item = ET.Element(f"{{{QTI_NS}}}assessmentItem", {
        "identifier": question.identifier, "title": question.title,
        "adaptive": "false", "timeDependent": "false",
    })
    choice = question.tipo in {"mc", "ma", "tf"}
    response = sub(item, "responseDeclaration", identifier="RESPONSE",
                   cardinality="multiple" if question.tipo == "ma" else "single",
                   baseType="identifier" if choice else "string")
    if question.tipo != "essay":
        correct = sub(response, "correctResponse")
        # Alternative text answers are OR conditions, not a multi-valued single response.
        for value in question.answers if question.tipo == "ma" else question.answers[:1]:
            sub(correct, "value", value)
    score = sub(item, "outcomeDeclaration", identifier="SCORE", cardinality="single", baseType="float",
                normalMaximum=format(question.points, ".15g"))
    if question.tipo != "essay":
        sub(sub(score, "defaultValue"), "value", "0")
    definitions = feedback_definitions(question)
    for outcome, _, _ in definitions:
        sub(item, "outcomeDeclaration", identifier=outcome, cardinality="single", baseType="identifier")
    body = sub(item, "itemBody")
    if question.tipo == "blank":
        before, after = question.text.split("{{respuesta}}")
        paragraph = sub(body, "p", before)
        entry = sub(paragraph, "textEntryInteraction", responseIdentifier="RESPONSE", expectedLength="30")
        entry.tail = after
    else:
        sub(body, "p", question.text)
        if choice:
            interaction = sub(body, "choiceInteraction", responseIdentifier="RESPONSE", shuffle="false",
                              maxChoices="0" if question.tipo == "ma" else "1")
            for key, text in question.options.items():
                if text:
                    sub(sub(interaction, "simpleChoice", identifier=key), "p", text)
        elif question.tipo == "short":
            sub(sub(body, "p"), "textEntryInteraction", responseIdentifier="RESPONSE", expectedLength="30")
        else:
            sub(body, "extendedTextInteraction", responseIdentifier="RESPONSE")
    processing = sub(item, "responseProcessing")
    if question.tipo != "essay":
        condition = sub(processing, "responseCondition")
        yes = sub(condition, "responseIf")
        if question.tipo in {"short", "blank"}:
            expression = sub(yes, "or") if len(question.answers) > 1 else yes
            for answer in question.answers:
                comparison = sub(expression, "stringMatch", caseSensitive="false", substring="false")
                sub(comparison, "variable", identifier="RESPONSE")
                sub(comparison, "baseValue", answer, baseType="string")
        else:
            comparison = sub(yes, "match")
            sub(comparison, "variable", identifier="RESPONSE")
            sub(comparison, "correct", identifier="RESPONSE")
        set_outcome(yes, "SCORE", format(question.points, ".15g"), "float")
        if question.feedback["feedback_correcta"]:
            set_outcome(yes, "FEEDBACK_CORRECTA", "FEEDBACK_CORRECTA_SHOWN", "identifier")
        no = sub(condition, "responseElse")
        set_outcome(no, "SCORE", "0", "float")
        if question.feedback["feedback_incorrecta"]:
            set_outcome(no, "FEEDBACK_INCORRECTA", "FEEDBACK_INCORRECTA_SHOWN", "identifier")
    if question.feedback["feedback"]:
        set_outcome(processing, "FEEDBACK", "FEEDBACK_SHOWN", "identifier")
    for key in OPTION_KEYS:
        if not question.feedback[f"feedback_{key}"]:
            continue
        yes = sub(sub(processing, "responseCondition"), "responseIf")
        comparison = sub(yes, "member" if question.tipo == "ma" else "match")
        if question.tipo == "ma":
            sub(comparison, "baseValue", key, baseType="identifier")
            sub(comparison, "variable", identifier="RESPONSE")
        else:
            sub(comparison, "variable", identifier="RESPONSE")
            sub(comparison, "baseValue", key, baseType="identifier")
        set_outcome(yes, f"FEEDBACK_{key.upper()}", f"FEEDBACK_{key.upper()}_SHOWN", "identifier")
    for outcome, identifier, text in definitions:
        sub(sub(item, "modalFeedback", outcomeIdentifier=outcome, identifier=identifier, showHide="show"), "p", text)
    return item


def create_item_xml(idx: int, title: str, tipo: str, pregunta: str, opciones: dict[str, str],
                    correctas: list[str], feedback: str) -> ET.Element:
    """Compatibility wrapper for callers of the previous XML API."""
    from qti_converter.questions import validate_question
    row = dict(opciones, titulo=title, tipo=tipo, pregunta=pregunta, feedback=feedback,
               correcta=correctas[0] if tipo in {"short", "blank"} and correctas else ",".join(correctas))
    if tipo in {"short", "blank"} and len(correctas) > 1:
        import json
        row["respuestas_aceptadas"] = json.dumps(correctas)
    return create_question_xml(validate_question(row, idx))


def write_xml(root: ET.Element, path: Path) -> None:
    ET.ElementTree(root).write(path, encoding="utf-8", xml_declaration=True)


def create_manifest(test_file: Path, item_files: list[Path], output_dir: Path,
                    qti_version: str = "2.1") -> Path:
    manifest = ET.Element("manifest", {"xmlns": "http://www.imsglobal.org/xsd/imscp_v1p1", "identifier": "manifest01"})
    ET.SubElement(manifest, "organizations")
    resources = ET.SubElement(manifest, "resources")
    test_resource = ET.SubElement(resources, "resource", {
        "identifier": "res_test", "type": "imsqti_test_xmlv2p1" if qti_version == "2.1" else "imsqti_xmlv1p2",
        "href": test_file.name,
    })
    ET.SubElement(test_resource, "file", href=test_file.name)
    for index, item_file in enumerate(item_files, 1):
        resource_id = f"res_item_{index:04d}"
        ET.SubElement(test_resource, "dependency", identifierref=resource_id)
        resource = ET.SubElement(resources, "resource", identifier=resource_id,
                                 type="imsqti_item_xmlv2p1", href=item_file.name)
        ET.SubElement(resource, "file", href=item_file.name)
    manifest_file = output_dir / "imsmanifest.xml"
    write_xml(manifest, manifest_file)
    return manifest_file


def build_qti_package(csv_path: Path, exam_title: str, destination_dir: Path,
                      qti_version: str = "2.1") -> BuildResult:
    if qti_version not in {"1.2", "2.1"}:
        raise ValidationError("El formato QTI debe ser 1.2 o 2.1.")
    if not exam_title.strip():
        raise ValidationError("Debes indicar un título para el examen.")
    if re.search(r"[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff\ufffe\uffff]", exam_title):
        raise ValidationError("El título contiene caracteres no permitidos en XML.")
    questions = read_questions(csv_path)  # Validate before touching any previous export.
    destination_dir = destination_dir.resolve()
    safe_name = sanitize_name(exam_title)
    output_dir = destination_dir / f"QTI{qti_version.replace('.', '')}_{safe_name}"
    zip_path = destination_dir / f"{safe_name}.zip"
    if output_dir.is_symlink() or output_dir.resolve().parent != destination_dir:
        raise ValidationError("La carpeta de salida no puede ser un enlace a otra ubicación.")
    destination_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".qti_", dir=destination_dir) as temporary:
        staging = Path(temporary)
        item_files = []
        if qti_version == "1.2":
            from qti_converter.canvas_qti12 import create_assessment
            test = create_assessment(questions, exam_title)
            test_file = staging / "assessment.xml"
        else:
            test = ET.Element(f"{{{QTI_NS}}}assessmentTest", identifier="Exam01", title=exam_title)
            part = sub(test, "testPart", identifier="Part1", navigationMode="nonlinear", submissionMode="individual")
            section = sub(part, "assessmentSection", identifier="Sec1", title="Preguntas", visible="true")
            sub(section, "itemSessionControl", showFeedback="true", allowReview="true")
            for index, question in enumerate(questions, 1):
                item_file = staging / f"item_{index:04d}.xml"
                write_xml(create_question_xml(question), item_file)
                item_files.append(item_file)
                sub(section, "assessmentItemRef", identifier=f"ref_{index:04d}", href=item_file.name)
            test_file = staging / "assessmentTest.xml"
        write_xml(test, test_file)
        manifest = create_manifest(test_file, item_files, staging, qti_version)
        staged_zip = staging / "package.zip"
        with zipfile.ZipFile(staged_zip, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in [manifest, test_file, *item_files]:
                archive.write(path, path.name)
        # Only replace a generated directory directly under the selected destination.
        if output_dir.exists():
            shutil.rmtree(output_dir)
        output_dir.mkdir()
        for path in [manifest, test_file, *item_files]:
            shutil.copy2(path, output_dir / path.name)
        staged_zip.replace(zip_path)
    warnings = []
    if qti_version == "2.1" and any(any(q.feedback.values()) for q in questions):
        warnings.append("Canvas puede omitir feedback al importar QTI 2.1. Compara con el perfil Canvas QTI 1.2 y revisa la visibilidad de resultados.")
    return BuildResult(exam_title, output_dir, zip_path, len(questions), warnings)
