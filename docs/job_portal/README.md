# Job Portal (Local)

Create job postings with questions, accept resumes, parse locally, and filter candidates—including an optional Gemini-assisted filter suggestion with <=500 token context.

- Admin: /jp/
- Apply: /jp/apply/<job_id>
- Data: data/job_portal/

## Key Features
- Admin UI to create job and questions.
- Public apply link to upload resume.
- Parse PDF/DOCX/TXT to text (local only).
- Local heuristic filters and Gemini-assisted filter suggestion.
- SQLite storage; resumes in data/job_portal/uploads.

## Getting Started
- .\.venv\Scripts\pip install -r requirements.txt
- .\.venv\Scripts\python .\run_job_portal.py

## Docs
- architecture.md
- flows.md
- wireframes.md
- configuration.md
- api.md
- privacy.md
- operations.md
- roadmap.md
