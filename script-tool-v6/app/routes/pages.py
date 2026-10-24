from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Project

router = APIRouter()


def _project_nav_info(db: Session, current_id: str = "") -> dict:
    """Return nav bar project count info for template rendering."""
    ordered = db.query(Project).order_by(Project.created_at.asc()).all()
    total = len(ordered)
    info = {"project_count": total}
    if total > 0 and current_id:
        for i, p in enumerate(ordered):
            if p.id == current_id:
                info["project_index"] = i + 1
                break
    return info


@router.get("/", response_class=HTMLResponse)
async def index(request: Request, db: Session = Depends(get_db)):
    projects = db.query(Project).order_by(Project.updated_at.desc()).all()
    return request.app.state.templates.TemplateResponse("index.html", {
        "request": request,
        "projects": projects,
        "project_count": len(projects),
    })

@router.get("/projects/new", response_class=HTMLResponse)
async def new_project(request: Request, db: Session = Depends(get_db)):
    total = db.query(Project).count()
    return request.app.state.templates.TemplateResponse("project_new.html", {
        "request": request,
        "project_count": total,
    })

@router.get("/workbench", response_class=HTMLResponse)
async def workbench(request: Request, db: Session = Depends(get_db)):
    """独立「创作工作台」（全局页，不绑定具体小说项目）。"""
    # 返回小说工作台：指向最近编辑的项目（无项目则回项目列表）
    recent = db.query(Project).order_by(Project.updated_at.desc()).first()
    back_url = f"/projects/{recent.id}" if recent else "/"
    back_label = f"小说工作台·{recent.title}" if recent else "项目列表"
    return request.app.state.templates.TemplateResponse("workbench.html", {
        "request": request,
        "back_url": back_url,
        "back_label": back_label,
        **_project_nav_info(db),
    })

@router.get("/projects/{project_id}", response_class=HTMLResponse)
async def project_workspace(project_id: str, request: Request, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return request.app.state.templates.TemplateResponse("404.html", {
            "request": request, "message": "项目不存在"
        }, status_code=404)
    return request.app.state.templates.TemplateResponse("project.html", {
        "request": request,
        "project": project,
        **_project_nav_info(db, project_id),
    })

@router.get("/projects/{project_id}/stage/{stage}", response_class=HTMLResponse)
async def stage_review(project_id: str, stage: int, request: Request, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return request.app.state.templates.TemplateResponse("404.html", {
            "request": request, "message": "项目不存在"
        }, status_code=404)
    return request.app.state.templates.TemplateResponse("stage_review.html", {
        "request": request,
        "project": project,
        "stage": stage,
        **_project_nav_info(db, project_id),
    })

@router.get("/projects/{project_id}/script", response_class=HTMLResponse)
async def script_view(project_id: str, request: Request, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return request.app.state.templates.TemplateResponse("404.html", {
            "request": request, "message": "项目不存在"
        }, status_code=404)
    return request.app.state.templates.TemplateResponse("script_view.html", {
        "request": request,
        "project": project,
        **_project_nav_info(db, project_id),
    })

@router.get("/projects/{project_id}/stage3/kanban", response_class=HTMLResponse)
async def stage3_kanban(project_id: str, request: Request, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return request.app.state.templates.TemplateResponse("404.html", {
            "request": request, "message": "项目不存在"
        }, status_code=404)
    return request.app.state.templates.TemplateResponse("stage3_kanban.html", {
        "request": request,
        "project": project,
        **_project_nav_info(db, project_id),
    })


@router.get("/projects/{project_id}/characters", response_class=HTMLResponse)
async def character_graph(project_id: str, request: Request, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return request.app.state.templates.TemplateResponse("404.html", {
            "request": request, "message": "项目不存在"
        }, status_code=404)
    return request.app.state.templates.TemplateResponse("character_graph.html", {
        "request": request,
        "project": project,
        **_project_nav_info(db, project_id),
    })


@router.get("/projects/{project_id}/prompts", response_class=HTMLResponse)
async def prompt_center(project_id: str, request: Request, db: Session = Depends(get_db)):
    """Prompt 中心：剧本(场)↔分镜(镜) 一一对应，结构化要素编辑与确认。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        return request.app.state.templates.TemplateResponse("404.html", {
            "request": request, "message": "项目不存在"
        }, status_code=404)
    return request.app.state.templates.TemplateResponse("prompt_center.html", {
        "request": request,
        "project": project,
        **_project_nav_info(db, project_id),
    })
