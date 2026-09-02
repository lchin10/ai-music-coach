import os
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import practice, sheet_music

# Allow whichever frontend origins are configured. Locally, .env.local sets
# both FRONTEND_URL (prod) and FRONTEND_DEV_URL (http://localhost:3000); in
# production only FRONTEND_URL is set, so only that origin is allowed.
allowed_origins = [
    url
    for url in (os.getenv("FRONTEND_URL"), os.getenv("FRONTEND_DEV_URL"))
    if url
]

app = FastAPI(
    title="AI Music Coach API",
    description="Python FastAPI server for AI Music Coach",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(sheet_music.router)
app.include_router(practice.router)


@app.get("/")
async def root():
  return {"status": "ok"}


if __name__ == "__main__":
  import uvicorn
  uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
