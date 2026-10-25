# Free repository audit

Reviewed on 2026-10-25 for the Amala two-hour GitHub Actions pipeline.

| Repository | License | Decision | Reason |
|---|---|---|---|
| `Jakeschincariol/youtube-agent-skill` | MIT | Integrated | Hook scoring and title linting are small, deterministic, require no account, and run on the existing CPU runner. |
| `calesthio/OpenMontage` | AGPL-3.0 | Reference only | Its zero-key Piper, Remotion, HyperFrames, and open-media paths are useful, but the full stack duplicates MoneyPrinterTurbo and adds Python, Node, browser rendering, agent orchestration, and AGPL obligations to every two-hour run. |
| `debpalash/VoiceStudio` | AGPL-3.0 plus model licenses | Not in cloud workflow | It is a desktop/local API product built around large PyTorch voice models. CPU mode needs about 5 GB just for the small PyTorch install and would make the GitHub runner slow and fragile. |
| `k2-fsa/OmniVoice` | Apache-2.0 plus model license | Optional future GPU voice | The library is free and capable, but its documented fast path uses PyTorch with NVIDIA, Apple, or Intel GPUs. Standard GitHub-hosted runners provide no GPU. |

The duplicated VoiceStudio URL in the request was reviewed once. The current free production stack remains Groq Free, MoneyPrinterTurbo, Edge TTS, Pillow, FFmpeg, and the MIT YouTube packaging tools.
