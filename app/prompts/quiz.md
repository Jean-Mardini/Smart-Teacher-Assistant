Create a quiz from the document.

Return ONLY valid JSON matching this schema:
{
  "quiz": [
    {
      "type": "mcq|short_answer",
      "question": "string",
      "options": ["A. option text", "B. option text", "C. option text", "D. option text"],
      "answer_index": 0,
      "answer_text": "the correct answer text",
      "explanation": "a clear explanation based on the document",
      "difficulty": "easy|medium|hard",
      "source_refs": ["Section heading > short clue"]
    }
  ]
}

Rules:
- Generate exactly {N_QUESTIONS} questions.
- Mix difficulties: ~40% easy, 40% medium, 20% hard.
- Use ONLY document info, no outside knowledge.
- Every question MUST include source_refs.
- Keep each question directly supported by the provided text.

For MCQ questions:
- Provide exactly 4 options.
- Each option MUST start with a letter label:
  A. ...
  B. ...
  C. ...
  D. ...
- answer_index must correspond to the correct option (0=A, 1=B, 2=C, 3=D).
- Include answer_text as the full correct option text.

For short_answer questions:
- Set options to [].
- Do NOT include answer_index.
- Provide answer_text only.

- No extra keys.
- JSON only.

STRICT RULES:
- Use ONLY explicit document content.
- DO NOT infer or expand beyond the text.
- Every question must be directly traceable to the document.
