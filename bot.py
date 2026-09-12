import os
import sys
import json
import re
import time
import random
import subprocess
import asyncio
from pathlib import Path
from datetime import datetime, timezone

import requests
import edge_tts
from google import genai
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.auth.transport.requests import Request
from PIL import Image, ImageDraw, ImageFont


# ============================================================
# FACTOSPHERE AUTO BOT - FINAL CLOUD VERSION
# 3 Shorts/day + 1 Long/day
# Gemini -> Script -> Edge TTS -> Pexels -> FFmpeg -> YouTube
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

VOICE_FILE = BASE_DIR / "voice.mp3"
BG_FILE = BASE_DIR / "background.mp4"
FINAL_FILE = BASE_DIR / "final_video.mp4"
SRT_FILE = BASE_DIR / "captions.srt"
THUMB_FILE = BASE_DIR / "thumbnail.jpg"
HOOK_FILE = BASE_DIR / "hook.txt"
BRAND_FILE = BASE_DIR / "brand.txt"
HISTORY_FILE = BASE_DIR / "topic_history.json"

VOICE = "en-US-AndrewMultilingualNeural"
VOICE_RATE = "+5%"
GEMINI_MODEL = "gemini-2.5-flash"

YOUTUBE_SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

CATEGORIES = [
    "psychology and human behavior",
    "space and the universe",
    "science and technology",
    "Earth and extreme events",
    "animals and nature",
    "mystery and unexplained phenomena",
    "strange and dark history",
    "money and business stories",
    "what-if and hypothetical scenarios",
    "records and extreme facts",
    "AI and future technology",
    "human body and biology",
    "ocean and deep sea",
    "ancient civilizations and archaeology",
]

FALLBACK_QUERIES = [
    "space universe",
    "ocean underwater",
    "wildlife nature",
    "earth planet",
    "technology futuristic",
    "science laboratory",
    "galaxy stars",
    "deep sea",
    "animal wildlife",
    "microscopic science",
    "ancient ruins",
    "human brain",
    "robot artificial intelligence",
]

FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
FONT_REG = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"


def env(name):
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is missing from GitHub Secrets.")
    return value


GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "").strip()
PEXELS_API_KEY = env("PEXELS_API_KEY")


def retry(label, fn, attempts=3, delay=3):
    last = None
    for n in range(1, attempts + 1):
        try:
            print(f"{label}: attempt {n}/{attempts}")
            return fn()
        except Exception as exc:
            last = exc
            print(f"{label} failed: {exc}")
            if n < attempts:
                time.sleep(delay * n)
    raise RuntimeError(f"{label} failed after {attempts} attempts: {last}")


def run_cmd(cmd):
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    if result.returncode != 0:
        raise RuntimeError("FFmpeg failed:\n" + result.stderr[-5000:])
    return result


def safe_json(raw):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*", "", raw)
        raw = re.sub(r"\s*```$", "", raw)
    return json.loads(raw)


def load_history():
    if not HISTORY_FILE.exists():
        return []
    try:
        data = json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []


