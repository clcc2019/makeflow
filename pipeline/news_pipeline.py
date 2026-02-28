"""News video production pipeline: script -> images -> TTS -> compose -> post-production."""
from __future__ import annotations

from pathlib import Path

from agents.news_script_agent import NewsScriptAgent
from media.tts import create_tts_engine
from media.image_gen import create_image_generator
from media.image_video import ImageVideoComposer
from media.post_production import PostProduction
from models.database import get_session, init_db, VideoTask, TaskStatus
from utils.file_manager import create_task_dir
from utils.logger import log


class NewsPipeline:
    """Produces a news video with AI-generated scene images, narration, and subtitles."""

    def __init__(self, llm_provider: str | None = None):
        self.llm_provider = llm_provider
        init_db()

    def produce(
        self,
        title: str,
        news_content: str,
        publish: bool = False,
    ) -> str:
        task_dir = create_task_dir()
        task_id = task_dir.name

        session = get_session()
        task = VideoTask(
            task_id=task_id,
            status=TaskStatus.PENDING,
            topic_title=title,
            topic_source="news",
            llm_provider=self.llm_provider or "default",
        )
        session.add(task)
        session.commit()

        try:
            # Step 1: Generate segmented news script
            log.info(f"[{task_id}] Step 1/5: Generating news script...")
            script_agent = NewsScriptAgent(llm_provider=self.llm_provider)
            script = script_agent.generate(title=title, news_content=news_content)

            task.script = script.full_narration
            task.script_word_count = script.word_count
            task.publish_title = script.publish_title
            task.publish_tags = ",".join(script.tags)
            task.status = TaskStatus.SCRIPT_GENERATED
            session.commit()

            log.info(f"[{task_id}] Script: {script.word_count} chars, {len(script.scenes)} scenes")
            for s in script.scenes:
                log.info(f"  Scene {s.scene_id}: {s.narration[:40]}...")

            # Step 2: Generate scene images
            log.info(f"[{task_id}] Step 2/5: Generating {len(script.scenes)} scene images...")
            images_dir = task_dir / "images"
            images_dir.mkdir(exist_ok=True)

            image_gen = create_image_generator()
            image_paths = []
            for scene in script.scenes:
                img_path = str(images_dir / f"scene_{scene.scene_id:02d}.png")
                image_gen.generate(
                    prompt=scene.image_prompt,
                    output_path=img_path,
                    size="1024x1792",
                )
                image_paths.append(img_path)

            # Step 3: TTS
            log.info(f"[{task_id}] Step 3/5: Synthesizing narration...")
            tts_engine = create_tts_engine()
            audio_path = str(task_dir / "audio" / "narration.mp3")
            srt_path = str(task_dir / "subtitle" / "narration.srt")
            tts_result = tts_engine.synthesize(script.full_narration, audio_path, srt_path)

            task.audio_path = audio_path
            task.audio_duration = tts_result.duration
            task.subtitle_path = srt_path
            task.status = TaskStatus.AUDIO_GENERATED
            session.commit()

            # Step 4: Compose image video
            log.info(f"[{task_id}] Step 4/5: Composing image video...")
            composer = ImageVideoComposer(width=1080, height=1920)
            raw_video_path = str(task_dir / "video" / "composed.mp4")
            compose_result = composer.compose(
                image_paths=image_paths,
                audio_path=audio_path,
                srt_path=srt_path,
                output_path=raw_video_path,
            )

            task.video_path = raw_video_path
            task.status = TaskStatus.VIDEO_GENERATED
            session.commit()

            # Step 5: Post-production (BGM + cover)
            log.info(f"[{task_id}] Step 5/5: Post-production...")
            cover_path = str(task_dir / "cover" / "cover.png")
            post = PostProduction()
            post.generate_cover(raw_video_path, script.publish_title, cover_path)

            final_video_path = raw_video_path
            if post.bgm_cfg.get("enabled", False):
                bgm_path = str(task_dir / "video" / "final.mp4")
                final_video_path = post.mix_bgm(raw_video_path, bgm_path)

            task.final_video_path = final_video_path
            task.cover_path = cover_path
            task.status = TaskStatus.POST_PRODUCED
            session.commit()

            log.info(f"[{task_id}] News video produced successfully!")
            log.info(f"  Video: {final_video_path}")
            log.info(f"  Cover: {cover_path}")
            log.info(f"  Duration: {compose_result.duration:.1f}s")

            return task_id

        except Exception as e:
            task.status = TaskStatus.FAILED
            task.error_message = str(e)
            session.commit()
            log.error(f"[{task_id}] Pipeline failed: {e}")
            raise
        finally:
            session.close()
