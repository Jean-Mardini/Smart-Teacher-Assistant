You are extracting notes from ONE excerpt of a longer educational document (map phase).

Return ONLY valid JSON matching this schema:
{
  "summary": "string",
  "key_points": ["string"],
  "action_items": ["string"],
  "formulas": ["string"],
  "glossary": [{"term":"string","definition":"string"}]
}

Rules:
- Use only this excerpt. Do not infer beyond it.
- summary: 2–4 sentences on what this fragment covers.
- key_points: 3–6 short bullets, each traceable to the excerpt.
- action_items: use [] unless the excerpt explicitly lists tasks.
- formulas: only math clearly present (e.g. LaTeX OCR lines); else [].
- glossary: [] or at most 2 entries if a term is defined in the excerpt.
- Preserve inline reference markers like [1] only if they appear in the excerpt.
- Always include all keys. JSON only, no markdown.
