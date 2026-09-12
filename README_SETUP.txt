FACTOSPHERE AUTO BOT - NEW REPOSITORY SETUP

This ZIP is rebuilt from the previous bot, with FACTOSPHERE branding. It keeps:
- 3 Shorts/day + 1 Long/day
- Gemini script generation when Gemini is available
- Built-in fallback facts if Gemini is unavailable
- Edge TTS voice
- Pexels video
- FFmpeg captions/rendering
- YouTube automatic upload
- topic_history.json to reduce repeats

GITHUB SECRETS (do not put keys inside code):
1. GEMINI_API_KEY (optional because fallback is included)
2. PEXELS_API_KEY (required)
3. YOUTUBE_TOKEN_JSON (required)

SCHEDULE — BANGLADESH TIME (UTC+6):
1:00 PM Short
5:00 PM Long
7:00 PM Short
11:00 PM Short

MANUAL TEST:
GitHub -> Actions -> FACTOSPHERE Auto Upload -> Run workflow -> choose short or long.

IMPORTANT:
The old Gemini error was a Google project-level 403. Changing the ZIP cannot unlock a denied Google project. This version therefore does NOT stop the whole bot when Gemini fails: it uses built-in facts and continues. If Gemini access works, it uses Gemini normally.

CHANNEL BRAND: FACTOSPHERE
YOUTUBE CATEGORY: Education (27)
UPLOAD VISIBILITY: Public
