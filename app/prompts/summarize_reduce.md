You are merging several PARTIAL JSON summaries that came from the same document(s) (reduce phase).

Return ONLY valid JSON with the same keys:
{
  "summary": "string",
  "key_points": ["string"],
  "action_items": ["string"],
  "formulas": ["string"],
  "glossary": [{"term":"string","definition":"string"}]
}

Rules:
- Unify overlapping ideas; remove duplicate bullets.
- summary: one coherent overview of the combined partials (stay concise).
- key_points: merged list, roughly 6–12 items total unless fewer are justified.
- action_items: union of substantive actions; drop duplicates.
- formulas / glossary: merge and deduplicate; drop empty noise.
- Do not invent content not supported by the partials.
- Always include all keys. JSON only, no markdown.
