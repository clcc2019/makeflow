import shutil
import uuid
from datetime import datetime
from pathlib import Path

from utils.config import get_settings


def get_output_dir() -> Path:
    settings = get_settings()
    base = Path(settings["output"]["base_dir"])
    base.mkdir(parents=True, exist_ok=True)
    return base


def get_temp_dir() -> Path:
    settings = get_settings()
    temp = Path(settings["output"]["temp_dir"])
    temp.mkdir(parents=True, exist_ok=True)
    return temp


def create_task_dir(task_id: str | None = None) -> Path:
    """Create a directory for a single video production task."""
    if task_id is None:
        task_id = datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:6]
    task_dir = get_output_dir() / task_id
    task_dir.mkdir(parents=True, exist_ok=True)
    for sub in ("audio", "video", "subtitle", "cover"):
        (task_dir / sub).mkdir(exist_ok=True)
    return task_dir


def cleanup_temp():
    temp = get_temp_dir()
    if temp.exists():
        shutil.rmtree(temp)
        temp.mkdir(parents=True, exist_ok=True)
