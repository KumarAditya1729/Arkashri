# pyre-ignore-all-errors
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
async def root():
    return {
        "app": "Arkashri Audit OS",
        "version": "1.0.0",
        "status": "active",
        "message": "API is running"
    }

@app.get("/health")
async def health():
    return {
        "status": "healthy",
        "message": "Health check passed"
    }
