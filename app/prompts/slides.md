Create slide content ONLY from the provided document.

Return ONLY valid JSON matching this schema:
{
  "title": "string",
  "slides": [
    {"slide_title":"string","bullets":["string"],"speaker_notes":"string"}
  ]
}

STRICT RULES:
- Use ONLY explicit information found in the document.
- DO NOT add external knowledge.
- DO NOT invent concepts not mentioned in the text.

- Generate exactly {N_SLIDES} slides.
- Each slide MUST contain:
  - a non-empty slide_title
  - 3–5 concise bullets
- Do NOT create empty slides.

- Slides should follow a logical presentation structure:
  Introduction → Overview → Methods → Results/Outputs → Conclusion.

- If the document has few sections, split information across slides logically.

- No extra keys.
- JSON only.