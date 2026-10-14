# CA3 submission artifacts

Everything submitted on the Exam Studio *Project Artifacts* page, kept in the repository so the
documents, the trace and the code can be checked against each other.

| Exam Studio field | What to submit | File here |
| --- | --- | --- |
| Project synopsis (PDF) | upload | [`Skopeo-Project-Synopsis.pdf`](Skopeo-Project-Synopsis.pdf) |
| Design document (PDF) | upload | [`Skopeo-Design-Document.pdf`](Skopeo-Design-Document.pdf) |
| Input definition | paste | [`input-definition.md`](input-definition.md) |
| Output definition | paste | [`output-definition.md`](output-definition.md) |
| GitHub repository URL | `https://github.com/mardromus/Skopeo` | — |
| Project URL | the live Render URL, e.g. `https://skopeo-xxxx.onrender.com` | deployment guide: [`../deployment.md`](../deployment.md) |
| Execution trace | paste the excerpt (it links to the full trace) | [`execution-trace-excerpt.txt`](execution-trace-excerpt.txt), full: [`execution-trace.md`](execution-trace.md), [`execution-trace.json`](execution-trace.json) |
| Demo video URL | upload the video (YouTube unlisted or Google Drive "anyone with the link") and paste its link | recorded from the running system; not stored in git |

## How the trace was produced

A real run through the HTTP API on 15 October 2026: `POST /api/demo/investigations {"fault_injection": true}`
on the bundled repository `examples/vulnerable-demo-repo`, followed by four questions to
`POST /api/investigations/{id}/chat`. The trace was exported unchanged from the Evidence Store with
`backend/app/utils/trace_exporter.py`. The capture ran without an LLM key, so decisions show
`decided_by: policy`. To capture a run in which the model makes the decisions, open a finished case on the
deployed site (with `GROQ_API_KEY` set) and download `GET /api/investigations/{id}/report`; every decision
there records `llm:<model>`.

## Sources

`src/` holds the HTML and SVG the PDFs are rendered from (`node src/render.cjs src/design.html Skopeo-Design-Document.pdf "…"`).
