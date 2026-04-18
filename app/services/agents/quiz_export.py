"""Export helpers for quiz outputs."""

from __future__ import annotations

from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom


def _strip_option_label(text: str) -> str:
    text = (text or "").strip()
    if len(text) >= 3 and text[1:3] == ". " and text[0].isalpha():
        return text[3:].strip()
    return text


def _append_text_node(parent: Element, tag: str, text: str, text_type: str = "html") -> Element:
    node = SubElement(parent, tag, {"format": text_type})
    text_node = SubElement(node, "text")
    text_node.text = text or ""
    return node


def _append_answer(parent: Element, text: str, fraction: str, feedback: str = "") -> None:
    answer = SubElement(parent, "answer", {"fraction": fraction, "format": "html"})
    answer_text = SubElement(answer, "text")
    answer_text.text = text or ""
    feedback_node = SubElement(answer, "feedback", {"format": "html"})
    feedback_text = SubElement(feedback_node, "text")
    feedback_text.text = feedback or ""


def _format_general_feedback(item: dict) -> str:
    explanation = (item.get("explanation") or "").strip()
    source_refs = [ref.strip() for ref in item.get("source_refs", []) if isinstance(ref, str) and ref.strip()]

    if not source_refs:
        return explanation

    refs_text = "<br/>".join(source_refs)
    if explanation:
        return f"{explanation}<br/><br/><strong>Source refs:</strong><br/>{refs_text}"
    return f"<strong>Source refs:</strong><br/>{refs_text}"


def _append_tags(parent: Element, source_refs: list[str]) -> None:
    if not source_refs:
        return

    tags = SubElement(parent, "tags")
    for ref in source_refs:
        tag = SubElement(tags, "tag")
        text = SubElement(tag, "text")
        text.text = ref


def quiz_to_moodle_xml(quiz: list[dict], category: str = "Smart Teacher Assistant") -> str:
    root = Element("quiz")

    category_question = SubElement(root, "question", {"type": "category"})
    category_tag = SubElement(category_question, "category")
    category_text = SubElement(category_tag, "text")
    category_text.text = f"$course$/{category}"

    for index, item in enumerate(quiz, start=1):
        q_type = item.get("type", "mcq")
        moodle_type = "multichoice" if q_type == "mcq" else "shortanswer"
        question = SubElement(root, "question", {"type": moodle_type})

        name = SubElement(question, "name")
        name_text = SubElement(name, "text")
        name_text.text = f"{category} Q{index}"

        _append_text_node(question, "questiontext", item.get("question", ""))
        _append_text_node(question, "generalfeedback", _format_general_feedback(item))
        _append_tags(
            question,
            [ref.strip() for ref in item.get("source_refs", []) if isinstance(ref, str) and ref.strip()],
        )

        if moodle_type == "multichoice":
            single = SubElement(question, "single")
            single.text = "true"
            shuffle = SubElement(question, "shuffleanswers")
            shuffle.text = "true"
            ans_num = SubElement(question, "answernumbering")
            ans_num.text = "abc"

            correct_index = item.get("answer_index", 0)
            explanation = item.get("explanation", "")
            for option_index, option in enumerate(item.get("options", [])):
                fraction = "100" if option_index == correct_index else "0"
                feedback = explanation if option_index == correct_index else ""
                _append_answer(question, _strip_option_label(option), fraction, feedback)
        else:
            use_case = SubElement(question, "usecase")
            use_case.text = "0"
            _append_answer(question, item.get("answer_text", ""), "100", item.get("explanation", ""))

    pretty_xml = minidom.parseString(tostring(root, encoding="utf-8")).toprettyxml(indent="  ")
    return pretty_xml
