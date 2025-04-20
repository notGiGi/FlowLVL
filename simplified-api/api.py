from fastapi import FastAPI, HTTPException
import os
import sys
import platform

# Print diagnostic information
print(f"Python version: {sys.version}")
print(f"Platform: {platform.platform()}")

# Create simple FastAPI app without complex dependencies
app = FastAPI(title="Simplified API")

@app.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {
        "status": "online",
        "python_version": sys.version,
        "platform": platform.platform()
    }

@app.get("/status")
async def status():
    """Get service status"""
    return {
        "services": {
            "api": "running",
            "database": "connected" if os.environ.get("DB_HOST") else "not_configured",
            "redis": "connected" if os.environ.get("REDIS_HOST") else "not_configured"
        }
    }

# This is the function that should be imported by the entrypoint
def create_api_app():
    return app
