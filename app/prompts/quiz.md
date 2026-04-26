Create a quiz from the document.

Return ONLY valid JSON matching this schema:
{
  "quiz": [
    {
      "type": "mcq|short_answer|true_false",
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
- The teacher set this quiz to be worth **{TOTAL_POINTS}** marks in total (you do not put points in JSON; only follow counts and difficulty).
- Generate exactly **{N_MCQ}** questions with `"type": "mcq"`, exactly **{N_TF}** with `"type": "true_false"`, and exactly **{N_SHORT}** with `"type": "short_answer"` (total **{N_TOTAL}**). Do not include any other types.
- Mix difficulties across the whole set: roughly ~40% easy, 40% medium, 20% hard (approximate counts per type).
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

For true_false questions:
- Phrase the question as a clear declarative statement (students decide if it is true or false).
- Set options to exactly: ["A. True", "B. False"] (same spelling and labels).
- Set answer_index to 0 if the statement is true, 1 if false.
- Set answer_text to either "A. True" or "B. False" to match answer_index.

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
