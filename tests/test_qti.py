"""Regression tests evaluate exported scoring/feedback, not just XML existence."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from pathlib import Path

from qti_converter.canvas_qti12 import QTI12_NS
from qti_converter.qti_builder import QTI_NS, analyze_csv, build_qti_package, create_question_xml
from qti_converter.questions import ValidationError, read_questions, validate_question
from qti_converter.template import TEMPLATE_HEADERS, write_template


def local(node):
    return node.tag.rsplit("}", 1)[-1]


def evaluate21(item, answer):
    values = {"RESPONSE": answer}
    declared = {n.get("identifier") for n in item if local(n) in {"responseDeclaration", "outcomeDeclaration"}}
    for node in item.findall(f"{{{QTI_NS}}}outcomeDeclaration"):
        default = node.find(f"{{{QTI_NS}}}defaultValue/{{{QTI_NS}}}value")
        values[node.get("identifier")] = float(default.text) if default is not None else None
    correct = [n.text for n in item.findall(f"{{{QTI_NS}}}responseDeclaration/{{{QTI_NS}}}correctResponse/{{{QTI_NS}}}value")]
    multiple = item.find(f"{{{QTI_NS}}}responseDeclaration").get("cardinality") == "multiple"

    def expression(node):
        tag = local(node)
        if tag == "variable":
            assert node.get("identifier") in declared
            return values[node.get("identifier")]
        if tag == "correct":
            return set(correct) if multiple else correct[0]
        if tag == "baseValue":
            return float(node.text) if node.get("baseType") == "float" else node.text
        if tag == "or":
            return any(expression(n) for n in node)
        left, right = (expression(n) for n in node)
        if tag == "match":
            return left is not None and right is not None and left == right
        if tag == "member":
            return right is not None and left in right
        if tag == "stringMatch":
            return left is not None and str(left).lower() == str(right).lower()
        raise AssertionError(tag)

    def execute(nodes):
        for node in nodes:
            if local(node) == "setOutcomeValue":
                assert node.get("identifier") in declared
                values[node.get("identifier")] = expression(node[0])
            elif local(node) == "responseCondition":
                for branch in node:
                    if local(branch) == "responseElse":
                        execute(branch)
                        break
                    if expression(branch[0]):
                        execute(list(branch)[1:])
                        break
            else:
                raise AssertionError(local(node))
    execute(item.find(f"{{{QTI_NS}}}responseProcessing"))
    feedback = ["".join(n.itertext()) for n in item.findall(f"{{{QTI_NS}}}modalFeedback")
                if values[n.get("outcomeIdentifier")] == n.get("identifier")]
    return values["SCORE"], feedback


def evaluate12(item, answer):
    score = None if item.find(".//qtimetadatafield[fieldentry='essay_question']") is not None else 0
    feedback = []
    def expression(node):
        tag = local(node)
        if tag == "other":
            return True
        if tag == "and":
            return all(expression(n) for n in node)
        if tag == "or":
            return any(expression(n) for n in node)
        if tag == "not":
            return not expression(node[0])
        if tag == "varequal":
            if isinstance(answer, set):
                return node.text in answer
            if answer is None:
                return False
            return str(answer).lower() == node.text.lower() if node.get("case") == "No" else answer == node.text
        raise AssertionError(tag)
    for condition in item.findall("resprocessing/respcondition"):
        if not expression(condition.find("conditionvar")[0]):
            continue
        for node in condition:
            if local(node) == "setvar":
                score = float(node.text)
            if local(node) == "displayfeedback":
                target = item.find(f"itemfeedback[@ident='{node.get('linkrefid')}']")
                assert target is not None, "Dangling feedback reference"
                feedback.append("".join(target.itertext()))
        if condition.get("continue") == "No":
            break
    return score, feedback


class QTITests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.addCleanup(self.temporary.cleanup)

    def csv(self, rows, delimiter=","):
        path = self.root / "questions.csv"
        with path.open("w", encoding="utf-8-sig", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=TEMPLATE_HEADERS, delimiter=delimiter)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def question(self, **changes):
        row = dict(tipo="mc", pregunta="¿Capital?", a="París", b="Madrid", correcta="a",
                   feedback="General", feedback_correcta="Bien", feedback_incorrecta="Revisa",
                   feedback_a="Sobre París", feedback_b="Sobre Madrid", puntos="2.5")
        row.update(changes)
        return read_questions(self.csv([row]))[0]

    def both(self, question):
        from qti_converter.canvas_qti12 import create_assessment
        q12 = create_assessment([question], "Examen").find("assessment/section/item")
        return [("2.1", create_question_xml(question), evaluate21, question.points),
                ("1.2", q12, evaluate12, 100)]

    def test_choice_scoring_and_combined_feedback(self):
        for version, item, evaluate, full in self.both(self.question()):
            with self.subTest(version=version):
                self.assertEqual(evaluate(item, "a"), (full, ["General", "Bien", "Sobre París"]) if version == "2.1" else (full, ["General", "Sobre París", "Bien"]))
                score, feedback = evaluate(item, "b")
                self.assertEqual(score, 0)
                self.assertCountEqual(feedback, ["General", "Revisa", "Sobre Madrid"])
                self.assertEqual(evaluate(item, None)[0], 0)

    def test_multiple_answers_are_exact_set(self):
        q = self.question(tipo="ma", c="Roma", correcta="a,c")
        for version, item, evaluate, full in self.both(q):
            with self.subTest(version=version):
                self.assertEqual(evaluate(item, {"a", "c"})[0], full)
                for answer in ({"a"}, {"a", "b", "c"}, set(), None):
                    self.assertEqual(evaluate(item, answer)[0], 0)

    def test_short_and_blank_accept_alternatives_and_literal_commas(self):
        for tipo in ("short", "blank"):
            q = self.question(tipo=tipo, pregunta="Ciudad: {{respuesta}}." if tipo == "blank" else "Ciudad?",
                              a="", b="", correcta="Quito, Ecuador", respuestas_aceptadas=json.dumps(["Quito"]),
                              feedback_a="", feedback_b="")
            for version, item, evaluate, full in self.both(q):
                with self.subTest(tipo=tipo, version=version):
                    for answer in ("Quito, Ecuador", "QUITO"):
                        self.assertEqual(evaluate(item, answer)[0], full)
                    for answer in ("Ecuador", "", None):
                        self.assertEqual(evaluate(item, answer)[0], 0)
                    if version == "2.1":
                        self.assertEqual(len(item.findall(f".//{{{QTI_NS}}}correctResponse/{{{QTI_NS}}}value")), 1)

    def test_blank_interaction_is_in_place(self):
        item = create_question_xml(self.question(tipo="blank", pregunta="Antes {{respuesta}} después.", a="", b="",
                                                correcta="texto", feedback_a="", feedback_b=""))
        paragraph = item.find(f"{{{QTI_NS}}}itemBody/{{{QTI_NS}}}p")
        self.assertEqual(paragraph.text, "Antes ")
        self.assertEqual(local(paragraph[0]), "textEntryInteraction")
        self.assertEqual(paragraph[0].tail, " después.")

    def test_canvas12_choice_importer_can_read_every_scoring_condition(self):
        # External contract: Instructure ChoiceInteraction#scoring_data reads
        # varequal.content for every respcondition that contains a setvar.
        from qti_converter.canvas_qti12 import create_assessment
        questions = []
        for index in range(20):
            questions.append(self.question(id=f"ERA1_P{index + 1:02d}", correcta="abcd"[index % 4],
                                           c="Roma", d="Berlín", puntos="0.5",
                                           feedback_a="", feedback_b=""))
        questions.append(self.question(tipo="tf", a="", b="", correcta="falso"))
        assessment = create_assessment(questions, "Banco realista")
        for item, question in zip(assessment.findall("assessment/section/item"), questions):
            with self.subTest(identifier=question.identifier):
                scores = []
                for rule in item.findall("resprocessing/respcondition"):
                    score = rule.find("setvar")
                    if score is not None:
                        # This dereference raised for the former <other/> zero-score rule.
                        answer = rule.find(".//varequal").text
                        scores.append((answer, float(score.text)))
                self.assertEqual(scores, [(question.answers[0], 100)])

    def test_canvas12_fillblank_importer_recognizes_text_alternatives(self):
        from qti_converter.canvas_qti12 import create_assessment
        for tipo in ("short", "blank"):
            question = self.question(tipo=tipo, pregunta="Capital: {{respuesta}}." if tipo == "blank" else "Capital?",
                                     a="", b="", correcta="Quito", respuestas_aceptadas='["San Francisco de Quito"]',
                                     feedback_a="", feedback_b="")
            item = create_assessment([question], "Texto").find("assessment/section/item")
            # External contract: FillBlankInteraction.matches excludes terminal other,
            # and match_and_answers reads only direct conditionvar/varequal.
            for rule in item.findall("resprocessing/respcondition"):
                if rule.find("conditionvar/other") is not None:
                    self.assertEqual(rule.get("continue"), "Yes")
            answers = [rule.find("conditionvar/varequal").text
                       for rule in item.findall("resprocessing/respcondition") if rule.find("setvar") is not None]
            self.assertEqual(answers, question.answers)

    def test_canvas12_blank_preserves_text_before_and_after_input(self):
        from qti_converter.canvas_qti12 import create_assessment
        question = self.question(tipo="blank", pregunta="Antes {{respuesta}} después.",
                                 a="", b="", correcta="texto", feedback_a="", feedback_b="")
        presentation = create_assessment([question], "Hueco").find("assessment/section/item/presentation")
        self.assertEqual([local(n) for n in presentation], ["material", "response_str", "material"])
        self.assertEqual(presentation[0].find("mattext").text, "Antes ")
        self.assertEqual(presentation[2].find("mattext").text, " después.")

    def test_essay_is_not_automatically_scored(self):
        q = self.question(tipo="essay", a="", b="", correcta="", feedback_a="", feedback_b="",
                          feedback_correcta="", feedback_incorrecta="")
        for version, item, evaluate, _ in self.both(q):
            with self.subTest(version=version):
                self.assertEqual(evaluate(item, "Mi ensayo"), (None, ["General"]))

    def test_true_false_normalizes_and_scores(self):
        q = self.question(tipo="tf", a="", b="", correcta="Falso")
        self.assertEqual(q.options["a"], "Verdadero")
        for _, item, evaluate, full in self.both(q):
            self.assertEqual(evaluate(item, "b")[0], full)
            self.assertEqual(evaluate(item, "a")[0], 0)

    def test_invalid_rows_are_rejected_by_analysis_and_build(self):
        cases = [dict(correcta="d"), dict(correcta="a,b"), dict(correcta="a,a"), dict(b=""),
                 dict(tipo="tf", a="Sí"), dict(tipo="upload"), dict(puntos="nan"), dict(puntos="inf"),
                 dict(puntos="0"), dict(puntos="-1"), dict(pregunta=""), dict(id="../outside"),
                 dict(tipo="blank", pregunta="Sin marcador", a="", b="", correcta="Quito"),
                 dict(tipo="blank", pregunta="{{respuesta}} y {{respuesta}}", a="", b=""),
                 dict(tipo="short", a="", b="", correcta="", feedback_a="", feedback_b=""),
                 dict(tipo="short", a="", b="", respuestas_aceptadas='[1]', feedback_a="", feedback_b=""),
                 dict(tipo="short", a="", b="", respuestas_aceptadas='["\\u0000"]', feedback_a="", feedback_b=""),
                 dict(feedback="Texto\x00inválido")]
        for changes in cases:
            row = dict(tipo="mc", pregunta="¿Capital?", a="París", b="Madrid", correcta="a") | changes
            path = self.csv([row])
            with self.subTest(changes=changes):
                with self.assertRaises(ValidationError):
                    analyze_csv(path)
                with self.assertRaises(ValidationError):
                    build_qti_package(path, "Examen", self.root / "exports")

    def test_csv_dialects_and_special_characters(self):
        for delimiter in (",", ";"):
            path = self.csv([dict(tipo="short", pregunta='¿Qué significa "A&B"?\nExplica <sí> 😀.', correcta="Quito, Ecuador", feedback="Línea 1\nLínea 2")], delimiter)
            self.assertEqual(analyze_csv(path).valid_question_count, 1)
            result = build_qti_package(path, "Tildes & símbolos", self.root)
            item = ET.parse(result.output_dir / "item_0001.xml").getroot()
            self.assertIn("😀", "".join(item.itertext()))

    def test_duplicate_ids_and_malformed_csv(self):
        path = self.csv([dict(id="repetido", pregunta="Una", correcta="a"), dict(id="repetido", pregunta="Otra", correcta="b")])
        with self.assertRaisesRegex(ValidationError, "duplicado"):
            analyze_csv(path)
        for text in ('pregunta,correcta,Correcta\nHola,a,b', 'pregunta,correcta\nHola,a,extra',
                     'pregunta,correcta\n"Sin cierre,a', 'pregunta,correcta\nHola'):
            path.write_text(text, encoding="utf-8")
            with self.assertRaises(ValidationError):
                analyze_csv(path)

    def test_template_and_package_references(self):
        path = write_template(self.root / "template.csv")
        self.assertEqual(analyze_csv(path).valid_question_count, 6)
        for version in ("1.2", "2.1"):
            result = build_qti_package(path, "Plantilla", self.root, version)
            with zipfile.ZipFile(result.zip_path) as archive:
                self.assertIsNone(archive.testzip())
                names = set(archive.namelist())
                for name in names:
                    tree = ET.fromstring(archive.read(name))
                    for node in tree.iter():
                        if "href" in node.attrib:
                            self.assertIn(node.get("href"), names)
                if version == "2.1":
                    for name in names - {"assessmentTest.xml", "imsmanifest.xml"}:
                        item = ET.fromstring(archive.read(name))
                        children = [local(n) for n in item]
                        if "modalFeedback" in children:
                            self.assertLess(children.index("responseProcessing"), children.index("modalFeedback"))
                else:
                    tree = ET.fromstring(archive.read("assessment.xml"))
                    self.assertEqual(tree.tag, f"{{{QTI12_NS}}}questestinterop")

    def test_invalid_input_does_not_destroy_previous_export(self):
        path = self.csv([dict(tipo="short", pregunta="Ciudad?", correcta="Quito")])
        result = build_qti_package(path, "Anterior", self.root)
        before = result.zip_path.read_bytes()
        path.write_text("pregunta,correcta\n,", encoding="utf-8")
        with self.assertRaises(ValidationError):
            build_qti_package(path, "Anterior", self.root)
        self.assertEqual(result.zip_path.read_bytes(), before)
        self.assertTrue((result.output_dir / "item_0001.xml").exists())


if __name__ == "__main__":
    unittest.main()
