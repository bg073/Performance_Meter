# API Surface

## Admin
- GET /jp/ → Admin list
- GET/POST /jp/job/new
- GET /jp/job/<job_id>
- GET /jp/job/<job_id>/candidates
- GET /jp/resume/<path>

## Applicants
- GET/POST /jp/apply/<job_id>

## Filters
- GET /jp/job/<job_id>/filters/propose → heuristic filters
- GET /jp/job/<job_id>/filters/gemini?target=N → Gemini-assisted filters (compact context)
