from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict, List

from .pipeline import RAGPipeline


# --------------------------------------------------------------------------- #
# Real parsed document loading (Matheos output)
# --------------------------------------------------------------------------- #
def _load_real_parsed_documents() -> List[Dict[str, Any]]:
    """
    Load real parsed document JSON produced by Matheos.

    Lookup order:
      1) Environment variable: MATHEOS_PARSED_JSON
      2) Common local output paths in this project.
    """
    candidates: List[Path] = []

    env_path = os.getenv("MATHEOS_PARSED_JSON")
    if env_path:
        candidates.append(Path(env_path))

    workspace_root = Path(__file__).resolve().parents[3]
    candidates.extend(
        [
            workspace_root / "data" / "parsed_documents" / "parsed_document.json",
            workspace_root / "data" / "parsed_documents" / "parsed_documents.json",
            workspace_root / "app" / "services" / "document_processing" / "output" / "parsed_document.json",
            workspace_root / "app" / "services" / "document_processing" / "output" / "parsed_documents.json",
        ]
    )

    for path in candidates:
        if not path.exists():
            continue

        with path.open("r", encoding="utf-8") as f:
            loaded = json.load(f)

        if isinstance(loaded, dict):
            if isinstance(loaded.get("sections"), list):
                return [loaded]
            if isinstance(loaded.get("documents"), list):
                return loaded["documents"]
        if isinstance(loaded, list):
            return loaded

    joined_candidates = "\n".join(f"  - {p}" for p in candidates)
    raise FileNotFoundError(
        "No real Matheos parsed JSON document found.\n"
        "Set MATHEOS_PARSED_JSON or place a parsed JSON in one of:\n"
        f"{joined_candidates}"
    )


def _build_realistic_questions_from_document(
    document: Dict[str, Any],
    min_questions: int = 5,
) -> List[Dict[str, str]]:
    """
    Build realistic retrieval questions from a real parsed document.

    We avoid synthetic corpus content and generate benchmark prompts from the
    actual section headings present in the parsed document.
    """
    sections = document.get("sections", []) or []
    document_id = str(document.get("document_id") or "")

    templates = [
        "Can you explain the core idea behind {heading}?",
        "What does the section on {heading} mainly discuss?",
        "I need a plain-language summary of {heading}.",
        "Which part of the document covers {heading} in detail?",
        "If I want to review {heading}, where should I look?",
        "What are the key points described under {heading}?",
    ]

    questions: List[Dict[str, str]] = []
    for i, section in enumerate(sections):
        heading = str(section.get("heading") or "").strip()
        section_id = str(section.get("section_id") or "").strip()
        if not heading:
            continue

        template = templates[i % len(templates)]
        questions.append(
            {
                "question": template.format(heading=heading),
                "expected_document_id": document_id,
                "expected_section_id": section_id,
                "expected_section_heading": heading,
            }
        )

        if len(questions) >= max(min_questions, 5):
            break

    if len(questions) < 5:
        raise ValueError(
            "Parsed document does not have enough valid sections to build "
            "at least 5 evaluation questions."
        )

    return questions


def _is_expected_match(chunk: Dict[str, Any], case: Dict[str, str]) -> bool:
    """
    Match by expected document_id plus either section_id or section heading.
    """
    if chunk.get("document_id") != case["expected_document_id"]:
        return False

    expected_section_id = case.get("expected_section_id")
    expected_section_heading = case.get("expected_section_heading")

    if expected_section_id:
        return chunk.get("section_id") == expected_section_id

    if expected_section_heading:
        return chunk.get("section") == expected_section_heading

    return False


def _reciprocal_rank(results: List[Dict[str, Any]], case: Dict[str, str]) -> float:
    for rank, chunk in enumerate(results, start=1):
        if _is_expected_match(chunk, case):
            return 1.0 / rank
    return 0.0


def main() -> None:
    """
    Local retrieval evaluation entrypoint.

    What this measures:
      - Whether retrieval surfaces the expected source chunk/section.
      - Ranking quality via hit@1, hit@3, and MRR.

    What this does NOT measure:
      - Any answer-generation quality, faithfulness, or fluency.
        No generator or LLM output is used here.
    """
    parsed_documents = _load_real_parsed_documents()
    primary_document = parsed_documents[0]
    evaluation_questions = _build_realistic_questions_from_document(primary_document)

    pipeline = RAGPipeline(device="cpu")
    pipeline.index_documents(parsed_documents)
    cases = evaluation_questions

    total_questions = len(cases)
    hit_at_1 = 0
    hit_at_3 = 0
    reciprocal_rank_sum = 0.0

    print("=== Retrieval Evaluation (No Generation) ===")
    print(f"Questions: {total_questions}")
    print()

    for i, case in enumerate(cases, start=1):
        question = case["question"]
        expected_doc = case["expected_document_id"]
        expected_sec_id = case.get("expected_section_id", "")
        expected_heading = case.get("expected_section_heading", "")

        results = pipeline.retrieve_chunks(question, top_k=3)
        rr = _reciprocal_rank(results, case)
        reciprocal_rank_sum += rr

        in_top1 = len(results) > 0 and _is_expected_match(results[0], case)
        in_top3 = any(_is_expected_match(chunk, case) for chunk in results)
        hit_at_1 += int(in_top1)
        hit_at_3 += int(in_top3)

        print(f"[Q{i}] {question}")
        print(
            f"Expected -> doc: {expected_doc}, section_id: {expected_sec_id}, "
            f"section: {expected_heading}"
        )
        if not results:
            print("Retrieved: <no results>")
        else:
            for rank, chunk in enumerate(results, start=1):
                print(
                    f"  #{rank} score={chunk['score']:.4f} "
                    f"doc={chunk.get('document_id')} "
                    f"section_id={chunk.get('section_id')} "
                    f"section={chunk.get('section')} "
                    f"pages={chunk.get('page_start')}-{chunk.get('page_end')}"
                )
        print(f"Hit@1={in_top1}  Hit@3={in_top3}  RR={rr:.4f}")
        print("-" * 72)

    mrr = reciprocal_rank_sum / total_questions if total_questions > 0 else 0.0

    print()
    print("=== Aggregate Metrics ===")
    print(f"total_questions: {total_questions}")
    print(f"hit@1: {hit_at_1}/{total_questions} = {hit_at_1 / total_questions:.4f}")
    print(f"hit@3: {hit_at_3}/{total_questions} = {hit_at_3 / total_questions:.4f}")
    print(f"MRR: {mrr:.4f}")


if __name__ == "__main__":
    main()
