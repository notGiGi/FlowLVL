from fastapi import FastAPI
import os
import sys
import platform

# Print diagnostic information
print(f"Python version: {sys.version}")
print(f"Platform: {platform.platform()}")

app = FastAPI(title="Minimal API")

@app.get("/")
async def root():
    return {"message": "Hello World"}

@app.get("/health")
async def health_check():
    return {
        "status": "online",
        "python_version": sys.version,
        "platform": platform.platform()
    }
