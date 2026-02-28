from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine, Column, Integer, String, Text, DateTime, Float, Enum as SAEnum
from sqlalchemy.orm import declarative_base, sessionmaker, Session
import enum

from utils.config import get_settings

Base = declarative_base()


class TaskStatus(enum.Enum):
    PENDING = "pending"
    TOPIC_SELECTED = "topic_selected"
    SCRIPT_GENERATED = "script_generated"
    AUDIO_GENERATED = "audio_generated"
    VIDEO_GENERATED = "video_generated"
    POST_PRODUCED = "post_produced"
    PUBLISHED = "published"
    FAILED = "failed"


class VideoTask(Base):
    __tablename__ = "video_tasks"

    id = Column(Integer, primary_key=True, autoincrement=True)
    task_id = Column(String(64), unique=True, nullable=False, index=True)
    status = Column(SAEnum(TaskStatus), default=TaskStatus.PENDING)

    topic_title = Column(String(256))
    topic_source = Column(String(128))
    topic_url = Column(String(512))
    topic_score = Column(Float)

    script = Column(Text)
    script_word_count = Column(Integer)

    audio_path = Column(String(512))
    audio_duration = Column(Float)
    video_path = Column(String(512))
    final_video_path = Column(String(512))
    cover_path = Column(String(512))
    subtitle_path = Column(String(512))

    publish_title = Column(String(256))
    publish_tags = Column(String(512))
    published_platforms = Column(String(256))

    llm_provider = Column(String(64))
    error_message = Column(Text)

    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class TopicHistory(Base):
    __tablename__ = "topic_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(256), nullable=False)
    source = Column(String(128))
    url = Column(String(512))
    score = Column(Float)
    selected = Column(Integer, default=0)
    created_at = Column(DateTime, default=datetime.utcnow)


def get_engine():
    settings = get_settings()
    db_url = settings["database"]["url"]
    db_path = db_url.replace("sqlite:///", "")
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return create_engine(db_url, echo=False)


def init_db():
    engine = get_engine()
    Base.metadata.create_all(engine)
    return engine


def get_session() -> Session:
    engine = get_engine()
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal()
