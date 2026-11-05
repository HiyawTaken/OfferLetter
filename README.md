# OfferLetter

OfferLetter is a local-first job application assistant. Set your target roles, add your resume and profile, and let it search relevant listings, screen descriptions with your chosen model, and prepare forms in a Chrome window you can watch. Unknown questions return to you, and every submission requires explicit approval.

## How it works

Search → title and location prefilter → model screening of the description → resume fit check → fill in Chrome → questions → review and approval.

- **Find and apply:** searches LinkedIn, Indeed and a relevant SimplifyJobs student list. Source availability varies; sites may block requests or require sign-in.
- **Profile setup:** separate contact, eligibility, education, and work-experience steps. Add multiple employers with titles, employment type, locations, start/end months, current-job status, and responsibilities. Employment dates replace the manual years-worked question.
- **Screening:** distinguishes matching work, adjacent roles, and unsuitable experience levels. Close matches return for a decision, with reasons.
- **Visible preparation:** fills recognized controls and attaches the selected resume. Custom controls, CAPTCHA and unsupported pages require user action.
- **Answer memory:** choose whether an answer may be reused for one job, similar roles, or every job.
- **Review:** snapshots show answers and highlight sensitive fields. Submission requires explicit approval and is attempted once; uncertain outcomes are not automatically retried.
- **Assistant:** answers questions about the current search and application state.

## Setup

Use Python 3.12+, Google Chrome, and Ollama. From the project folder:

```powershell
python -m pip install -r requirements.txt
python -m playwright install chrome
ollama pull muse-glimmer:30b
python -m uvicorn app:app --host 127.0.0.1 --port 8765
```

Open http://127.0.0.1:8765 and complete onboarding. For local inference, select provider `local`, server `http://127.0.0.1:11434/v1`, and model `muse-glimmer:30b`. A local model server must already be running. This is a large model; check your machine's available resources. Other OpenAI-compatible local models are supported, and output is validated before use.

Set `OFFERLETTER_DATA` to use an isolated workspace. The default `data/` directory holds private profile information, screenshots, and browser sessions. Keep the server on loopback.

## Safety and privacy

- Local-first: profile storage and browser automation run on your computer. Job searches still contact job sites. Cloud models are optional and require acknowledgment before sending resume and posting text.
- Every final submission needs recorded user approval. Inspect every answer and the actual browser form before approving.
- The demonstration uses fictional details, creates no accounts, performs no sign-ins, and submits no employer application.
- Optional account and email tools require separate configuration and user actions. They are not needed for the demo.
- JobSpy uses browser-style TLS impersonation for some sources. CAPTCHA pauses for the user; no working automatic solver is bundled.
- Model judgments can be wrong. Resume quotations are checked against source text; this does not establish that the interpretation is correct.

## Tests

```powershell
python -m pip install -r requirements-dev.txt
python -m pytest -q tests
python run_checks.py
```

Browser checks need Chrome and local networking. Automated tests use controlled fixtures and fictional data. They do not establish support for every real employer form. Workday sign-in walls, LinkedIn Easy Apply and many custom controls still need manual work. Gmail requires a user-supplied Google desktop OAuth client and has not been accepted against a real account.

## Demo

[Watch or download the 90-second montage](demo/offerletter-demo.mp4). It uses fictional details, actual app and Greenhouse recordings, a local Muse model, and the motion-graphics engine requested for the edit. No employer application was submitted.

The demo model was verified against a public posting using both fit-check and screening paths. Demo notes document the final recording, model, limitations and exact employer pages used.
