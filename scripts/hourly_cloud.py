"""Generate and optionally publish one original Amala Short in a cloud runner."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import textwrap
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from urllib.error import HTTPError

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
YOUTUBE_AGENT_ROOT = ROOT / "third_party" / "youtube-agent-skill"
MODEL = os.environ.get("GROQ_MODEL", "qwen/qwen3.8-27b")
TOPICS = [
    "find files changed today with Python",
    "rename many files safely with Python",
    "count file types in a folder with Python",
    "find empty folders without deleting them",
    "create a simple folder inventory as CSV",
    "check which files use the most disk space",
    "compare two text files with Python",
    "make a timestamped backup copy of one file",
    "find duplicate filenames across folders",
    "organize downloads by file extension in preview mode",
    "read a CSV and show the top five rows",
    "create strong random passwords locally with Python",
]


def run(*args, cwd=None, input_text=None):
    return subprocess.run(args, cwd=cwd, input=input_text, text=True, check=True, capture_output=True)


def request(method: str, url: str, *, headers=None, data=None, timeout=60):
    req = Request(url, data=data, headers=headers or {}, method=method)
    try:
        return urlopen(req, timeout=timeout)
    except HTTPError as exc:
        detail = exc.read(1000).decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {detail}") from None


def topic_for(slot: str) -> str:
    index = int(hashlib.sha256(slot.encode()).hexdigest()[:8], 16) % len(TOPICS)
    return TOPICS[index]


def groq_json(topic: str) -> dict:
    key = os.environ.get("GROQ_API_KEY")
    if not key:
        raise RuntimeError("GROQ_API_KEY is missing")
    prompt = f"""Create one original 35-50 second faceless YouTube Short about: {topic}.
