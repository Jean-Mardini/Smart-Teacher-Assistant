// Turns a generated quiz into QA rubric rows and a teacher key for the Grading page.

export type QuizQuestionLike = {
  type?: string
  question?: string
  options?: string[]
  answer_index?: number | null
  answer_text?: string | null
  explanation?: string
  points?: number
}

export type QaRubricItem = {
  item_origin: 'teacher_key'
  name: string
  description: string
  points: number
  grounding: '' | 'ai' | 'reference' | 'hybrid'
  expected_answer: string
  mode: 'exact' | 'conceptual'
}

const LETTERS = 'ABCDEFGH'

function hasChoices(q: QuizQuestionLike): boolean {
  return (
    (q.type === 'mcq' || q.type === 'true_false') &&
    Array.isArray(q.options) &&
    q.options.length > 0 &&
    typeof q.answer_index === 'number' &&
    q.answer_index >= 0 &&
    q.answer_index < q.options.length
  )
}

function correctLetter(q: QuizQuestionLike): string {
  return LETTERS[q.answer_index as number] ?? ''
}

function questionPoints(q: QuizQuestionLike): number {
  const p = Number(q.points)
  return Number.isFinite(p) && p > 0 ? Math.round(p) : 1
}

export function quizQuestionsToRubricItems(questions: QuizQuestionLike[]): QaRubricItem[] {
  return questions.map((q, i) => {
    const text = (q.question || '').trim()
    if (hasChoices(q)) {
      const options = (q.options || []).join('\n')
      return {
        item_origin: 'teacher_key',
        name: `Q${i + 1}`,
        description: options ? `${text}\n${options}` : text,
        points: questionPoints(q),
        grounding: '',
        expected_answer: correctLetter(q),
        mode: 'exact',
      }
    }
    return {
      item_origin: 'teacher_key',
      name: `Q${i + 1}`,
      description: text,
      points: questionPoints(q),
      grounding: 'reference',
      expected_answer: (q.answer_text || '').trim(),
      mode: 'conceptual',
    }
  })
}

export function buildTeacherKeyFromQuiz(questions: QuizQuestionLike[], title?: string | null): string {
  const lines: string[] = []
  if (title && title.trim()) lines.push(title.trim(), '')
  questions.forEach((q, i) => {
    lines.push(`Q${i + 1}. ${(q.question || '').trim()}`)
    if (hasChoices(q)) {
      for (const opt of q.options || []) lines.push(opt)
      const optText = (q.options || [])[q.answer_index as number] || ''
      lines.push(`Answer: ${optText || correctLetter(q)}`)
    } else {
      lines.push(`Answer: ${(q.answer_text || '').trim()}`)
    }
    if (q.explanation && q.explanation.trim()) lines.push(`Explanation: ${q.explanation.trim()}`)
    lines.push('')
  })
  return lines.join('\n').trim()
}

export function rubricPointsSum(items: { points?: number }[]): number {
  return items.reduce((sum, item) => sum + (Number(item.points) || 0), 0)
}
