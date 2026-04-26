Create slide content ONLY from the provided document.

PRESENTATION TEMPLATE (tone, density, and slide flow — apply to titles, bullets, and speaker notes):
{TEMPLATE_INSTRUCTIONS}

Return ONLY valid JSON matching this schema:
{
  "title": "string",
  "slides": [
    {
      "slide_title": "string",
      "subtitle": "string",
      "bullets": ["string"],
      "speaker_notes": "string",
      "image_refs": ["image_id"],
      "layout": "split_text_left|split_text_right|fullwidth_cards|grid_quad|grid_triple|highlight_feature|comparison|process_flow|image_dominant"
    }
  ]
}

STRICT RULES:
- Use ONLY explicit information found in the document.
- DO NOT add external knowledge.
- DO NOT invent concepts not mentioned in the text.
- Generate exactly {N_SLIDES} slides.
- Do NOT create empty slides.

VISUAL CONTRACT (PPTX export — DEMO LESSON style):
- **Header band**: small **DEMO LESSON** label + **numbered section title** + **subtitle** (definition / scope line).
- **Main area** (default export): **visual / diagram on the left** and **rounded card with bullets on the right** — keep bullets tight; put depth in speaker notes.
- **Rare variant**: set ``layout`` to ``grid_triple`` only when you truly want **three equal topic cards** in one row (same ``**Keyword** — explanation`` pattern).
- **Hero imagery**: attach real document figures where possible; generated art fills gaps so slides are never empty.
- **image_refs**: attach the best **document** `image_id` whenever it supports the slide.

ON-SLIDE VS SPEAKER NOTES (priority: teach with examples):
- **slide_title**: short headline (**about 4–10 words**), specific to the document.
- **subtitle**: **required on every slide** — one line (**about 12–26 words**) that frames the slide; must not duplicate the title wording; may name the scope or audience when the source allows.
- **bullets**: **3 to 5** items. Each line is **one teaching point** (**about 12–28 words**): still one scannable line, but include **clear definition + short hook** after the em dash when the document gives you material. Prefer **`**Keyword** — explanation`** (em dash, keyword bold). If the source names a **case, number, named study, or quoted scenario**, you may tuck a **brief** fragment of it into the explanation (never a full paragraph). **Do not** label bullets “Step 1”, “Step 2”, etc.
- **speaker_notes**: **130–240 words** — this is where most **detail** lives: **explain** each bullet, add **why it matters**, and include **examples**.
  - **Examples are required when the document contains any** (case studies, scenarios, numbers, comparisons, quotes, figure takeaways): **quote or paraphrase them here** and tie them to the bullets.
  - If the document truly has **no** illustrative material for a slide, say so briefly and deepen with **step-by-step oral reasoning** grounded only in the text (still no invented facts).
  - Aim for **at least two distinct illustrative beats** per slide when the source supports it (e.g. one scenario + one implication), otherwise **one** solid example minimum.
  - End with a **transition** cue to the next slide. No filler.

LAYOUT FIELD (informational — export maps layouts to DEMO LESSON structures):
- You may set `layout` to any id in the schema for documentation; export will rotate **split_text_left**, **split_text_right**, **fullwidth_cards**, **grid_quad**, **grid_triple**, **highlight_feature**, **comparison**, **process_flow**, and **image_dominant** so adjacent slides do not repeat.
- Prefer **one** `image_refs` entry per slide when a document image supports the point; missing visuals are filled automatically for export — still describe what belongs on-slide in bullets and notes.

STRUCTURE:
- Slides should follow a logical flow (e.g. Introduction → Overview → Methods → Results → Conclusion) when the material supports it.
- If image captions or descriptions matter, weave them into bullets or speaker notes and reference the image id when the figure should appear on that slide.
- Use only image IDs that appear in the provided document text.

- Only the keys shown in the schema (plus `layout` when used). No other extra keys.
- JSON only.