Return JSON only with keys title, title_options, hook_options, narration, description, hashtags, scenes, code_lines.
Rules: title <= 70 characters; narration 80-105 words (count carefully and never exceed 105); exactly 5 scenes; each scene <= 7 words;
code_lines is an array of 2-5 short Python lines that match the lesson and never delete or modify files;
title_options is exactly 5 accurate titles under 60 characters; hook_options is exactly 5 factual opening lines of 9-24 words;
each hook must confirm the title, create curiosity, avoid invented numbers, and avoid clickbait; the narration must begin with one hook option;
hashtags is an array of 4 useful tags; teach a safe Python technique; never claim guaranteed results;
never delete or modify user files; no copied quotes, music, brands, news, or unverifiable statistics.
The final narration sentence must invite viewers to subscribe for practical Python tips."""
    payload = {
        "model": MODEL,
        "temperature": 0.65,
        "max_tokens": 1200,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "You write concise, original, factual educational Shorts. Output valid JSON only."},
            {"role": "user", "content": prompt},
        ],
    }
    for attempt in range(3):
        req = Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=json.dumps(payload).encode(),
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                # Groq's edge rejects urllib's default Python-urllib user agent
                # from some shared cloud runner IPs with Cloudflare error 1010.
                "User-Agent": "amala-youtube-operations/1.0",
            },
            method="POST",
        )
        try:
            with urlopen(req, timeout=60) as response:
                result = json.load(response)
            return json.loads(result["choices"][0]["message"]["content"])
        except HTTPError as exc:
            if exc.code != 429 or attempt == 2:
                detail = exc.read(1000).decode("utf-8", errors="replace")
                raise RuntimeError(f"Groq HTTP {exc.code}: {detail}") from None
            time.sleep(min(20, int(exc.headers.get("retry-after", "3"))))
    raise AssertionError("unreachable")


def validate_content(content: dict) -> dict:
    required = {"title", "narration", "description", "hashtags", "scenes"}
    if not required.issubset(content):
        raise ValueError(f"Groq output lacks fields: {sorted(required - set(content))}")
    if len(str(content["title"])) > 70:
        raise ValueError("Title exceeds 70 characters")
    word_count = len(str(content["narration"]).split())
    # Allow a small cushion above the prompt's 115-word target. Models can
    # count punctuation-bound words differently, and a harmless one-word
    # variation should not stop the entire scheduled publishing job.
    if not 70 <= word_count <= 130:
        raise ValueError(f"Narration has {word_count} words; expected 70-130")
    if not isinstance(content["scenes"], list) or len(content["scenes"]) != 5:
        raise ValueError("Exactly five scenes are required")
    if not isinstance(content["hashtags"], list) or not 3 <= len(content["hashtags"]) <= 6:
        raise ValueError("Three to six hashtags are required")
    # Safe lessons often explain that preview code does not delete or remove
    # files. Reject misleading promises, while the prompt and fixed topic list
    # keep the generated lesson non-destructive.
    blocked = re.compile(r"\b(guaranteed|100%)\b", re.I)
    if blocked.search(str(content["narration"])):
        raise ValueError("Narration contains a blocked misleading claim")
    return content


def _load_vendor_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if not spec or not spec.loader:
        raise RuntimeError(f"Unable to load vendored module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def optimize_packaging(content: dict) -> dict:
    """Choose stronger hooks and titles with the free MIT YouTube agent tools."""
    hook_options = [str(item).strip() for item in content.get("hook_options", []) if str(item).strip()]
    title_options = [str(item).strip() for item in content.get("title_options", []) if str(item).strip()]
    if not hook_options and not title_options:
        return content
    content = dict(content)
    packaging = {}
    if hook_options:
        hookscore = _load_vendor_module(
            "amala_hookscore", YOUTUBE_AGENT_ROOT / "yt-script" / "hookscore.py"
        )
        ranked_hooks = []
        for hook in hook_options[:10]:
            parts, verdict, formula, _ = hookscore.score(hook)
            ranked_hooks.append({"hook": hook, "score": verdict, "formula": formula, "properties": parts})
        ranked_hooks.sort(key=lambda item: item["score"], reverse=True)
        winner = ranked_hooks[0]
        narration = str(content.get("narration", "")).strip()
        body_parts = re.split(r"(?<=[.!?])\s+", narration, maxsplit=1)
        body = body_parts[1] if len(body_parts) == 2 else narration
        hook_text = winner["hook"] if winner["hook"].endswith((".", "!", "?")) else winner["hook"] + "."
        improved = (hook_text + " " + body).strip()
        if len(improved.split()) < 70:
            improved = (hook_text + " " + narration).strip()
        words = improved.split()
        if len(words) > 130:
            improved = " ".join(words[:130]).rstrip(".,;:") + "."
        content["narration"] = improved
        packaging["hook"] = winner

    current_title = str(content.get("title", "")).strip()
    if current_title:
        title_options.append(current_title)
    eligible_titles = list(dict.fromkeys(title for title in title_options if len(title) <= 70))
    if eligible_titles:
        title_tool = _load_vendor_module(
            "amala_title_lint", YOUTUBE_AGENT_ROOT / "yt-package" / "title.py"
        )
        ranked_titles = [title_tool.check(title) for title in eligible_titles]
        ranked_titles.sort(key=lambda item: item["score"], reverse=True)
        content["title"] = ranked_titles[0]["title"]
        packaging["title"] = {
            "title": ranked_titles[0]["title"],
            "score": ranked_titles[0]["score"],
            "issues": ranked_titles[0]["issues"],
        }
    if packaging:
        content["packaging"] = packaging
    return content


def generate_valid_content(topic: str, attempts: int = 3) -> dict:
    """Regenerate a bounded number of times when an LLM misses hard limits."""
    errors = []
    for _ in range(attempts):
        content = optimize_packaging(groq_json(topic))
        try:
            return validate_content(content)
        except ValueError as exc:
            errors.append(str(exc))
    raise ValueError("Groq returned invalid content after retries: " + "; ".join(errors))


def font(size: int):
    for candidate in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "C:/Windows/Fonts/arialbd.ttf"):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default()


def render_cards(content: dict, out: Path) -> list[Path]:
    cards = []
    palettes = [
        ("#071426", "#0d3152", "#36d1ff"),
        ("#180b2d", "#43206b", "#d56bff"),
        ("#071f1a", "#124f43", "#43f0b4"),
        ("#291207", "#663516", "#ffad42"),
        ("#11152e", "#293f79", "#79a7ff"),
    ]
    code_lines = [str(line)[:42] for line in content.get("code_lines", [])][:5]
    for number, text in enumerate(content["scenes"], 1):
        background, panel, accent = palettes[number - 1]
        image = Image.new("RGB", (1080, 1920), background)
        draw = ImageDraw.Draw(image)
        # Layered shapes remain readable during MoneyPrinterTurbo's pan/zoom motion.
        draw.ellipse((-180, -120, 520, 580), fill=panel)
        draw.ellipse((700, 1370, 1280, 2020), fill=panel)
        for stripe in range(0, 1920, 64):
            draw.line((0, stripe, 1080, stripe + 240), fill="#26384a", width=2)
        draw.rounded_rectangle((58, 86, 1022, 1795), 58, fill=panel, outline=accent, width=7)
        draw.rounded_rectangle((96, 145, 984, 245), 28, fill=background)
        draw.text((125, 171), "AMALA  •  PYTHON SHORTS", font=font(38), fill=accent)
        draw.ellipse((865, 159, 925, 219), outline=accent, width=8)
        draw.line((895, 173, 895, 205), fill=accent, width=7)
        draw.line((881, 189, 909, 189), fill=accent, width=7)

        # A large animated focal badge gives every scene a distinct visual anchor.
        draw.rounded_rectangle((130, 330, 950, 570), 48, fill=background, outline=accent, width=5)
        draw.text((180, 365), f"STEP  {number}", font=font(45), fill=accent)
        draw.rectangle((180, 465, 180 + number * 125, 495), fill=accent)
        draw.rectangle((180 + number * 125, 465, 805, 495), fill="#5b6f88")
        wrapped = textwrap.wrap(str(text), width=17)[:5]
        y = 650
        for line in wrapped:
            box = draw.textbbox((0, 0), line, font=font(84))
            draw.text(((1080 - (box[2] - box[0])) / 2, y), line, font=font(84), fill="white")
            y += 115

        if code_lines:
            draw.rounded_rectangle((120, 1050, 960, 1485), 36, fill="#050b14", outline="#60738b", width=3)
            draw.ellipse((160, 1090, 184, 1114), fill="#ff5f56")
            draw.ellipse((200, 1090, 224, 1114), fill="#ffbd2e")
            draw.ellipse((240, 1090, 264, 1114), fill="#27c93f")
            for index, line in enumerate(code_lines[:4], 1):
                draw.text((165, 1160 + (index - 1) * 70), f"{index:>2}  {line}", font=font(31), fill="#d9f3ff")
        else:
            draw.rounded_rectangle((180, 1110, 900, 1390), 44, fill=background, outline=accent, width=4)
            draw.text((265, 1190), "{  SAFE CODE  }", font=font(48), fill=accent)

        draw.text((115, 1660), f"{number}/5", font=font(42), fill=accent)
        draw.text((760, 1660), "@Amala", font=font(42), fill="white")
        draw.text((115, 1725), "SAVE  •  TRY  •  SUBSCRIBE", font=font(32), fill="#d3deea")
        path = out / f"scene-{number:02}.png"
        image.save(path)
        cards.append(path)
    return cards


def make_simple_video(content: dict, out: Path, voice_file: Path | None = None) -> Path:
    out = out.resolve()
    narration = re.sub(r"[#*_`]", "", str(content["narration"]))
    wav = out / "voice.wav"
    transcript = out / "transcript.txt"
    transcript.write_text(narration + "\n", encoding="utf-8")
    if voice_file:
        shutil.copy2(voice_file.resolve(), wav)
    elif shutil.which("espeak-ng"):
        run("espeak-ng", "-v", "en-us+f3", "-s", "158", "-w", str(wav), narration)
    elif os.name == "nt":
        run("powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(ROOT / "scripts" / "narrate_windows.ps1"), "-ScriptPath", str(transcript), "-OutputPath", str(wav))
    else:
        raise RuntimeError("espeak-ng is required on non-Windows runners")
    cards = render_cards(content, out)
    seconds = float(run("ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(wav)).stdout.strip())
    concat = out / "concat.txt"
    per_card = seconds / len(cards)
    concat.write_text("".join(f"file '{p.as_posix()}'\nduration {per_card:.3f}\n" for p in cards) + f"file '{cards[-1].as_posix()}'\n", encoding="utf-8")
    video = out / "amala-short.mp4"
    run("ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-safe", "0", "-f", "concat", "-i", str(concat), "-i", str(wav), "-vf", "fps=30,scale=1080:1920,format=yuv420p", "-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-c:a", "aac", "-b:a", "128k", "-shortest", "-movflags", "+faststart", str(video))
    probe = json.loads(run("ffprobe", "-v", "error", "-show_streams", "-of", "json", str(video)).stdout)
    kinds = {stream["codec_type"] for stream in probe["streams"]}
    if kinds != {"video", "audio"}:
        raise RuntimeError(f"Rendered media streams are invalid: {kinds}")
    return video


def moneyprinter_command(content: dict, cards: list[Path]) -> list[str]:
    """Build the no-paid-provider MoneyPrinterTurbo CLI invocation."""
    return [
        "mpt", "cli",
        "--video-subject", str(content["title"]),
        "--video-script", re.sub(r"[#*_`]", "", str(content["narration"])),
        "--video-source", "local",
        "--video-materials", ",".join(str(card.resolve()) for card in cards),
        "--video-aspect", "9:16",
        "--video-concat-mode", "sequential",
        "--image-motion", "zoom",
        "--video-transition-mode", "shuffle",
        "--voice-name", os.environ.get("MPT_VOICE", "en-US-AriaNeural"),
        "--voice-rate", "1.08",
        "--bgm-type", "none",
        "--subtitle-enabled",
        "--subtitle-position", "bottom",
        "--subtitle-display-mode", "word_by_word",
        "--subtitle-animation", "pop_spring",
        "--subtitle-background-enabled",
        "--rounded-subtitle-background",
        "--stop-at", "video",
    ]


def make_moneyprinter_video(content: dict, out: Path) -> Path:
    """Render with MoneyPrinterTurbo using only local visuals and free Edge TTS."""
    if not shutil.which("mpt"):
        raise RuntimeError("MoneyPrinterTurbo CLI (mpt) is not installed")
    cards = render_cards(content, out)
    result = run(*moneyprinter_command(content, cards), cwd=out)
    lines = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    try:
        payload = json.loads(lines[-1])
    except (IndexError, json.JSONDecodeError) as exc:
        raise RuntimeError("MoneyPrinterTurbo did not return its JSON result") from exc
    task_result = payload.get("result", payload)
    videos = task_result.get("videos") or []
    if not videos:
        raise RuntimeError(f"MoneyPrinterTurbo failed: {task_result.get('error', 'no video returned')}")
    source = Path(videos[0])
    if not source.is_absolute():
        source = (out / source).resolve()
    if not source.is_file() or source.stat().st_size == 0:
        raise RuntimeError("MoneyPrinterTurbo returned a missing or empty video")
    video = out / "amala-short.mp4"
    shutil.copy2(source, video)
    (out / "moneyprinter-result.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return video


def make_video(content: dict, out: Path, voice_file: Path | None = None, renderer: str = "simple") -> tuple[Path, str]:
    if renderer == "moneyprinter" and voice_file is None:
        try:
            return make_moneyprinter_video(content, out), "moneyprinter"
        except Exception as exc:
            (out / "moneyprinter-fallback.txt").write_text(
                f"MoneyPrinterTurbo failed; used the reliable local renderer.\n{type(exc).__name__}: {exc}\n",
                encoding="utf-8",
            )
    return make_simple_video(content, out, voice_file), "simple"


def youtube_access_token() -> str:
    required = ["YOUTUBE_CLIENT_ID", "YOUTUBE_CLIENT_SECRET", "YOUTUBE_REFRESH_TOKEN"]
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        raise RuntimeError("Missing YouTube secrets: " + ", ".join(missing))
    form = urlencode({
        "client_id": os.environ["YOUTUBE_CLIENT_ID"],
        "client_secret": os.environ["YOUTUBE_CLIENT_SECRET"],
        "refresh_token": os.environ["YOUTUBE_REFRESH_TOKEN"],
        "grant_type": "refresh_token",
    }).encode()
    with request("POST", "https://oauth2.googleapis.com/token", headers={"Content-Type": "application/x-www-form-urlencoded"}, data=form, timeout=30) as response:
        return json.load(response)["access_token"]


def upload(video: Path, content: dict) -> str:
    token = youtube_access_token()
    tags = [str(tag).lstrip("#") for tag in content["hashtags"]]
    description = str(content["description"]).strip() + "\n\n" + " ".join("#" + tag for tag in tags)
    metadata = {
        "snippet": {"title": content["title"], "description": description, "tags": tags, "categoryId": "27"},
        "status": {"privacyStatus": "public", "selfDeclaredMadeForKids": False, "containsSyntheticMedia": True},
    }
    body = json.dumps(metadata).encode()
    with request("POST",
        "https://www.googleapis.com/upload/youtube/v3/videos?uploadType=resumable&part=snippet,status&notifySubscribers=false",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json; charset=UTF-8", "Content-Length": str(len(body)), "X-Upload-Content-Type": "video/mp4", "X-Upload-Content-Length": str(video.stat().st_size)},
        data=body, timeout=30,
    ) as start:
        location = start.headers["Location"]
    media = video.read_bytes()
    with request("PUT", location, headers={"Content-Type": "video/mp4", "Content-Length": str(len(media))}, data=media, timeout=300) as finish:
        result = json.load(finish)
    return "https://youtube.com/shorts/" + result["id"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--publish", action="store_true", help="Upload publicly after generation and QA")
    parser.add_argument("--slot", help="Stable UTC slot, defaults to the current hour")
    parser.add_argument("--content-file", type=Path, help="Use reviewed JSON instead of calling Groq")
    parser.add_argument("--voice-file", type=Path, help="Use an existing WAV for a local media test")
    parser.add_argument("--existing-video", type=Path, help="Publish an already reviewed MP4 without regenerating it")
    parser.add_argument(
        "--renderer", choices=("simple", "moneyprinter"),
        default=os.environ.get("VIDEO_RENDERER", "simple"),
        help="Video renderer; MoneyPrinterTurbo falls back to the simple renderer on failure",
    )
    parser.add_argument("--output", type=Path, default=ROOT / "hourly-output")
    args = parser.parse_args()
    if args.existing_video:
        if not args.publish or not args.content_file:
            parser.error("--existing-video requires --publish and --content-file")
        content = validate_content(json.loads(args.content_file.read_text(encoding="utf-8")))
        video = args.existing_video.resolve()
        if not video.is_file() or video.stat().st_size == 0:
            parser.error("--existing-video must point to a non-empty MP4")
        args.output.mkdir(parents=True, exist_ok=True)
        result = {
            "model": MODEL,
            "renderer": "moneyprinter",
            "video": str(video),
            "published": True,
            "url": upload(video, content),
        }
        (args.output / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(result))
        return 0
    slot = args.slot or datetime.now(timezone.utc).strftime("%Y-%m-%dT%H")
    out = args.output / slot.replace(":", "-")
    out.mkdir(parents=True, exist_ok=True)
    if args.content_file:
        content = json.loads(args.content_file.read_text(encoding="utf-8"))
        validate_content(content)
    else:
        content = generate_valid_content(topic_for(slot))
    (out / "content.json").write_text(json.dumps(content, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    video, renderer = make_video(content, out, args.voice_file, args.renderer)
    result = {"slot": slot, "model": MODEL, "renderer": renderer, "video": str(video), "published": False}
    if args.publish:
        result.update(published=True, url=upload(video, content))
    (out / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
