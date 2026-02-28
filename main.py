"""MakeFlow - AI 科技科普视频自动化工厂

Usage:
    python main.py                          # Start scheduler (continuous)
    python cli.py topics -n 5               # Select 5 topics
    python cli.py script "AI Agent是什么"    # Generate script for topic
    python cli.py tts "测试语音合成"         # Test TTS
    python cli.py produce -n 1 --no-publish # Produce 1 video without publishing
    python cli.py produce -n 3 --publish    # Produce 3 videos and publish
    python cli.py status                    # Show task status
    python cli.py login                     # Login to platforms (save cookies)
    python cli.py start                     # Start scheduler
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from models.database import init_db
from pipeline.scheduler import PipelineScheduler
from utils.logger import log


def main():
    log.info("MakeFlow - AI 科技科普视频自动化工厂")
    log.info("Initializing database...")
    init_db()

    log.info("Starting scheduler...")
    scheduler = PipelineScheduler()
    scheduler.start()


if __name__ == "__main__":
    main()
