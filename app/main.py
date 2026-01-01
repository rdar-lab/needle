"""Needle - Java Thread Dump Analyzer Application."""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

from app.api import upload

# Create FastAPI application
app = FastAPI(
    title="Needle - Java Thread Dump Analyzer",
    description="Web application for analyzing Java thread dumps with visualizations",
    version="0.1.0"
)

# Get the current directory
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(CURRENT_DIR, "static")

# Include API routes
app.include_router(upload.router)

# Mount static files
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/")
async def root():
    """Serve the main HTML page."""
    index_file = os.path.join(STATIC_DIR, "index.html")
    return FileResponse(index_file)


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
