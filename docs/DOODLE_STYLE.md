# GLIVARAO doodle style v2 (our own hand-drawn explainer look)

Status: **samples only until you approve them in Telegram.** The current style stays the default; tapping ✅ under
the samples sets `GLIVARAO_THEME=doodle` for new videos. Production stays paused until you resume it.

**One server command:** `python -m glivarao style-samples --send` (hard cap $2 of Nano Banana; prints the money
spent; images are cached, so re-running costs nothing for what exists).

- **Max, designed once:** Nano Banana draws a master design (2K) and 8 poses from it (1K each): explaining,
  pointing, worried, shocked, thinking, happy, sad, cheering. Backgrounds are keyed out to transparent PNG
  cutouts (`data/character/max/`), each checked automatically; the 8-pose style sheet is the reference for every
  scene request. Never regenerated unless `--redesign-max`.
- **Full pictures behind every shot:** key scenes per video drawn by Nano Banana with Max acting in them (6 per
  long video at 2K 16:9, 1 per Short at 1K 9:16); every other shot uses a reusable place from the scene library
  (12 places such as a kitchen table with bills, a bank lobby, a suburban street; made once and cached) with the
  Max cutout whose pose matches the narration. Charts, numbers and titles are code-drawn cards on top.
- **Checks in code:** every text is fitted inside the safe area (never cut off, never under the captions; tested);
  frames may have at most 15% blank area (tested; the rejected v1 frames scored 60-70%). If Max or the pictures
  aren't available, that video is made in the editorial style instead of a half-empty doodle video.
- **Thumbnails:** 2-3 word statement ending with a period, one simple chart (grey history + green spike with a
  gold dot), a Max cutout with an emotion, off-white paper. Code-drawn, no extra cost.
- **Nano Banana cost:** $0.30 per long video, $0.034 per Short, about $7.86 a month for 16 long + 90 Shorts,
  plus one-time ~$1.01 for the scene library and up to ~$0.59 for designing Max. Fits the $15 image budget.
