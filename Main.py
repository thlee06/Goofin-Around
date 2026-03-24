import logging
import uvicorn
from app import create_app

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

app = create_app()

if __name__ == "__main__":
    uvicorn.run(
        "Main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        workers=1,  # Must stay at 1 — APScheduler runs in-process
    )
