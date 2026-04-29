/** Payload from ``POST /generate-slides`` — mirrors backend ``run_live_slides_json``. */

export type LiveSlideSpec = {
  title: string
  bullets: string[]
  image_prompt?: string
  type?: string
  layout?: string
  /** PNG (or JPEG) ``data:image/...;base64,...`` — required for live preview & export */
  image: string
  use_icons?: boolean
  icon?: string | null
}

export type LiveSlidesResponse = {
  deck_title: string
  slides: LiveSlideSpec[]
  warnings?: string[]
}
