"""QTI 1.2 profile with explicit Canvas question types and feedback links.

This profile is an import alternative, not a guarantee of New Quizzes behavior.
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

from qti_converter.questions import OPTION_KEYS, Question

QTI12_NS = "http://www.imsglobal.org/xsd/ims_qtiasiv1p2"
CANVAS_TYPES = {
    "mc": "multiple_choice_question", "ma": "multiple_answers_question",
    "tf": "true_false_question", "short": "short_answer_question",
    "blank": "short_answer_question", "essay": "essay_question",
}


def material(parent: ET.Element, text: str) -> None:
    ET.SubElement(ET.SubElement(parent, "material"), "mattext", texttype="text/plain").text = text


def condition(parent: ET.Element, continue_: str = "Yes") -> tuple[ET.Element, ET.Element]:
    node = ET.SubElement(parent, "respcondition", {"continue": continue_})
    return node, ET.SubElement(node, "conditionvar")


def feedback_link(parent: ET.Element, identifier: str) -> None:
    ET.SubElement(parent, "displayfeedback", feedbacktype="Response", linkrefid=identifier)


def create_assessment(questions: list[Question], title: str) -> ET.Element:
    root = ET.Element("questestinterop", xmlns=QTI12_NS)
    assessment = ET.SubElement(root, "assessment", ident="Exam01", title=title)
    section = ET.SubElement(assessment, "section", ident="root_section")
    for question in questions:
        item = ET.SubElement(section, "item", ident=question.identifier, title=question.title)
        metadata = ET.SubElement(ET.SubElement(item, "itemmetadata"), "qtimetadata")
        for key, value in (("question_type", CANVAS_TYPES[question.tipo]), ("points_possible", format(question.points, ".15g"))):
            field = ET.SubElement(metadata, "qtimetadatafield")
            ET.SubElement(field, "fieldlabel").text = key
            ET.SubElement(field, "fieldentry").text = value
        presentation = ET.SubElement(item, "presentation")
        if question.tipo == "blank":
            before, after = question.text.split("{{respuesta}}")
            material(presentation, before)
        else:
            material(presentation, question.text)
        if question.tipo in {"mc", "ma", "tf"}:
            response = ET.SubElement(presentation, "response_lid", ident="response1",
                                     rcardinality="Multiple" if question.tipo == "ma" else "Single")
            render = ET.SubElement(response, "render_choice")
            for key, text in question.options.items():
                if text:
                    material(ET.SubElement(render, "response_label", ident=key), text)
        else:
            response = ET.SubElement(presentation, "response_str", ident="response1", rcardinality="Single")
            ET.SubElement(ET.SubElement(response, "render_fib"), "response_label", ident="answer1", rshuffle="No")
            if question.tipo == "blank":
                material(presentation, after)
        processing = ET.SubElement(item, "resprocessing")
        ET.SubElement(ET.SubElement(processing, "outcomes"), "decvar", varname="SCORE", vartype="Decimal",
                      minvalue="0", maxvalue="100", defaultval="0")
        feedbacks = {}
        if question.feedback["feedback"]:
            node, expression = condition(processing)
            ET.SubElement(expression, "other")
            feedback_link(node, "general_fb")
            feedbacks["general_fb"] = question.feedback["feedback"]
        for key in OPTION_KEYS:
            if question.feedback[f"feedback_{key}"]:
                node, expression = condition(processing)
                ET.SubElement(expression, "varequal", respident="response1").text = key
                feedback_link(node, f"{key}_fb")
                feedbacks[f"{key}_fb"] = question.feedback[f"feedback_{key}"]
        if question.tipo != "essay":
            # Canvas reads text answers only from a direct conditionvar/varequal.
            # Export each alternative as an independent full-credit condition.
            alternatives = question.answers if question.tipo in {"short", "blank"} else [None]
            for answer in alternatives:
                node, expression = condition(processing, "No")
                if question.tipo == "ma":
                    expression = ET.SubElement(expression, "and")
                    for key, text in question.options.items():
                        if text:
                            target = expression if key in question.answers else ET.SubElement(expression, "not")
                            ET.SubElement(target, "varequal", respident="response1").text = key
                elif answer is not None:
                    ET.SubElement(expression, "varequal", respident="response1", case="No").text = answer
                else:
                    ET.SubElement(expression, "varequal", respident="response1").text = question.answers[0]
                # Answer weights are normalized; points_possible holds the actual score.
                ET.SubElement(node, "setvar", varname="SCORE", action="Set").text = "100"
                if question.feedback["feedback_correcta"]:
                    feedback_link(node, "correct_fb")
                    feedbacks["correct_fb"] = question.feedback["feedback_correcta"]
            # SCORE defaults to zero. A scoring setvar with only <other/> causes
            # ChoiceInteraction#scoring_data to dereference a missing varequal.
            # FillBlankInteraction also excludes <other/> unless continue="Yes".
            node, expression = condition(processing, "Yes")
            ET.SubElement(expression, "other")
            if question.feedback["feedback_incorrecta"]:
                feedback_link(node, "general_incorrect_fb")
                feedbacks["general_incorrect_fb"] = question.feedback["feedback_incorrecta"]
        for identifier, text in feedbacks.items():
            material(ET.SubElement(ET.SubElement(item, "itemfeedback", ident=identifier), "flow_mat"), text)
    return root
