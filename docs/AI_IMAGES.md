# AI images: Nano Banana 2.1 (long videos)

Same `GEMINI_API_KEY` as the voice. The model is pinned to `gemini-nano-banana-2.1`, Google's stable model ID
(October 2026).

## What it makes

1. **3 thumbnail options per long video.** Each one has:
   - our character Max;
   - one big, simple chart drawn by the AI with **no numbers or text** (so it can't invent a figure);
   - **2–3 bold words** added by our own code, so the spelling is always exact.

   You pick one with the 🖼 1 / 2 / 3 buttons in the review. Option 1 is used if you don't pick. Made at 2K and
   saved as 1280×720 (YouTube's size).
2. **10–20 scene illustrations per long video** (1K, square), one per scene and spread evenly. They appear in each
   scene's picture panel. Max appears in about a third of them; the others show objects only.

Shorts keep the code-drawn visuals.

## One consistent character

Max is our own original, code-drawn narrator (round glasses, brown hair, green sweater).
- His reference sheet is created once at `data/character/reference.png` and sent with every image that shows him,
  so he looks the same every time.
- The prompts forbid real people, celebrities, logos, watermarks and photorealism.
- The YouTube "altered or synthetic content" setting stays **No** (illustrated, not realistic). The description's AI
  note says some illustrations are AI-made.

## Cost and cap

| | |
|---|---|
| Price (reported Gemini API rates, Oct 2026) | about $0.034 per 1K image, $0.050 per 2K image |
| Per long video | 3 × 2K + up to 20 × 1K ≈ $0.83 at most (≈ $0.66 with 15 scenes) |
| Per month (16 long videos) | ≈ $10.50–13.30 |
| Separate cap | **$15/month**, checked before every image; Telegram alert at **80%** ($12) |

Every image is cached, so a re-render never pays again. Check Google's pricing page once and correct
`IMAGE_PRICE_1K` / `IMAGE_PRICE_2K` if the prices differ.

## If the image API fails

Each image is retried 3 times. If it still fails, or the cap is reached, or paid use is off, **that image is drawn
by the existing code** (thumbnail or scene). The video is never delayed for images; only the voice can hold a
video.

## Settings (`.env`)

- `IMAGE_PROVIDER=gemini`: set `none` to switch AI images off.
- `IMAGE_MONTHLY_BUDGET_USD=15`
- `IMAGE_SCENE_SIZE=1K`, `IMAGE_THUMB_SIZE=2K`
- `IMAGE_SCENES_MAX=20`
