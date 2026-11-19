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

## AI vs me (bonus stage)

I wrote the prompt from memory (`ai-version/PROMPT.md`) and asked a free
OpenRouter model (`nvidia/nemotron-3.5-super-vl:free`) to build the same job
system. Its code is quarantined in `ai-version/ai1/` and `ai-version/ai2/`;
`ai-version/diff.txt` is the side-by-side diff. I fired the Stage 2 and Stage
3 checkpoints at both rounds.

**Round 1** produced a plausible-looking 79-line app: `/health`, a 202
endpoint, a status endpoint, a make-report function and a cron function — but
it fails at import:

```
AttributeError: module 'inngest' has no attribute 'Client'
```

There is no `inngest.Client` in the Python SDK (it is `inngest.Inngest`), no
`inngest.serve` at package level (the helper lives in `inngest.fast_api`), its
functions declared a second `step` argument that the SDK never passes, and
`@step.run("build")` as a decorator does not exist. It also used
`await step.sleep("wait", "8s")` — a JavaScript-style string where the Python
SDK wants an int number of milliseconds. It silently omitted `say-hello`
entirely. **Round 2** fixed the sleep call to `await ctx.step.sleep(
"do-the-slow-work", 8000)`, but regressed the rest: 46 lines of "demo" app
with no FastAPI endpoints, no reports dict, no `retries=2`, no `topic: "fail"`
branch, and still the non-existent `inngest.Client` — it fails at import the
same way. Neither round could answer a single checkpoint request.

What the AI did better — and I understand it, I adopted it: round 1 validated
the topic with `isinstance(topic, str) and topic.strip()` (mine only checked
truthiness, so `42` was accepted), and it set the report's status to
`"failed"` when the build step raised (mine left failed reports stuck at
`"pending"` forever, which made the heartbeat's failed count meaningless).
Both are now in my `main.py`.

What it got wrong or silently ignored:

1. **Wrong SDK API surface, twice.** `inngest.Client`, package-level
   `inngest.serve`, a second `step` handler argument, and a `@step.run`
   decorator are all invented — every one would be caught by running the
   file, which is exactly what I did before judging it.
2. **The 8-second sleep was fake in round 1.** Passing `"8s"` to an SDK that
   expects milliseconds is the same class of bug I hit in my own Stage 2 —
   except mine silently produced a done report in under a second, so the
   only way to catch it was polling at 1 second instead of trusting a green
   "Completed" in the dashboard.
3. **Round 2 traded correctness for the one flagged line.** It absorbed the
   sleep correction and dropped the API entirely — a reminder that "fix the
   diff" with no regression check can make a system less complete.
4. **No `say-hello` in either round.** The simplest function, with its own
   explicit requirement, was silently left out both times.

What my prompt forgot to specify — and what the AI silently decided for me:
I did not spell out the exact import/wiring names (`inngest.Inngest`,
`inngest.fast_api.serve`, `ctx.step.run`) in round 1, assuming a model would
look them up — it invented plausible alternatives instead. I also never said
what status a failed report should show, so round 1 chose `"failed"` (better
than my choice) while round 2 chose no status at all.

One sentence on what changed between rounds: naming the exact async sleep
syntax in round 2 fixed that one line but cost the rest of the system — no
prompt wording substitutes for running the generated code against the same
checkpoints you used while building it yourself.
