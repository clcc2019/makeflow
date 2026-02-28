from __future__ import annotations

import traceback
from pathlib import Path

from agents.topic_agent import TopicAgent, TopicCandidate
from agents.script_agent import ScriptAgent, VideoScript
from agents.review_agent import ReviewAgent
from media.tts import create_tts_engine
from media.digital_human import create_digital_human_engine
from media.post_production import PostProduction
from publisher.manager import PublishManager
from models.database import get_session, init_db, VideoTask, TaskStatus
from utils.file_manager import create_task_dir
from utils.logger import log


class VideoPipeline:
    """Orchestrates the full video production pipeline from topic to publish."""

    def __init__(self, llm_provider: str | None = None, headless: bool = True):
        self.llm_provider = llm_provider
        self.headless = headless
        init_db()

    def run_full(self, topic_count: int = 3, publish: bool = True) -> list[str]:
        """Run the full pipeline: select topics -> produce videos -> publish."""
        log.info("=" * 60)
        log.info("VIDEO PIPELINE: Starting full run")
        log.info("=" * 60)

        # Step 1: Select topics
        topic_agent = TopicAgent(llm_provider=self.llm_provider)
        topics = topic_agent.run(count=topic_count)
        log.info(f"Selected {len(topics)} topics")

        # Step 2: Produce video for each topic
        results = []
        for i, topic in enumerate(topics, 1):
            log.info(f"\n--- Producing video {i}/{len(topics)}: {topic.title} ---")
            try:
                task_id = self.produce_single(topic, publish=publish)
                results.append(task_id)
            except Exception as e:
                log.error(f"Failed to produce video for '{topic.title}': {e}")
                log.error(traceback.format_exc())

        log.info(f"\nPipeline complete: {len(results)}/{len(topics)} videos produced")
        return results

    def produce_single(
        self,
        topic: TopicCandidate,
        publish: bool = True,
    ) -> str:
        """Produce a single video from topic to final output."""
        task_dir = create_task_dir()
        task_id = task_dir.name

        session = get_session()
        task = VideoTask(
            task_id=task_id,
            status=TaskStatus.PENDING,
            topic_title=topic.title,
            topic_source=topic.source,
            topic_url=topic.url,
            topic_score=topic.score,
            llm_provider=self.llm_provider or "default",
        )
        session.add(task)
        session.commit()

        try:
            # Step 1: Generate script
            log.info(f"[{task_id}] Step 1/5: Generating script...")
            script_agent = ScriptAgent(llm_provider=self.llm_provider)
            script = script_agent.run(topic)

            task.script = script.full_script
            task.script_word_count = script.word_count
            task.status = TaskStatus.SCRIPT_GENERATED
            task.publish_title = script.publish_title
            task.publish_tags = ",".join(script.tags)
            session.commit()

            # Step 2: TTS
            log.info(f"[{task_id}] Step 2/5: Synthesizing speech...")
            tts_engine = create_tts_engine()
            audio_path = str(task_dir / "audio" / "speech.mp3")
            srt_path = str(task_dir / "subtitle" / "speech.srt")
            tts_result = tts_engine.synthesize(script.full_script, audio_path, srt_path)

            task.audio_path = tts_result.audio_path
            task.audio_duration = tts_result.duration
            task.subtitle_path = srt_path
            task.status = TaskStatus.AUDIO_GENERATED
            session.commit()

            # Step 3: Digital human
            log.info(f"[{task_id}] Step 3/5: Generating digital human video...")
            dh_engine = create_digital_human_engine()
            raw_video_path = str(task_dir / "video" / "raw.mp4")
            dh_result = dh_engine.generate(audio_path, raw_video_path)

            task.video_path = dh_result.video_path
            task.status = TaskStatus.VIDEO_GENERATED
            session.commit()

            # Step 4: Post-production
            log.info(f"[{task_id}] Step 4/5: Post-production...")
            post = PostProduction()
            post_result = post.process(
                video_path=raw_video_path,
                srt_path=srt_path,
                title=script.publish_title,
                task_dir=str(task_dir),
            )

            task.final_video_path = post_result["final_video_path"]
            task.cover_path = post_result["cover_path"]
            task.status = TaskStatus.POST_PRODUCED
            session.commit()

            # Step 5: Publish
            if publish:
                log.info(f"[{task_id}] Step 5/5: Publishing to platforms...")
                review_agent = ReviewAgent(llm_provider=self.llm_provider)
                platform_meta = review_agent.generate_platform_metadata(
                    title=script.publish_title,
                    summary=script.full_script[:200],
                    tags=script.tags,
                )

                pub_manager = PublishManager(headless=self.headless)
                pub_results = pub_manager.publish_to_all(
                    video_path=post_result["final_video_path"],
                    cover_path=post_result["cover_path"],
                    platform_metadata=platform_meta,
                )

                published = [r.platform for r in pub_results if r.success]
                task.published_platforms = ",".join(published)
                task.status = TaskStatus.PUBLISHED
            else:
                log.info(f"[{task_id}] Step 5/5: Skipping publish (publish=False)")
                task.status = TaskStatus.POST_PRODUCED

            session.commit()
            log.info(f"[{task_id}] Pipeline complete: {task.final_video_path}")
            return task_id

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            session.commit()
            raise
        finally:
            session.close()

    def produce_from_text(
        self,
        title: str,
        script_text: str,
        publish: bool = False,
    ) -> str:
        """Produce a video from manually provided script text (skip topic & script generation)."""
        topic = TopicCandidate(title=title, source="manual", score=10.0)
        script = VideoScript(
            title=title,
            hook="",
            body=script_text,
            full_script=script_text,
            word_count=len(script_text),
            publish_title=title[:20],
            tags=["AI", "科技", "科普"],
            topic=topic,
        )

        task_dir = create_task_dir()
        task_id = task_dir.name

        session = get_session()
        task = VideoTask(
            task_id=task_id,
            status=TaskStatus.SCRIPT_GENERATED,
            topic_title=title,
            topic_source="manual",
            script=script_text,
            script_word_count=len(script_text),
            publish_title=title[:20],
        )
        session.add(task)
        session.commit()

        try:
            # TTS
            tts_engine = create_tts_engine()
            audio_path = str(task_dir / "audio" / "speech.mp3")
            srt_path = str(task_dir / "subtitle" / "speech.srt")
            tts_result = tts_engine.synthesize(script_text, audio_path, srt_path)

            task.audio_path = audio_path
            task.audio_duration = tts_result.duration
            task.subtitle_path = srt_path
            task.status = TaskStatus.AUDIO_GENERATED
            session.commit()

            # Digital human
            dh_engine = create_digital_human_engine()
            raw_video_path = str(task_dir / "video" / "raw.mp4")
            dh_result = dh_engine.generate(audio_path, raw_video_path)

            task.video_path = raw_video_path
            task.status = TaskStatus.VIDEO_GENERATED
            session.commit()

            # Post-production
            post = PostProduction()
            post_result = post.process(
                video_path=raw_video_path,
                srt_path=srt_path,
                title=title,
                task_dir=str(task_dir),
            )

            task.final_video_path = post_result["final_video_path"]
            task.cover_path = post_result["cover_path"]
            task.status = TaskStatus.POST_PRODUCED
            session.commit()

            log.info(f"[{task_id}] Manual video produced: {task.final_video_path}")
            return task_id

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            session.commit()
            raise
        finally:
            session.close()
