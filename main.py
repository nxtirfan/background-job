import inngest
from fastapi import FastAPI
from inngest.fast_api import serve

app = FastAPI(title="report-api")

inngest_client = inngest.Inngest(app_id="report-api")


@inngest_client.create_function(
    fn_id="say-hello",
    trigger=inngest.TriggerEvent(event="test/hello"),
)
async def say_hello(ctx: inngest.Context) -> str:
    ctx.step.sleep("wait-5s", "5s")
    return "Hello from the background!"


@app.get("/health")
def health():
    return {"status": "ok"}


serve(app, inngest_client, [say_hello])
