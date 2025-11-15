# Architecture

```mermaid
flowchart TD
  A[Admin UI /jp/] --> B[SQLite DB]
  C[Apply UI /jp/apply/:id] --> B
  C --> U[Uploads dir]
  P[Resume Parser] --> B
  H[Heuristic Filters] --> E[Employer View]
  G[Gemini Filters (<=500 tokens)] --> E
  E --> B
```

- Admin UI: create job with description and questions.
- Apply UI: candidate details, answers, resume upload.
- Parser: PyPDF2 / python-docx / txt; stored as text in DB.
- Filters: heuristics + Gemini suggestion (compact stats only);
  applied locally; no resume text leaves device.
