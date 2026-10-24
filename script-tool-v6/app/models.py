import uuid
import json
from datetime import datetime, timezone

from sqlalchemy import Column, String, Text, Integer, ForeignKey, UniqueConstraint
from sqlalchemy.orm import relationship
from app.db import Base

def _uid():
    return uuid.uuid4().hex[:12]

def _now():
    return datetime.now(timezone.utc).isoformat()

class Project(Base):
    __tablename__ = "projects"

    id = Column(String, primary_key=True, default=_uid)
    title = Column(String, nullable=False)
    source_novel = Column(String, default="")
    source_author = Column(String, default="")
    script_type = Column(String, default="other")
    config_json = Column(Text, default="{}")
    status = Column(String, default="draft")
    created_at = Column(String, default=_now)
    updated_at = Column(String, default=_now, onupdate=_now)

    pipeline_runs = relationship("PipelineRun", back_populates="project", cascade="all, delete-orphan")
    stage_caches = relationship("StageCache", back_populates="project", cascade="all, delete-orphan")

    def config(self):
        return json.loads(self.config_json) if self.config_json else {}

    def set_config(self, cfg: dict):
        self.config_json = json.dumps(cfg, ensure_ascii=False)


class PipelineRun(Base):
    __tablename__ = "pipeline_runs"

    id = Column(String, primary_key=True, default=_uid)
    project_id = Column(String, ForeignKey("projects.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False, index=True)
    current_stage = Column(Integer, default=0)
    stage_status_json = Column(Text, default="{}")
    error_message = Column(Text, default="")
    started_at = Column(String, default="")
    completed_at = Column(String, default="")
    paused = Column(Integer, default=0)
    paused_at_stage = Column(Integer, nullable=True)

    project = relationship("Project", back_populates="pipeline_runs")

    def stage_status(self):
        return json.loads(self.stage_status_json) if self.stage_status_json else {}

    def set_stage_status(self, data: dict):
        self.stage_status_json = json.dumps(data, ensure_ascii=False)


class StageCache(Base):
    __tablename__ = "stage_caches"

    id = Column(String, primary_key=True, default=_uid)
    project_id = Column(String, ForeignKey("projects.id", onupdate="CASCADE", ondelete="CASCADE"), nullable=False, index=True)
    stage = Column(Integer, nullable=False)
    input_hash = Column(String, default="")
    output_json = Column(Text, default="{}")
    created_at = Column(String, default=_now)

    project = relationship("Project", back_populates="stage_caches")

    __table_args__ = (
        UniqueConstraint("project_id", "stage", "input_hash", name="uq_stage_cache_lookup"),
    )
