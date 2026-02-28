"""MakeFlow CLI - AI Video Factory Command Line Interface."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is in sys.path
sys.path.insert(0, str(Path(__file__).parent))

import click
from rich.console import Console
from rich.table import Table

from models.database import init_db, get_session, VideoTask, TaskStatus
from utils.logger import log

console = Console()


@click.group()
def cli():
    """MakeFlow - AI 科技科普视频自动化工厂"""
    init_db()


@cli.command()
@click.option("--count", "-n", default=3, help="Number of topics to select")
@click.option("--provider", "-p", default=None, help="LLM provider (deepseek/openai/qwen/gemini)")
def topics(count: int, provider: str | None):
    """Select trending AI/tech topics."""
    from agents.topic_agent import TopicAgent

    agent = TopicAgent(llm_provider=provider)
    selected = agent.run(count=count)

    table = Table(title=f"Selected Topics ({len(selected)})")
    table.add_column("Score", justify="right", width=6)
    table.add_column("Source", width=12)
    table.add_column("Title", width=50)
    table.add_column("Reasoning", width=30)

    for t in selected:
        table.add_row(f"{t.score:.1f}", t.source, t.title, t.reasoning[:30])

    console.print(table)


@cli.command()
@click.argument("title")
@click.option("--provider", "-p", default=None, help="LLM provider")
def script(title: str, provider: str | None):
    """Generate a video script for a given topic title."""
    from agents.topic_agent import TopicCandidate
    from agents.script_agent import ScriptAgent

    topic = TopicCandidate(title=title, source="cli")
    agent = ScriptAgent(llm_provider=provider)
    result = agent.run(topic)

    console.print(f"\n[bold]Title:[/bold] {result.publish_title}")
    console.print(f"[bold]Tags:[/bold] {', '.join(result.tags)}")
    console.print(f"[bold]Word Count:[/bold] {result.word_count}")
    console.print(f"\n[bold]Script:[/bold]\n{result.full_script}")


@cli.command()
@click.argument("text")
@click.option("--output", "-o", default="./output/test_speech.mp3", help="Output audio path")
def tts(text: str, output: str):
    """Test TTS: synthesize text to speech."""
    from media.tts import create_tts_engine

    Path(output).parent.mkdir(parents=True, exist_ok=True)
    srt_path = output.replace(".mp3", ".srt")

    engine = create_tts_engine()
    result = engine.synthesize(text, output, srt_path)

    console.print(f"Audio: {result.audio_path}")
    console.print(f"Duration: {result.duration:.1f}s")


@cli.command()
@click.option("--count", "-n", default=1, help="Number of videos to produce")
@click.option("--provider", "-p", default=None, help="LLM provider")
@click.option("--publish/--no-publish", default=False, help="Whether to publish after production")
def produce(count: int, provider: str | None, publish: bool):
    """Run the full video production pipeline."""
    from pipeline.video_pipeline import VideoPipeline

    pipeline = VideoPipeline(llm_provider=provider)
    task_ids = pipeline.run_full(topic_count=count, publish=publish)

    console.print(f"\n[bold green]Produced {len(task_ids)} videos:[/bold green]")
    for tid in task_ids:
        console.print(f"  - {tid}")


@cli.command()
@click.argument("title")
@click.argument("script_text")
@click.option("--provider", "-p", default=None, help="LLM provider")
def manual(title: str, script_text: str, provider: str | None):
    """Produce a video from manually provided script text."""
    from pipeline.video_pipeline import VideoPipeline

    pipeline = VideoPipeline(llm_provider=provider)
    task_id = pipeline.produce_from_text(title=title, script_text=script_text, publish=False)

    console.print(f"\n[bold green]Video produced: {task_id}[/bold green]")


@cli.command()
@click.option("--limit", "-l", default=20, help="Number of records to show")
def status(limit: int):
    """Show recent video task status."""
    session = get_session()
    try:
        tasks = (
            session.query(VideoTask)
            .order_by(VideoTask.created_at.desc())
            .limit(limit)
            .all()
        )

        table = Table(title="Video Tasks")
        table.add_column("Task ID", width=25)
        table.add_column("Status", width=16)
        table.add_column("Title", width=30)
        table.add_column("Duration", justify="right", width=8)
        table.add_column("Platforms", width=20)
        table.add_column("Created", width=19)

        for t in tasks:
            status_style = {
                TaskStatus.PUBLISHED: "green",
                TaskStatus.POST_PRODUCED: "yellow",
                TaskStatus.FAILED: "red",
            }.get(t.status, "white")

            table.add_row(
                t.task_id,
                f"[{status_style}]{t.status.value}[/{status_style}]",
                (t.topic_title or "")[:30],
                f"{t.audio_duration:.0f}s" if t.audio_duration else "-",
                t.published_platforms or "-",
                t.created_at.strftime("%Y-%m-%d %H:%M") if t.created_at else "-",
            )

        console.print(table)
    finally:
        session.close()


@cli.command()
@click.option("--provider", "-p", default=None, help="LLM provider")
def start(provider: str | None):
    """Start the automated scheduler (runs continuously)."""
    from pipeline.scheduler import PipelineScheduler

    console.print("[bold]Starting MakeFlow scheduler...[/bold]")
    console.print("Press Ctrl+C to stop\n")

    scheduler = PipelineScheduler(llm_provider=provider)
    scheduler.start()


@cli.command()
@click.argument("title")
@click.argument("news_file", required=False, default=None)
@click.option("--content", "-c", default=None, help="News content text (alternative to file)")
@click.option("--provider", "-p", default=None, help="LLM provider")
def news(title: str, news_file: str | None, content: str | None, provider: str | None):
    """Produce a news video with AI-generated scene images.

    TITLE: The news headline.
    NEWS_FILE: Optional path to a text file with news content.
    """
    from pipeline.news_pipeline import NewsPipeline

    if news_file:
        news_content = Path(news_file).read_text(encoding="utf-8")
    elif content:
        news_content = content
    else:
        console.print("[red]Provide either NEWS_FILE or --content[/red]")
        return

    pipeline = NewsPipeline(llm_provider=provider)
    task_id = pipeline.produce(title=title, news_content=news_content)

    console.print(f"\n[bold green]News video produced: {task_id}[/bold green]")
    console.print(f"Output: output/{task_id}/video/")


@cli.command()
def login():
    """Open browsers for platform login (saves cookies for automation)."""
    import asyncio
    from playwright.async_api import async_playwright

    platforms = {
        "douyin": "https://creator.douyin.com",
        "kuaishou": "https://cp.kuaishou.com",
        "bilibili": "https://member.bilibili.com",
        "xiaohongshu": "https://creator.xiaohongshu.com",
        "weixin_video": "https://channels.weixin.qq.com",
    }

    async def _login():
        async with async_playwright() as pw:
            browser = await pw.chromium.launch(headless=False)

            for name, url in platforms.items():
                console.print(f"\n[bold]Opening {name}...[/bold]")
                console.print(f"Please login at {url}")
                console.print("After login, press Enter to save cookies and continue...")

                context = await browser.new_context()
                page = await context.new_page()
                await page.goto(url)

                input()

                cookie_path = Path(f"./data/cookies/{name}.json")
                cookie_path.parent.mkdir(parents=True, exist_ok=True)
                await context.storage_state(path=str(cookie_path))
                console.print(f"[green]Cookies saved for {name}[/green]")
                await context.close()

            await browser.close()

    asyncio.run(_login())
    console.print("\n[bold green]All platform logins complete![/bold green]")


if __name__ == "__main__":
    cli()
