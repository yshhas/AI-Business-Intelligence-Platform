"""Entry: python -m app.workers.analysis_worker

Or from backend/: python -m app.workers.analysis_worker
"""

from app.workers.analysis_worker import run_forever

if __name__ == "__main__":
    run_forever()
