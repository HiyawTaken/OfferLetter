# OfferLetter demo — November 4, 2026

- Video: `offerletter-demo.mp4`, 1920 × 1080, H.264 / AAC, 2:17, about 9.1 MB.
- Narration: generated with `en-US-AndrewNeural`, with no music bed. Script is in `voiceover-script.md`.
- Model: Ollama `muse-glimmer:30b`, served on loopback. Both the application fit-check endpoint and `model_client.screen` returned valid results for the public Figma posting. No fallback model was used.
- All contact details, work history and resume information used for the demo are fictional. The dedicated demo workspace is separate from the owner's default data directory.
- Actual pages recorded: [Figma Software Engineer Intern (Summer 2027)](https://job-boards.greenhouse.io/figma/jobs/6143238004) and [Verkada Backend Software Engineer — University Graduate 2027](https://job-boards.greenhouse.io/verkada/jobs/5280545007).
- Figma reached review after required questions were answered. The Verkada recording shows profile fields and education dropdowns filling; its school selector and some additional required fields still need user attention. No claim is made that the entire second application was completed.
- The recorded search found 708 source results before filtering and deduplication. It was paused during screening; the video does not represent all results as screened or completed.
- The form sequence is condensed. Review pauses are held for readability. The title and closing sequences use the supplied motion-graphics repository's actual engine.
- The demo database contains **zero approvals and zero submitted jobs**. No employer Submit control or approval endpoint was used. No accounts or sign-ins were created.
- Onboarding now separates Education and Work experience. Work history supports repeated employers, titles, employment type, location, start/end month, current employment, and responsibilities. Overlapping dates do not inflate the derived experience summary.
- Rehearsal fixes: queued screening stops for paused/terminal runs, and the review table has sufficient width for the Required column.
- Verification: 108 unit tests passed (plus 6 subtests), the full workflow/browser check runner passed, and the entire exported video decoded without errors.
- Code initially pushed as commit `5357afb` under the owner's configured identity, without co-author tags. Final video and rehearsal fixes are pushed in the follow-up commit.

Before submission, upload the MP4 to the hackathon's video host if it requires a public streaming URL. GitHub stores the downloadable file; no Devpost submission has been made.
