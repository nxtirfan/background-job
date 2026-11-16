from fastapi import FastAPI

app = FastAPI(title="report-api")


@app.get("/health")
def health():
    return {"status": "ok"}
