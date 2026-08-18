from fastapi import FastAPI

app = FastAPI(title="AnswerLens API")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "healthy"}
