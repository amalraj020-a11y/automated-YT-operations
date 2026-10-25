# Amala YouTube operations

This project contains Amala's local cartoon pipeline and a cloud pipeline for public Shorts every two hours.

## Current state

- The imported operations workbook is a live Google Sheet in the Amala Raj account: https://docs.google.com/spreadsheets/d/1X0Zkn0JHzXhLUq7aCFdsAopoOephhvAdCT2Y1SgCb3w/edit
- The original five tabs were preserved. `Operations Events` adds the requested event fields. Spreadsheet locale is India and time zone is India Standard Time.
- Local stages are implemented and tested. Two owner-approved public Shorts are live: [largest files](https://youtube.com/shorts/8gNksgap2-o) and [duplicate files](https://youtube.com/shorts/umSJXBdLqzY). See the [daily reports](docs/reports).
- The `YouTube Upload Log` and `Operations Events` tabs contain verified publication rows. Local Sheets API access is still pending.
- Google Sheets automatic synchronization is implemented but **not connected**: application default credentials with Sheets scope are not available here.
- Groq is connected to GitHub Actions through the protected `GROQ_API_KEY` secret. Secrets are never committed.
- Piper is **not available on PATH**. Both published videos used local Windows System.Speech narration. The voice stage also accepts an existing WAV file or configured Piper binary and model.
- The source, examples, graphic builders, workbook, and production reports are in the [GitHub repository](https://github.com/amalraj020-a11y/amala-youtube-operations). See [audit and blockers](docs/AUDIT.md).

## Public publishing every two hours without OpenAI

`.github/workflows/hourly-youtube.yml` runs at minute 17 every two hours on a standard GitHub-hosted runner. `scripts/hourly_cloud.py` uses Groq with the non-OpenAI Qwen model `qwen/qwen3.8-27b` and creates original local visual cards with Pillow. MoneyPrinterTurbo 1.3.9 adds motion, free Edge TTS narration, subtitles, transitions, and the final 9:16 render without calling OpenAI or a paid media provider. If MoneyPrinterTurbo has a temporary failure, the tested local eSpeak NG + FFmpeg renderer takes over so the schedule can continue. The final MP4 is validated and uploaded through the official YouTube Data API. A manual workflow run defaults to generation-only test mode. Scheduled runs publish publicly once YouTube OAuth secrets are configured.

MoneyPrinterTurbo is pinned to its official `mpt` PyPI package. This configuration uses `--video-source local`, so it needs no Pexels, Pixabay, or Coverr key. It uses packaged/local visuals and no background music to avoid stock API limits and music claims. Set `VIDEO_RENDERER=simple` to bypass MoneyPrinterTurbo for troubleshooting.

The MoneyPrinterTurbo template uses animated pan/zoom, shuffled transitions, word-by-word captions with spring motion, five color themes, progress indicators, and topic-specific code panels. These features keep the video dynamic while preserving the zero-cost local-material setup.

The pipeline also vendors the MIT-licensed hook scorer and title linter from [`Jakeschincariol/youtube-agent-skill`](https://github.com/Jakeschincariol/youtube-agent-skill). Groq proposes multiple factual hooks and titles; the local tools rank them before rendering and save the selected scores in `content.json`. This adds no API key, subscription, or Claude dependency.

A reviewed generation-only artifact can be published unchanged by manually running the workflow with `publish=true` and its `artifact_run_id`. The workflow downloads that exact MP4 and metadata, validates both, and uploads without regenerating the video.

Four GitHub Actions secrets are required before scheduled runs can succeed: `GROQ_API_KEY`, `YOUTUBE_CLIENT_ID`, `YOUTUBE_CLIENT_SECRET`, and `YOUTUBE_REFRESH_TOKEN`. The Google OAuth token must belong to the intended Amala channel and include the `youtube.upload` scope. Never commit these values. The workflow marks the upload as containing synthetic media, sets made-for-kids to false, suppresses subscriber notification for hourly frequency, and saves generation evidence for three days.

GitHub schedules are best-effort and may be delayed under high load. Publishing every two hours uses up to 12 YouTube video-upload calls per day, so the Google Cloud project must have sufficient quota. Free Groq limits and model availability can change. The workflow fails closed when generation, content validation, media QA, OAuth, or upload fails.

## Run locally

Use Python 3.12+, FFmpeg, and ffprobe. Install packages from `requirements.txt` in a virtual environment. Set environment variables from `.env.example` through a protected user or service environment; do not commit a filled `.env`.

```powershell
python -m pip install -r requirements.txt
python -m unittest discover -s tests -v
python amala_youtube.py status 2026-10-18
python amala_youtube.py stage 2026-10-18 research --research-file C:\path\to\topic-research.md
python amala_youtube.py stage 2026-10-18 script --script-file C:\path\to\script.md --storyboard-file C:\path\to\storyboard.csv
python amala_youtube.py stage 2026-10-18 voice --voice-file C:\path\to\approved-voice.wav
python amala_youtube.py stage 2026-10-18 graphics
python amala_youtube.py stage 2026-10-18 assemble
python amala_youtube.py stage 2026-10-18 qa
python amala_youtube.py stage 2026-10-18 metadata --title "Accurate title for review"
```

Stages require the prior stage. `progress.json` stores status, timestamps and retry counts; completed stages are skipped on rerun. `--force` explicitly reruns one stage. Every transition is appended to `data/sheet-queue.jsonl`, which remains durable if Sheets is unavailable. Do not delete this queue until its contents have been backed up.

`qa` checks media streams, dimensions and duration. It records human checks as pending. The generated SRT segments captions and needs timing review. A successful technical test does **not** produce `final.mp4` or authorize upload. `metadata` prepares a review package only. There is no public upload command.

## Google Sheets synchronization

`sheet_sync.py` upserts the latest event for each `date:stage` key into `Operations Events`. It reads the existing keys before writing and updates a row on retries, avoiding duplicate event rows. Local events stay in the queue for audit and recovery. It uses Google Application Default Credentials with the Sheets scope; no token is stored in this project.

```powershell
$env:GOOGLE_SHEET_ID='1X0Zkn0JHzXhLUq7aCFdsAopoOephhvAdCT2Y1SgCb3w'
python sheet_sync.py
```

To enable unattended sync, Raj must authorize a suitable Google OAuth client for the Amala account with the Sheets scope, store the resulting credentials outside Git, and confirm `python sheet_sync.py` succeeds. An ordinary browser sign-in does not authorize this local program. Do not paste passwords or tokens into chat.

## Approval and upload

Open `draft.mp4`, `captions.srt`, `asset-sources.md`, `qa-checklist.md`, and `upload-metadata.md`. Correct factual, visual, audio, rights or privacy issues first. Raj's explicit approval is required before any public release. Use YouTube Studio or an authorized YouTube Data API client after authorization; record the real video URL and publication date only after confirmation. `python amala_youtube.py record-upload YYYY-MM-DD --url URL --title TITLE` records verified publication. The current code intentionally has no automated upload action.

Google's current [YouTube Data API quota reference](https://developers.google.com/youtube/data/determine_quota_cost) lists a separate default bucket of 100 `videos.insert` calls per day; [upload authorization](https://developers.google.com/youtube/documentation/authentication) requires OAuth access to the channel. The actual project quota and account access have not been verified here.

## Recovery

Read `python amala_youtube.py status YYYY-MM-DD`, resolve the failed stage's note, then rerun that stage. Completed earlier outputs are preserved. Groq 429 responses have at most two retries with bounded delay. Do not keep retrying an exhausted free quota; resume later or supply an approved local script.

## Excel and Google Drive reports

Every cloud workflow run exports the topic, narration, title, hook scores, renderer, publication result, and YouTube URL to `reports/latest/amala-operations.xlsx`. GitHub Actions commits that workbook back to this repository. To upload a copy to Drive automatically, configure encrypted repository secrets `GOOGLE_DRIVE_CLIENT_ID`, `GOOGLE_DRIVE_CLIENT_SECRET`, and `GOOGLE_DRIVE_REFRESH_TOKEN`; optionally set `GOOGLE_DRIVE_FOLDER_ID`. The Drive OAuth client must include the `drive.file` scope. Without those secrets, the workbook remains safely available in GitHub and the run records a skipped Drive upload.

## Cost policy

No payment method, paid plan, trial, credits, or hosted resource was activated by this project. Local electricity and internet costs still exist. Verify the actual Groq account is on its Free plan and its current limits before setting `GROQ_API_KEY`. See the [official Groq Free limits](https://console.groq.com/docs/rate-limits), [OpenClaw Groq setup](https://docs.openclaw.ai/providers/groq), and [Sheets API limits](https://developers.google.com/workspace/sheets/api/limits).
# AMALA CODE QUEST

The repository includes a zero-cost, no-OpenAI cartoon pilot pipeline. It draws original characters with Pillow, generates narration locally, renders with FFmpeg, burns in captions, validates the MP4, and stops for human review. The pilot used neither OpenAI nor Groq.

Run the pilot on Windows:

```powershell
python scripts/code_quest.py
```

Review output is written to `code-quest-output/episode-001/`. The pilot build is manual so it cannot repeatedly create the same episode. The separate cloud workflow creates and publishes a new Short every two hours.

See `docs/CODE_QUEST_AUDIT.md` for verified environment, voice, security, and integration status.
