# Your first background job

A small FastAPI service where slow work happens in a background job. The
endpoint accepts the order in milliseconds (`202`), an Inngest function does
the 8-second work, a status endpoint reports `pending` → `done`, failures are
retried automatically, and a cron function runs every minute with no request
at all.

Built for the FlyRank Backend track assignment (Your first background job).

## Run it (two terminals)

```bash
# 1. The API (port 8000)
pip install -r requirements.txt
$env:INNGEST_DEV = "1"          # PowerShell: required for local dev signing
python -m uvicorn main:app --port 8000

# 2. The Inngest Dev Server + dashboard (port 8288), in a second terminal
npx inngest-cli@latest dev -u http://localhost:8000/api/inngest
```

Open the dashboard at http://localhost:8288. Two gotchas worth knowing before
you debug anything: the Python SDK needs `INNGEST_DEV=1` in the API terminal
(or startup raises `SigningKeyMissingError`), and `ctx.step.sleep(id, ms)` is
an **async** call taking **milliseconds** — `await ctx.step.sleep("x", 8000)`,
not the JavaScript-style `"8s"` string. A missing `await` silently skips the
sleep (Python only logs a `RuntimeWarning`), so polling flips to `done`
instantly.

## Endpoints

| Endpoint | What it does |
|---|---|
| `GET /health` | `{"status": "ok"}` |
| `POST /reports` | `{"topic": "cats"}` → `202` with `{id, status: "pending"}` immediately; no topic → `400`, no event sent |
| `GET /reports/{id}` | The report object: `pending`, then `done` + `result`; unknown id → `404` |

## Functions

| Function | Trigger | Work |
|---|---|---|
| `say-hello` | event `test/hello` | 5-second sleep, then returns "Hello from the background!" |
| `make-report` | event `report/requested` | `step.sleep("do-the-slow-work", 8000)` → `step.run("build-report", ...)` saves `done` + result; `retries=2` |
| `heartbeat` | cron `* * * * *` | Logs one line: pending / done / failed counts |

## Proof: 202 first, result later

```
$ time curl -i -X POST http://localhost:8000/reports -H "Content-Type: application/json" -d '{"topic":"cats"}'
HTTP/1.1 202 Accepted
{"id":"d9bfddfd-ea6d-45bf-b27c-ef6a11a64979","status":"pending"}
real: 0.38s          <- the 8-second work is NOT in this request

$ curl -s http://localhost:8000/reports/d9bfddfd-ea6d-45bf-b27c-ef6a11a64979
{"id":"d9bfddfd-ea6d-45bf-b27c-ef6a11a64979","topic":"cats","status":"pending"}
                     <- 1 second later: still pending

$ curl -s http://localhost:8000/reports/d9bfddfd-ea6d-45bf-b27c-ef6a11a64979
{"id":"d9bfddfd-ea6d-45bf-b27c-ef6a11a64979","topic":"cats","status":"done","result":"A very serious report about cats"}
                     <- 10 seconds later: done + result
```

`POST /reports` with no topic returns `400 Bad Request` and sends no event.

## Stage 3 sentence: bad input vs bad moment

A missing topic is wrong input and is rejected at the door with `400` —
retrying it would just produce the same error forever. A temporary failure
inside the job (simulated by `topic: "fail"`, which raises
`RuntimeError("The report oven is broken!")`) is a wrong moment: Inngest
retries it twice with backoff, and the dashboard shows 3 attempts before the
run ends `Failed` (about 1m41s total, visible in the trace).

## Stage 4 sentences: cron expressions

- Every day at 08:00: `0 8 * * *`
- Every Sunday at 22:00: `0 22 * * 0`

The heartbeat itself uses `* * * * *` (every minute) only so two runs can be
observed quickly. Servers usually evaluate cron in UTC — check the timezone
before trusting a schedule.

## Dashboard

`docs/dashboard-runs.png` shows all three functions in one view: a completed
`make-report` (11:55:20 → 11:55:28, the 8-second step), a failed `make-report`
with retries (11:44:56 → 11:46:38), and five `heartbeat` cron runs one minute
apart. `docs/dashboard-failed-retries.png` zooms into the failed run's trace
with its three attempt segments and the error text.

## Note on state

Reports live in an in-memory dict, so they reset when the API restarts. That
is intentional for this assignment — the same lesson as the first CRUD API.
Inngest keeps the job state and step results outside the API process, which is
why a job can outlive a request.
