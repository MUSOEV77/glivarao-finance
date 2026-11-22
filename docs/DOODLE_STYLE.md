# GLIVARAO doodle style (our own hand-drawn explainer look)

Status: **samples only until you approve them in Telegram.** The current style stays the default
(`GLIVARAO_THEME=editorial`); tapping ✅ under the samples sets `GLIVARAO_THEME=doodle` for new videos.

- **Frames:** off-white paper, black marker doodles, simple stick-style characters, hand-drawn charts and arrows,
  brand deep green `#1f8a4c` + gold `#e0a526`, a small GLIVARAO mark in the top-right corner. No real faces and no
  one else's characters or logos.
- **Max:** code-drawn (round head, round glasses, three-hair tuft, green sweater with a gold coin pin), so he is
  identical in every video. 7 emotions: happy, worried, shocked, thinking, confident, cheering, sad. His style
  reference sheet (`data/character/doodle_reference.png`) is sent with every Nano Banana request in this style.
- **Motion:** each scene is cut into 6-10 second shots at sentence boundaries (a title, a big circled number, a
  hand-drawn chart, key points, a doodle icon or an AI drawing); the camera slowly zooms or pans across each one,
  and shots change with a hard cut. Calm music bed, no cartoon sound effects. Captions as before.
- **Thumbnails:** a 2-3 word statement ending with a period ("Debt Wins."), one simple chart (grey history line +
  green spike with a gold dot, no numbers), Max with an emotion, off-white paper. 3 options per long video, code-
  drawn (nothing spent).
- **Samples:** `python -m glivarao style-samples --send` (Max reference sheet, 3 frames + 3 thumbnails for 3
  launch-list topics, a 14 s motion clip, Approve / Request changes buttons). Code-drawn: costs nothing.
- Code: `glivarao/art/doodle.py` (drawing), `glivarao/render/doodle.py` (shots + camera),
  `glivarao/studio/style_samples.py` (samples + approval).
