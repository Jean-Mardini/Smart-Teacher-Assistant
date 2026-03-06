from __future__ import annotations

from typing import Iterable, List

import torch
from transformers import (
    AutoModelForSeq2SeqLM,
    AutoTokenizer,
    PreTrainedModel,
    PreTrainedTokenizer,
)

from .retriever import RetrievedChunk


DEFAULT_LLM_MODEL = "google/flan-t5-base"


class AnswerGenerator:
    """
    Responsible for turning retrieved chunks + a user question into an answer
    using a local HuggingFace seq2seq model (default: `google/flan-t5-base`).

    The class is intentionally CPU-friendly: it defaults to running entirely on
    CPU with `float32` weights and conservative generation settings.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_LLM_MODEL,
        device: str = "cpu",
    ) -> None:
        self.model_name: str = model_name
        self.device: str = device

        self.tokenizer: PreTrainedTokenizer = AutoTokenizer.from_pretrained(model_name)
        self.model: PreTrainedModel = AutoModelForSeq2SeqLM.from_pretrained(
            model_name,
            torch_dtype=torch.float32,
        )
        self.model.to(device)
        self.model.eval()

    @staticmethod
    def _format_context(chunks: Iterable[RetrievedChunk]) -> str:
        parts: List[str] = []
        for c in chunks:
            if c.page_end is None or c.page_end == c.page_start:
                pages_str = f"{c.page_start}"
            else:
                pages_str = f"{c.page_start}-{c.page_end}"
            header = f"[Section: {c.section_heading} | Pages: {pages_str}]"
            parts.append(f"{header}\n{c.chunk_text}")
        return "\n\n---\n\n".join(parts)

    def _build_prompt(self, question: str, context_chunks: List[RetrievedChunk]) -> str:
        """
        Construct the prompt according to the project template.
        """
        context_str = self._format_context(context_chunks) if context_chunks else ""

        prompt = (
            "You are answering questions using ONLY the provided context.\n\n"
            f"Context:\n{context_str}\n\n"
            f"Question:\n{question}\n\n"
            "Instructions:\n"
            'If the answer is not contained in the context, reply:\n'
            "\"Answer not found in the document.\"\n\n"
            "Answer:\n"
        )
        return prompt

    @torch.inference_mode()
    def generate_answer(self, question: str, context_chunks: List[RetrievedChunk]) -> str:
        """
        Generate an answer given a question and retrieved context chunks.

        Args:
            question: User question.
            context_chunks: Retrieved chunks providing the grounding context.

        Returns:
            The generated answer text (already stripped).
        """
        prompt = self._build_prompt(question, context_chunks)

        inputs = self.tokenizer(prompt, return_tensors="pt").to(self.device)
        output_ids = self.model.generate(
            **inputs,
            max_new_tokens=200,
            do_sample=False,
        )

        text = self.tokenizer.decode(output_ids[0], skip_special_tokens=True)
        return text.strip()


__all__ = ["AnswerGenerator"]

