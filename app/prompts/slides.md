Create slide content ONLY from the provided document.

Return ONLY valid JSON matching this schema:
{
  "title": "string",
  "slides": [
    {"slide_title":"string","bullets":["string"],"speaker_notes":"string","image_refs":["image_id"]}
  ]
}

STRICT RULES:
- Use ONLY explicit information found in the document.
- DO NOT add external knowledge.
- DO NOT invent concepts not mentioned in the text.
- Generate exactly {N_SLIDES} slides.
- Each slide MUST contain:
  - a non-empty slide_title
  - 3-5 concise bullets
- Do NOT create empty slides.
- If the document is short, split the available information into smaller factual bullets instead of writing only one long sentence.
- Do not leave a slide with only one bullet unless the document is completely empty.
- Slides should follow a logical presentation structure:
  Introduction -> Overview -> Methods -> Results/Outputs -> Conclusion.
- If the document has few sections, split information across slides logically.
- If image captions or image descriptions contain important information, include that information in the relevant slide bullets or speaker notes.
- If the input includes image identifiers such as `[image_id]`, add the relevant IDs to `image_refs` for slides that should display those images.
- Use only image IDs that appear in the provided document text.
- No extra keys.
- JSON only.
