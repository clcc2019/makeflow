from __future__ import annotations

from apscheduler.schedulers.blocking import BlockingScheduler
from apscheduler.triggers.cron import CronTrigger

from pipeline.video_pipeline import VideoPipeline
from utils.config import get_settings
from utils.logger import log


def _parse_cron(expr: str) -> dict:
    """Parse 'minute hour day month day_of_week' cron expression."""
    parts = expr.split()
    return {
        "minute": parts[0],
        "hour": parts[1],
        "day": parts[2],
        "month": parts[3],
        "day_of_week": parts[4],
    }


class PipelineScheduler:
    """Scheduled execution of the video production pipeline."""

    def __init__(self, llm_provider: str | None = None):
        self.settings = get_settings()
        self.llm_provider = llm_provider
        self.scheduler = BlockingScheduler()

    def _job_produce(self):
        """Scheduled job: select topics + produce videos (no publish)."""
        log.info("Scheduled job: produce")
        try:
            pipeline = VideoPipeline(llm_provider=self.llm_provider)
            daily_output = self.settings["content"].get("daily_output", 3)
            pipeline.run_full(topic_count=daily_output, publish=False)
        except Exception as e:
            log.error(f"Scheduled produce failed: {e}")

    def _job_publish(self):
        """Scheduled job: publish pending videos."""
        log.info("Scheduled job: publish")
        from models.database import get_session, VideoTask, TaskStatus
        from publisher.manager import PublishManager
        from agents.review_agent import ReviewAgent

        session = get_session()
        try:
            pending = (
                session.query(VideoTask)
                .filter(VideoTask.status == TaskStatus.POST_PRODUCED)
                .order_by(VideoTask.created_at)
                .limit(3)
                .all()
            )

            if not pending:
                log.info("No pending videos to publish")
                return

            review_agent = ReviewAgent(llm_provider=self.llm_provider)
            pub_manager = PublishManager(headless=True)

            for task in pending:
                try:
                    platform_meta = review_agent.generate_platform_metadata(
                        title=task.publish_title or task.topic_title,
                        summary=(task.script or "")[:200],
                        tags=(task.publish_tags or "AI,科技,科普").split(","),
                    )

                    results = pub_manager.publish_to_all(
                        video_path=task.final_video_path,
                        cover_path=task.cover_path,
                        platform_metadata=platform_meta,
                    )

                    published = [r.platform for r in results if r.success]
                    task.published_platforms = ",".join(published)
                    task.status = TaskStatus.PUBLISHED
                    session.commit()
                    log.info(f"Published task {task.task_id} to: {published}")
                except Exception as e:
                    log.error(f"Failed to publish task {task.task_id}: {e}")
        finally:
            session.close()

    def start(self):
        """Start the scheduler with configured cron jobs."""
        sched_cfg = self.settings["schedule"]

        produce_cron = _parse_cron(sched_cfg["produce_cron"])
        self.scheduler.add_job(
            self._job_produce,
            CronTrigger(**produce_cron),
            id="produce",
            name="Produce videos",
            replace_existing=True,
        )

        publish_cron = _parse_cron(sched_cfg["publish_cron"])
        self.scheduler.add_job(
            self._job_publish,
            CronTrigger(**publish_cron),
            id="publish",
            name="Publish videos",
            replace_existing=True,
        )

        log.info("Scheduler started with jobs:")
        log.info(f"  Produce: {sched_cfg['produce_cron']}")
        log.info(f"  Publish: {sched_cfg['publish_cron']}")

        try:
            self.scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            log.info("Scheduler stopped")
