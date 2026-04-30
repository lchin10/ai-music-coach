import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import ocr_check

frontend_url = os.getenv("FRONTEND_URL")

app = FastAPI(
    title="AI Music Coach API",
    description="Python FastAPI server for AI Music Coach",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[frontend_url],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(ocr_check.router)


@app.get("/")
async def root():
  return {"status": "ok"}


if __name__ == "__main__":
  import uvicorn
  uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
