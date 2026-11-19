import uuid

import inngest
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from inngest.fast_api import serve

app = FastAPI(title="report-api")

inngest_client = inngest.Inngest(app_id="report-api")

REPORTS: dict = {}


@inngest_client.create_function(
    fn_id="say-hello",
    trigger=inngest.TriggerEvent(event="test/hello"),
)
async def say_hello(ctx: inngest.Context) -> str:
    await ctx.step.sleep("wait-5s", 5000)
    return "Hello from the background!"


@inngest_client.create_function(
    fn_id="make-report",
    trigger=inngest.TriggerEvent(event="report/requested"),
    retries=2,
)
async def make_report(ctx: inngest.Context) -> str:
    report_id = ctx.event.data["id"]
    topic = ctx.event.data["topic"]

    await ctx.step.sleep("do-the-slow-work", 8000)

    async def build() -> str:
        if topic == "fail":
            REPORTS[report_id]["status"] = "failed"
            raise RuntimeError("The report oven is broken!")
        REPORTS[report_id]["status"] = "done"
        REPORTS[report_id]["result"] = f"A very serious report about {topic}"
        return REPORTS[report_id]["result"]

    result = await ctx.step.run("build-report", build)
    return result


@app.post("/reports")
async def create_report(body: dict | None = None):
    topic = (body or {}).get("topic")
    if not isinstance(topic, str) or not topic.strip():
        raise HTTPException(status_code=400, detail="topic is required")
    report_id = str(uuid.uuid4())
    REPORTS[report_id] = {"id": report_id, "topic": topic, "status": "pending"}
    await inngest_client.send(
        inngest.Event(name="report/requested", data={"id": report_id, "topic": topic})
    )
    return JSONResponse(
        status_code=202, content={"id": report_id, "status": "pending"}
    )


@app.get("/reports/{report_id}")
def get_report(report_id: str):
    if report_id not in REPORTS:
        raise HTTPException(status_code=404, detail="report not found")
    return REPORTS[report_id]


@inngest_client.create_function(
    fn_id="heartbeat",
    trigger=inngest.TriggerCron(cron="* * * * *"),
)
async def heartbeat(ctx: inngest.Context) -> str:
    pending = sum(r["status"] == "pending" for r in REPORTS.values())
    done = sum(r["status"] == "done" for r in REPORTS.values())
    failed = sum(r["status"] == "failed" for r in REPORTS.values())
    summary = f"heartbeat: {pending} pending, {done} done, {failed} failed"
    print(summary, flush=True)
    return summary


@app.get("/health")
def health():
    return {"status": "ok"}


serve(app, inngest_client, [say_hello, make_report, heartbeat])