def save_history(history):
    HISTORY_FILE.write_text(
        json.dumps(history[-150:], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def choose_category():
    return random.choice(CATEGORIES)


def generate_content(video_type):
    category = choose_category()
    history = load_history()
    recent = history[-40:]

    if video_type == "short":
        length_rule = "35 to 60 spoken words"
        format_rule = "a fast YouTube Short"
    else:
        length_rule = "850 to 1500 spoken words, suitable for roughly 6 to 10 minutes"
        format_rule = "a long-form YouTube documentary/explainer"

    prompt = f"""
You are the senior writer for FACTOSPHERE, a premium English facts and curiosity channel.

Create ONE completely original, highly engaging {format_rule}.
Primary category: {category}.

Return ONLY valid JSON in exactly this shape:
{{
  "title": "YouTube title, max 95 characters",
  "script": "complete English narration",
  "description": "SEO-friendly YouTube description with natural hashtags",
  "search_query": "2 to 5 word Pexels visual search query",
  "thumbnail_text": "2 to 6 powerful words for thumbnail",
  "topic_key": "short normalized unique topic phrase",
  "category": "one category label",
  "tags": ["10 to 18 relevant tags"]
}}

Rules:
- The topic must be genuinely interesting and curiosity-driven.
- Never invent facts, statistics, quotations, studies, historical claims, or scientific claims.
- If uncertain about a claim, choose a safer well-established topic instead.
- Avoid medical misinformation, political persuasion, dangerous instructions, illegal instructions, hate, sexual content, and graphic gore.
- Do not start with "Did you know".
- The first sentence must create immediate curiosity.
- Use an open loop and payoff structure.
- Keep narration natural for an English AI voice.
- No emojis inside the narration.
- Do not copy or imitate another creator's script.
- Do not use clickbait that makes a false promise.
- The title should create curiosity while remaining accurate.
- Search query must visually match the subject.
- thumbnail_text must be short, bold, and understandable.
- Tags must include topic-specific terms, not only generic terms.
- Channel brand is FACTOSPHERE.
- Avoid these recent topic keys whenever possible:
{json.dumps(recent, ensure_ascii=False)}
- Required narration length: {length_rule}.
"""

    def fallback_content():
        facts = [
            {"title":"The Ocean Has a Hidden Mountain Range","script":"There is a mountain range on Earth that most people never see. It stretches for tens of thousands of kilometers beneath the oceans, forming a giant underwater chain around the planet. This system is called the mid-ocean ridge, and new ocean floor is created along parts of it as molten rock rises and cools. So while the continents may look like the main landscape of Earth, an enormous hidden world is moving beneath the waves.","search_query":"underwater ocean mountains","thumbnail_text":"EARTH HAS HIDDEN MOUNTAINS","topic_key":"mid ocean ridge underwater mountain range","category":"ocean and deep sea"},
            {"title":"A Day on Venus Is Longer Than Its Year","script":"Venus has one of the strangest calendars in the solar system. It takes Venus about 225 Earth days to orbit the Sun, but about 243 Earth days to rotate once on its axis. That means a Venusian day is actually longer than a Venusian year. Even stranger, Venus rotates in the opposite direction from most planets. If you stood there, the Sun would appear to rise in the west and set in the east.","search_query":"Venus planet space","thumbnail_text":"VENUS BREAKS THE RULES","topic_key":"venus day longer than year","category":"space and the universe"},
            {"title":"Octopuses Have Three Hearts","script":"An octopus does not have one heart like a human. It has three. Two hearts pump blood toward the gills, where oxygen is picked up, while a third heart sends that oxygen-rich blood around the body. There is another strange detail: when an octopus swims, the main heart temporarily stops beating. That is one reason octopuses often prefer crawling along the seafloor instead of swimming for long periods.","search_query":"octopus underwater wildlife","thumbnail_text":"THIS ANIMAL HAS 3 HEARTS","topic_key":"octopus three hearts","category":"animals and nature"},
            {"title":"Your Bones Are Living Tissue","script":"Bones may look like solid pieces of stone, but they are living tissue. Inside them are blood vessels, nerves, and cells that constantly build and break down bone material. Your skeleton is continuously being remodeled throughout your life. That means the bones supporting you today are not exactly the same tissue you had years ago. Your body is quietly maintaining its internal framework all the time.","search_query":"human skeleton science","thumbnail_text":"YOUR BONES ARE ALIVE","topic_key":"bones living tissue remodeling","category":"human body and biology"},
            {"title":"Lightning Can Be Hotter Than the Sun's Surface","script":"A lightning channel can reach temperatures of roughly thirty thousand kelvin, making it several times hotter than the visible surface of the Sun. The extreme heat causes surrounding air to expand explosively, creating the shock wave we hear as thunder. So the flash you see during a storm is not just bright electricity. For a tiny fraction of a second, it creates one of the hottest natural events near Earth's surface.","search_query":"lightning thunderstorm","thumbnail_text":"LIGHTNING IS EXTREMELY HOT","topic_key":"lightning hotter than sun surface","category":"Earth and extreme events"},
            {"title":"The Deepest Ocean Point Is Far Below Everest","script":"Mount Everest is the highest point above sea level, but the deepest known parts of Earth's ocean are far deeper than Everest is tall. Challenger Deep in the Mariana Trench reaches nearly eleven kilometers below sea level. If Mount Everest were placed there, its summit would still be underwater. The deepest ocean is a world of crushing pressure, darkness, and cold that humans have only rarely visited directly.","search_query":"Mariana Trench deep ocean","thumbnail_text":"DEEPER THAN EVEREST IS HIGH","topic_key":"challenger deep deeper than everest","category":"ocean and deep sea"},
            {"title":"Bananas Are Berries, But Strawberries Are Not","script":"Botanically, some fruits have very different identities from the ones we use in everyday language. A banana qualifies as a berry under botanical definitions because it develops from one flower with one ovary and contains seeds in its structure. A strawberry, despite its name, is not a true berry. The red flesh we eat is actually an enlarged part of the flower, while the tiny seed-like structures on the outside are individual fruits.","search_query":"banana strawberry fruit science","thumbnail_text":"BANANAS ARE BERRIES","topic_key":"banana berry strawberry not berry","category":"science and technology"},
            {"title":"There Is a Giant Water Reservoir in Space","script":"Astronomers have found enormous amounts of water vapor in distant regions of space. One famous example surrounds a quasar billions of light-years away and contains vastly more water than all the oceans on Earth. It is not a floating ocean that a spacecraft could visit, but a huge cloud of water molecules spread through space. Discoveries like this show that water is not unique to our planet.","search_query":"space nebula water molecules","thumbnail_text":"SPACE HAS ENORMOUS WATER","topic_key":"water reservoir in space quasar","category":"space and the universe"},
        ]
        history_set=set(load_history()[-100:])
        available=[f for f in facts if f["topic_key"] not in history_set]
        item=random.choice(available or facts)
        data=dict(item)
        data["description"] = f"Explore an amazing fact about {data['category']}. Learn something new with FACTOSPHERE. #FACTOSPHERE #Facts #Knowledge"
        data["tags"] = ["facts","interesting facts","knowledge","science","education","FACTOSPHERE",data["category"],"amazing facts","did you know","shorts"]
        print("Using built-in fallback fact because Gemini was unavailable.")
        return data

    if not GEMINI_API_KEY:
        data = fallback_content()
    else:
        def call():
            client = genai.Client(api_key=GEMINI_API_KEY)
            response = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
            )
            return safe_json(response.text)

        try:
            data = retry("Gemini content generation", call, attempts=3, delay=4)
        except Exception as exc:
            print("Gemini unavailable; switching to built-in fallback:", exc)
            data = fallback_content()

    required = [
        "title", "script", "description", "search_query",
        "thumbnail_text", "topic_key", "category", "tags"
    ]
    for key in required:
        if not data.get(key):
            raise RuntimeError(f"Gemini did not return {key}.")

    if video_type == "short":
        data["description"] = data["description"].rstrip() + "\n\n#shorts #FACTOSPHERE"
    else:
        data["description"] = data["description"].rstrip() + "\n\n#FACTOSPHERE #Facts #Knowledge"

    data["title"] = str(data["title"]).strip()[:100]
    data["script"] = re.sub(r"\s+", " ", str(data["script"]).strip())
    data["search_query"] = str(data["search_query"]).strip()
    data["thumbnail_text"] = re.sub(r"\s+", " ", str(data["thumbnail_text"]).strip())[:70]
    data["topic_key"] = re.sub(r"\s+", " ", str(data["topic_key"]).strip().lower())

    if not isinstance(data["tags"], list):
        data["tags"] = []

    print("\nTITLE:", data["title"])
    print("CATEGORY:", data["category"])
    print("TOPIC:", data["topic_key"])
    print("SCRIPT WORDS:", len(data["script"].split()))
    return data


async def create_voice(text):
    if VOICE_FILE.exists():
        VOICE_FILE.unlink()

    async def make():
        communicate = edge_tts.Communicate(
            text=text,
            voice=VOICE,
            rate=VOICE_RATE,
        )
        await communicate.save(str(VOICE_FILE))

    for attempt in range(1, 4):
        try:
            print(f"Creating AI voice: attempt {attempt}/3")
            await make()
            if VOICE_FILE.exists() and VOICE_FILE.stat().st_size > 1000:
                return
        except Exception as exc:
            print("Voice error:", exc)
        await asyncio.sleep(attempt * 2)

    raise RuntimeError("AI voice could not be created.")


def pexels_video(search_query, video_type):
    headers = {"Authorization": PEXELS_API_KEY}
    url = "https://api.pexels.com/videos/search"

    queries = [search_query] + [
        q for q in FALLBACK_QUERIES
        if q.lower() != search_query.lower()
    ]

    orientation = "portrait" if video_type == "short" else "landscape"
    selected = None

    for query in queries:
        try:
            r = requests.get(
                url,
                headers=headers,
                params={
                    "query": query,
                    "per_page": 20,
                    "orientation": orientation,
                },
                timeout=30,
            )
            r.raise_for_status()
            videos = r.json().get("videos", [])
        except Exception as exc:
            print("Pexels search error:", exc)
            continue

        candidates = []
        for video in videos:
            for vf in video.get("video_files", []):
                width = vf.get("width") or 0
                height = vf.get("height") or 0
                link = vf.get("link")
                if not link:
                    continue

                if video_type == "short":
                    good = height >= width and height >= 720
                else:
                    good = width >= height and width >= 1280

                if good:
                    candidates.append((width * height, height, width, link))

        if candidates:
            candidates.sort(reverse=True)
            selected = candidates[0][3]
            print("Selected Pexels query:", query)
            break

    if not selected:
        raise RuntimeError("Pexels returned no usable video.")

    if BG_FILE.exists():
        BG_FILE.unlink()

    def download():
        with requests.get(selected, stream=True, timeout=90) as r:
            r.raise_for_status()
            with open(BG_FILE, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024 * 1024):
                    if chunk:
                        f.write(chunk)

    retry("Pexels video download", download, attempts=3, delay=3)

    if not BG_FILE.exists() or BG_FILE.stat().st_size < 10000:
        raise RuntimeError("Downloaded Pexels video is invalid.")


def pexels_image(search_query):
    headers = {"Authorization": PEXELS_API_KEY}
    url = "https://api.pexels.com/v1/search"

    try:
        r = requests.get(
            url,
            headers=headers,
            params={"query": search_query, "per_page": 10, "orientation": "landscape"},
            timeout=30,
        )
        r.raise_for_status()
        photos = r.json().get("photos", [])
        if not photos:
            return None
        return photos[0].get("src", {}).get("large2x") or photos[0].get("src", {}).get("large")
    except Exception as exc:
        print("Thumbnail image search failed:", exc)
        return None


def make_thumbnail(meta):
    try:
        image_url = pexels_image(meta["search_query"])
        if image_url:
            r = requests.get(image_url, timeout=60)
            r.raise_for_status()
            temp = BASE_DIR / "thumb_source.jpg"
            temp.write_bytes(r.content)
            img = Image.open(temp).convert("RGB")
            img = img.resize((1280, 720))
        else:
            img = Image.new("RGB", (1280, 720), (10, 16, 28))

        draw = ImageDraw.Draw(img, "RGBA")

        # Dark overlay for professional readable text.
        draw.rectangle((0, 0, 1280, 720), fill=(0, 0, 0, 105))
        draw.rectangle((0, 0, 1280, 18), fill=(40, 130, 255, 255))

        try:
            font_big = ImageFont.truetype(FONT_BOLD, 78)
            font_brand = ImageFont.truetype(FONT_BOLD, 34)
        except Exception:
            font_big = ImageFont.load_default()
            font_brand = ImageFont.load_default()

        text = meta["thumbnail_text"].upper()
        max_width = 1120
        words = text.split()
        lines, current = [], ""
        for word in words:
            test = (current + " " + word).strip()
            if draw.textbbox((0, 0), test, font=font_big)[2] <= max_width:
                current = test
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        lines = lines[:3]

        total_h = sum(draw.textbbox((0, 0), line, font=font_big)[3] for line in lines) + 20 * (len(lines) - 1)
        y = (720 - total_h) // 2

        for line in lines:
            box = draw.textbbox((0, 0), line, font=font_big)
            w = box[2] - box[0]
            x = (1280 - w) // 2
            draw.text((x + 4, y + 4), line, font=font_big, fill=(0, 0, 0, 220))
            draw.text((x, y), line, font=font_big, fill=(245, 248, 255, 255))
            y += box[3] - box[1] + 20

        draw.text((50, 45), "FACTOSPHERE", font=font_brand, fill=(235, 242, 255, 255))
        draw.text((50, 88), "DISCOVER WHAT YOU DIDN'T KNOW", font=ImageFont.truetype(FONT_REG, 20), fill=(190, 205, 225, 230))

        img.save(THUMB_FILE, quality=92, optimize=True)
        print("Thumbnail created.")
    except Exception as exc:
        print("Thumbnail generation skipped:", exc)


def make_srt(text):
    words = text.split()
    if not words:
        raise RuntimeError("Script is empty.")

    # Approximate timing from word count; keeps captions readable without
    # requiring a speech-to-text service.
    total_seconds = max(1.0, len(words) / 2.45)
    chunk_size = 9
    chunks = [words[i:i + chunk_size] for i in range(0, len(words), chunk_size)]
    seconds_per_word = total_seconds / len(words)

    lines = []
    cursor_word = 0

    def stamp(sec):
        ms = int(round((sec - int(sec)) * 1000))
        whole = int(sec)
        h = whole // 3600
        m = (whole % 3600) // 60
        s = whole % 60
        return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

    for idx, chunk in enumerate(chunks, 1):
        start = cursor_word * seconds_per_word
        cursor_word += len(chunk)
        end = cursor_word * seconds_per_word
        lines.append(
            f"{idx}\n{stamp(start)} --> {stamp(end)}\n{' '.join(chunk)}\n"
        )

    SRT_FILE.write_text("\n".join(lines), encoding="utf-8")


def ffmpeg_path():
    path = subprocess.run(
        ["which", "ffmpeg"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    ).stdout.strip()
    return path or "ffmpeg"


def create_video(meta, video_type):
    if FINAL_FILE.exists():
        FINAL_FILE.unlink()

    make_srt(meta["script"])
    HOOK_FILE.write_text(meta["title"][:70], encoding="utf-8")
    BRAND_FILE.write_text("FACTOSPHERE", encoding="utf-8")

    ffmpeg = ffmpeg_path()

    if video_type == "short":
        size_filter = (
            "scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920"
        )
        subtitle_style = (
            "FontName=DejaVu Sans,FontSize=18,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,"
            "BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=170"
        )
        hook = (
            f"drawtext=textfile='{HOOK_FILE}':fontfile='{FONT_BOLD}':"
            "fontcolor=white:fontsize=58:box=1:boxcolor=black@0.58:"
            "boxborderw=24:x=(w-text_w)/2:y=180:"
            "alpha='if(lt(t,0.35),t/0.35,if(gt(t,2.6),(3-t)/0.4,1))':"
            "enable='between(t,0,3)'"
        )
        brand = (
            f"drawtext=textfile='{BRAND_FILE}':fontfile='{FONT_BOLD}':"
            "fontcolor=white@0.88:fontsize=30:x=34:y=42"
        )
    else:
        size_filter = (
            "scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080"
        )
        subtitle_style = (
            "FontName=DejaVu Sans,FontSize=20,"
            "PrimaryColour=&H00FFFFFF,OutlineColour=&H00101010,"
            "BorderStyle=1,Outline=2,Shadow=0,Alignment=2,MarginV=55"
        )
        hook = (
            f"drawtext=textfile='{HOOK_FILE}':fontfile='{FONT_BOLD}':"
            "fontcolor=white:fontsize=62:box=1:boxcolor=black@0.58:"
            "boxborderw=26:x=(w-text_w)/2:y=100:"
            "alpha='if(lt(t,0.35),t/0.35,if(gt(t,2.6),(3-t)/0.4,1))':"
            "enable='between(t,0,3)'"
        )
        brand = (
            f"drawtext=textfile='{BRAND_FILE}':fontfile='{FONT_BOLD}':"
            "fontcolor=white@0.88:fontsize=32:x=45:y=40"
        )

    vf = (
        f"{size_filter},"
        f"{hook},"
        f"{brand},"
        f"subtitles='{SRT_FILE}':force_style='{subtitle_style}'"
    )

    cmd = [
        ffmpeg, "-y",
        "-stream_loop", "-1",
        "-i", str(BG_FILE),
        "-i", str(VOICE_FILE),
        "-map", "0:v:0",
        "-map", "1:a:0",
        "-vf", vf,
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-pix_fmt", "yuv420p",
        "-r", "30",
        "-c:a", "aac",
        "-b:a", "128k",
        "-shortest",
        "-movflags", "+faststart",
        str(FINAL_FILE),
    ]

    retry("FFmpeg video render", lambda: run_cmd(cmd), attempts=2, delay=4)

    if not FINAL_FILE.exists() or FINAL_FILE.stat().st_size < 100000:
        raise RuntimeError("Final video was not created correctly.")


def youtube_service():
    token_json = os.getenv("YOUTUBE_TOKEN_JSON", "").strip()
    if not token_json:
        raise RuntimeError("YOUTUBE_TOKEN_JSON is missing from GitHub Secrets.")

    try:
        token_data = json.loads(token_json)
    except json.JSONDecodeError:
        raise RuntimeError("YOUTUBE_TOKEN_JSON is not valid JSON.")

    creds = Credentials.from_authorized_user_info(token_data, YOUTUBE_SCOPES)

    if creds.expired and creds.refresh_token:
        creds.refresh(Request())

    if not creds.valid:
        raise RuntimeError("YouTube authorization is invalid or expired.")

    return build("youtube", "v3", credentials=creds)


def upload_to_youtube(meta, video_type):
    youtube = youtube_service()

    base_tags = [
        "FACTOSPHERE", "facts", "knowledge", "interesting facts",
        "amazing facts", "science", "curiosity", "educational",
    ]
    if video_type == "short":
        base_tags += ["shorts", "youtube shorts"]

    tags = []
    for tag in base_tags + meta.get("tags", []):
        tag = re.sub(r"#", "", str(tag)).strip()
        if tag and tag.lower() not in {x.lower() for x in tags}:
            tags.append(tag)
    tags = tags[:30]

    body = {
        "snippet": {
            "title": meta["title"][:100],
            "description": meta["description"][:4900],
            "tags": tags,
            "categoryId": "27",
        },
        "status": {
            "privacyStatus": "public",
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        str(FINAL_FILE),
        mimetype="video/mp4",
        chunksize=1024 * 1024,
        resumable=True,
    )

    def do_upload():
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media,
        )
        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                print("Upload:", int(status.progress() * 100), "%")
        return response["id"]

    video_id = retry("YouTube upload", do_upload, attempts=3, delay=6)

    if video_type == "long" and THUMB_FILE.exists():
        try:
            thumb_media = MediaFileUpload(
                str(THUMB_FILE),
                mimetype="image/jpeg",
                resumable=False,
            )
            youtube.thumbnails().set(
                videoId=video_id,
                media_body=thumb_media,
            ).execute()
            print("Custom thumbnail uploaded.")
        except Exception as exc:
            print("Thumbnail upload skipped:", exc)

    print("\nSUCCESS")
    print("Video ID:", video_id)
    print("URL:", f"https://www.youtube.com/watch?v={video_id}")
    return video_id


def cleanup():
    for file in [
        VOICE_FILE, BG_FILE, FINAL_FILE, SRT_FILE,
        THUMB_FILE, HOOK_FILE, BRAND_FILE,
        BASE_DIR / "thumb_source.jpg",
    ]:
        try:
            if file.exists():
                file.unlink()
        except Exception as exc:
            print("Cleanup warning:", exc)


def main():
    requested = "short"
    if len(sys.argv) > 1 and sys.argv[1].lower() in {"short", "long"}:
        requested = sys.argv[1].lower()

    print("=" * 56)
    print("              FACTOSPHERE AUTO BOT")
    print(f"              VIDEO TYPE: {requested.upper()}")
    print("=" * 56)

    # Validate YouTube secret before doing expensive generation.
    if not os.getenv("YOUTUBE_TOKEN_JSON", "").strip():
        raise RuntimeError("YOUTUBE_TOKEN_JSON is missing from GitHub Secrets.")

    meta = generate_content(requested)

    # Avoid a recent duplicate; regenerate once if necessary.
    history = load_history()
    if meta["topic_key"] in history[-60:]:
        print("Duplicate topic detected. Regenerating once.")
        meta = generate_content(requested)

    asyncio.run(create_voice(meta["script"]))
    pexels_video(meta["search_query"], requested)

    if requested == "long":
        make_thumbnail(meta)

    create_video(meta, requested)
    video_id = upload_to_youtube(meta, requested)

    history = load_history()
    history.append(meta["topic_key"])
    save_history(history)

    print(f"\nFACTOSPHERE {requested.upper()} FINISHED SUCCESSFULLY.")
    print("Uploaded:", video_id)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("Stopped by user.")
        cleanup()
        raise
    except Exception as exc:
        print("\nBOT ERROR:", type(exc).__name__, exc)
        cleanup()
        raise
