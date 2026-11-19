# Prompt for the AI rematch

This is the exact prompt I sent to the AI assistant. I wrote it from memory
after building the job system by hand, without copying text from the
assignment document.

## Round 1 prompt

```
Build a small Python/FastAPI service with background jobs. Use the `inngest`
Python package (an Inngest client and the FastAPI serve helper) for jobs and
cron, and no other job library. Keep it under ~120 lines in one main.py.

Requirements:

1. GET /health returns {"status": "ok"}.

2. A POST /reports endpoint accepts JSON {"topic": "cats"}. It must:
   - reject a missing/empty topic with HTTP 400 and send no event,
   - otherwise create a unique id, store {"id", "topic", "status": "pending"}
     in a plain in-memory Python dict,
   - send an event named report/requested with the id and topic in its data,
   - return HTTP 202 with {"id": ..., "status": "pending"} in a few
     milliseconds. No slow work may happen inside this request.

3. An Inngest function make-report triggered by report/requested, with two
   steps: first a sleep step of about 8 seconds, then a run step that marks
   the report "done" and adds a result string mentioning the topic. Configure
   it for 2 retries. With topic "fail", the build step must raise an error so
   the job fails after 3 attempts.

4. GET /reports/<id> returns the stored dict: first "pending", later "done"
   plus the result. Unknown id returns HTTP 404.

5. A third Inngest function heartbeat triggered by a cron expression
   "* * * * *" (every minute) that logs one line counting how many reports
   are pending, done and failed.

6. Add requirements.txt and a .gitignore for __pycache__ and .env.

Assume local development: the Inngest Dev Server runs separately at
localhost:8288 and points at /api/inngest on the app.
```

## Round 2 prompt

Same as round 1 plus these clarifications (what round 1 got wrong):

```
Additions after reviewing round 1:
- In the Python SDK, ctx.step.sleep(step_id, duration_ms) is ASYNC and takes
  milliseconds as an int — write `await ctx.step.sleep("do-the-slow-work",
  8000)`. Do not pass a string like "8s" and do not omit the await.
- The build step handler passed to ctx.step.run must be a nested `async def`,
  not a lambda returning a coroutine.
- local mode needs INNGEST_DEV=1 set for the API process; mention it in a
  short README with both run commands.
- Use `inngest.TriggerCron(cron="* * * * *")` for the cron function.
```
