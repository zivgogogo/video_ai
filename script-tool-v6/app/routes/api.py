import json
import re
import asyncio
from datetime import datetime
from dataclasses import asdict
from urllib.parse import quote
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Request
from fastapi.responses import StreamingResponse, PlainTextResponse, HTMLResponse, Response
from sqlalchemy.orm import Session
from app.db import get_db
from app.models import Project, PipelineRun, StageCache
from app.pipeline.executor import (run_pipeline, compute_input_hash,
    run_stage_0, run_stage_1, run_stage_2, run_stage_3, run_stage_4, run_stage_5)
from app.config import TEXT_STORE_DIR, MODEL_POOL
from app.ai.factory import create_ai_provider
from app import text_store
from app.text_store import (save_text as _save_text, load_text as _load_text,
                            save_chapters, clear_chapters)
from app.pipeline.stage0_preprocess import PreprocessResult, Chapter
from app.pipeline.stage1_chapter_analysis import ChapterAnalysis
from app.pipeline.stage2_cross_chapter_synthesis import GlobalAnalysis
from app.pipeline.stage3_script_structure import ScriptStructure, ScenePlan
from app.pipeline.stage4_scene_generation import GeneratedScene

router = APIRouter(prefix="/api")


def _render_import_result(title: str, stats: dict) -> HTMLResponse:
    """Generate HTML status card for HTMX upload/paste responses."""
    # 暗色主题兼容：使用半透明深色背景 + 高可读性文字颜色
    is_error = bool(stats.get("errors"))
    accent_color = "#f87171" if is_error else "#34d399"   # red / green
    accent_bg = "rgba(239,68,68,0.1)" if is_error else "rgba(16,185,129,0.1)"
    accent_border = "rgba(239,68,68,0.25)" if is_error else "rgba(16,185,129,0.25)"
    title_color = "#fca5a5" if is_error else "#34d399"
    icon = stats.get("icon", "⚠️" if is_error else "✅")

    errors_html = ""
    if stats.get("errors"):
        items = "".join(f"<li>{e}</li>" for e in stats["errors"])
        errors_html = (
            f'<div style="margin-top:0.75em;padding:0.75em;'
            f'background:rgba(245,158,11,0.1);border:1px solid rgba(245,158,11,0.2);'
            f'border-radius:6px;font-size:0.9em;color:#fbbf24">'
            f'<strong>⚠ 警告：</strong><ul style="margin:0.25em 0 0;padding-left:1.25em">{items}</ul>'
            f'</div>'
        )

    items_html = "".join(
        f"<div style=\"display:flex;justify-content:space-between;"
        f"padding:0.4em 0;border-bottom:1px solid rgba(255,255,255,0.06)\">"
        f"<span style=\"color:#a0a0b8;font-size:0.9em\">{k}</span>"
        f"<strong style=\"color:#e8e8f0;font-size:0.95em\">{v}</strong></div>"
        for k, v in stats.get("items", [])
    )

    return HTMLResponse(content=f"""<div id="upload-result" style="background:{accent_bg};border:1px solid {accent_border};border-radius:var(--radius);padding:1em;margin-top:0.5em;animation:scaleIn 0.3s ease">
<div style="display:flex;align-items:center;gap:0.5em;margin-bottom:0.75em">
    <span style="font-size:1.5em">{icon}</span>
    <strong style="font-size:1.05em;color:{title_color}">{title}</strong>
</div>
{items_html}
{errors_html}
</div>""")

@router.post("/projects")
async def create_project(
    request: Request,
    title: str = Form(...),
    source_novel: str = Form(""),
    source_author: str = Form(""),
    script_type: str = Form("other"),
    config_json: str = Form("{}"),
    db: Session = Depends(get_db),
):
    project = Project(
        title=title, source_novel=source_novel, source_author=source_author,
        script_type=script_type, config_json=config_json,
    )
    db.add(project)
    db.commit()
    db.refresh(project)

    # HTMX request → return HTML modal fragment
    if request.headers.get("HX-Request"):
        # 内联 SVG 庆祝动画 — 不依赖外部资源
        return HTMLResponse(content=f"""<div id="create-modal-overlay" style="position:fixed;inset:0;background:rgba(0,0,0,0.5);display:flex;align-items:center;justify-content:center;z-index:9999;animation:fadeIn 0.2s ease">
<div id="create-modal" style="background:linear-gradient(145deg,#1a1a35,#1f1f40);border:1px solid rgba(255,255,255,0.1);border-radius:16px;padding:2em;text-align:center;max-width:420px;box-shadow:0 20px 60px rgba(0,0,0,0.5),0 0 40px rgba(99,102,241,0.15);animation:scaleIn 0.3s ease">
<div style="margin-bottom:0.75em;display:flex;justify-content:center">
    <svg width="100" height="100" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
        <defs>
            <linearGradient id="checkGrad" x1="0%" y1="0%" x2="100%" y2="100%">
                <stop offset="0%" style="stop-color:#6366f1"/>
                <stop offset="100%" style="stop-color:#8b5cf6"/>
            </linearGradient>
            <filter id="glow">
                <feGaussianBlur stdDeviation="2" result="blur"/>
                <feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>
            </filter>
        </defs>
        <circle cx="50" cy="50" r="48" fill="none" stroke="url(#checkGrad)" stroke-width="3" opacity="0.3">
            <animate attributeName="r" values="48;52;48" dur="2s" repeatCount="indefinite"/>
            <animate attributeName="opacity" values="0.3;0.6;0.3" dur="2s" repeatCount="indefinite"/>
        </circle>
        <circle cx="50" cy="50" r="42" fill="rgba(99,102,241,0.1)"/>
        <path d="M35 52 L45 62 L65 40" fill="none" stroke="url(#checkGrad)" stroke-width="4" stroke-linecap="round" stroke-linejoin="round" filter="url(#glow)">
            <animate attributeName="stroke-dasharray" values="0,100;100,0" dur="0.6s" fill="freeze"/>
        </path>
    </svg>
</div>
<h2 style="margin:0.25em 0;font-size:1.25em;color:#e8e8f0">项目创建成功！🎉</h2>
<p style="color:#a0a0b8;margin-bottom:1.5em;font-size:0.95em">「{title}」已就绪</p>
<div style="display:flex;gap:0.5em;justify-content:center">
<a href="/projects/{project.id}" style="display:inline-flex;align-items:center;gap:0.3em;padding:0.55em 1.25em;background:linear-gradient(135deg,#6366f1,#8b5cf6);color:#fff;border-radius:8px;text-decoration:none;font-size:0.95em;font-weight:600">🚀 前往项目工作台</a>
<button onclick="document.getElementById('create-modal-overlay').remove()" style="padding:0.55em 1.25em;background:rgba(255,255,255,0.06);color:#a0a0b8;border:1px solid rgba(255,255,255,0.1);border-radius:8px;cursor:pointer;font-size:0.95em">✕ 关闭</button>
</div>
</div>
</div>
<script>
setTimeout(function() {{
    var overlay = document.getElementById('create-modal-overlay');
    if (overlay) {{
        overlay.style.transition = 'opacity 0.3s';
        overlay.style.opacity = '0';
        setTimeout(function() {{ if (overlay.parentNode) overlay.remove(); }}, 300);
    }}
}}, 4000);
</script>
""")

    return {"id": project.id, "title": project.title}

@router.post("/projects/{project_id}/upload")
async def upload_file(project_id: str, request: Request,
                      file: UploadFile = File(...),
                      db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    content = await file.read()
    filename = file.filename or "upload.txt"

    if filename.endswith(".docx"):
        from app.pipeline.stage0_preprocess import preprocess_docx
        result = preprocess_docx(content)
        text = ""
    elif filename.endswith(".md"):
        text = content.decode("utf-8", errors="replace")
        from app.pipeline.stage0_preprocess import preprocess_markdown
        result = preprocess_markdown(text)
    else:
        text = content.decode("utf-8", errors="replace")
        from app.pipeline.stage0_preprocess import preprocess_text
        result = preprocess_text(text)

    # Save text so pipeline can read it later
    _save_text(project_id, text)
    text_store.clear_chapters(project_id)

    resp_data = {
        "filename": filename,
        "chapters": len(result.chapters),
        "total_chars": result.total_chars,
        "title": result.title,
        "errors": result.errors,
    }

    if request.headers.get("HX-Request"):
        return _render_import_result("导入成功！", {
            "icon": "✅",
            "items": [
                ("文件名", filename),
                ("章节数", f"{len(result.chapters)} 章"),
                ("总字数", f"{result.total_chars:,}"),
            ],
            "errors": result.errors,
        })

    return resp_data

def _extract_file_text(filename: str, content: bytes) -> str:
    """按文件类型提取纯文本（.docx / .md / 其他按 UTF-8 文本）。"""
    if filename.lower().endswith(".docx"):
        from io import BytesIO
        from docx import Document
        return "\n".join(p.text for p in Document(BytesIO(content)).paragraphs)
    text = content.decode("utf-8", errors="replace")
    if filename.lower().endswith(".md"):
        import markdown
        return re.sub(r'<[^>]+>', '', markdown.markdown(text))
    return text


@router.post("/projects/{project_id}/upload-multi")
async def upload_multi_files(project_id: str, request: Request,
                             files: list[UploadFile] = File(...),
                             db: Session = Depends(get_db)):
    """v2：一次性导入多个章节文档，按上传顺序合并章节结构。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    from app.pipeline.stage0_preprocess import _split_chapters

    all_chapters: list = []   # [(title, content)]
    per_file: list = []       # [(filename, chapter_count)]
    errors: list = []

    for f in files:
        content = await f.read()
        name = f.filename or "upload.txt"
        try:
            text = _extract_file_text(name, content)
        except Exception as e:
            errors.append(f"{name}：解析失败（{e}）")
            continue
        if not text.strip():
            errors.append(f"{name}：内容为空")
            continue
        chapters = _split_chapters(text)
        if len(chapters) <= 1:
            # 文件内没有章节标题 → 整个文件作为一章，标题取文件名
            title = re.sub(r'\.(txt|docx|md)$', '', name, flags=re.I)
            chapters = [(title, text.strip())]
        all_chapters.extend(chapters)
        per_file.append((name, len(chapters)))

    if not all_chapters:
        raise HTTPException(400, "所选文件没有可导入的章节内容")

    # 统一重新编号并落盘：章节结构供 stage0 直接复用，全文供展示
    chapter_objs = [Chapter(index=i, title=t, content=c)
                    for i, (t, c) in enumerate(all_chapters)]
    save_chapters(project_id, [
        {"index": c.index, "title": c.title,
         "content": c.content, "char_count": c.char_count}
        for c in chapter_objs])
    combined = "\n\n".join(
        f"第{i + 1}章 {t}\n\n{c}" for i, (t, c) in enumerate(all_chapters))
    _save_text(project_id, combined)
    # 重新导入后旧缓存失效
    clear_chapters_cache(project_id, db)

    total_chars = sum(c.char_count for c in chapter_objs)
    resp_data = {
        "files": [n for n, _ in per_file],
        "chapters": len(chapter_objs),
        "total_chars": total_chars,
        "errors": errors,
    }

    if request.headers.get("HX-Request"):
        return _render_import_result("多文件导入成功！", {
            "icon": "✅",
            "items": [
                ("导入文件", f"{len(per_file)} 个"),
                ("章节数", f"{len(chapter_objs)} 章"),
                ("总字数", f"{total_chars:,}"),
            ],
            "errors": errors,
        })

    return resp_data


def clear_chapters_cache(project_id: str, db: Session):
    """删除该项目的流水线阶段缓存，避免旧解析结果残留。"""
    db.query(StageCache).filter(StageCache.project_id == project_id).delete()
    db.commit()


@router.post("/projects/{project_id}/paste")
async def paste_text(project_id: str, request: Request,
                     db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        text = body.get("text", "")
    else:
        form = await request.form()
        text = form.get("text", "")
    if len(text) > 500_000:
        raise HTTPException(400, "文本超过 50 万字上限")

    from app.pipeline.stage0_preprocess import preprocess_text
    result = preprocess_text(text)

    # Save text so pipeline can read it later
    _save_text(project_id, text)
    text_store.clear_chapters(project_id)

    resp_data = {
        "chapters": len(result.chapters),
        "total_chars": result.total_chars,
        "title": result.title,
        "errors": result.errors,
        "text": text,
    }

    if request.headers.get("HX-Request"):
        return _render_import_result("解析完成！", {
            "icon": "✅",
            "items": [
                ("章节数", f"{len(result.chapters)} 章"),
                ("总字数", f"{result.total_chars:,}"),
            ],
            "errors": result.errors,
        })

    return resp_data


@router.get("/projects/{project_id}/text")
async def get_text(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    text = _load_text(project_id)
    return {"text": text, "project_id": project_id}

@router.post("/projects/{project_id}/run")
async def run_pipeline_endpoint(project_id: str, request: Request,
                                db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    body = await request.json()
    text = body.get("text", "") or _load_text(project_id)
    if text:
        _save_text(project_id, text)
    if not text:
        raise HTTPException(400, "请先上传或粘贴小说文本")

    meta = {
        "title": project.title,
        "source_novel": project.source_novel,
        "source_author": project.source_author,
        "script_type": project.script_type,
        "version": "0.1.0",
        "created_at": project.created_at,
        "language": "zh-CN",
    }
    config = project.config()
    config["script_type"] = project.script_type

    run = PipelineRun(project_id=project_id)
    project.status = "processing"
    db.add(run)
    db.commit()

    import time as _time
    _start_time = _time.time()

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()
        pipeline_state = None

        async def progress_callback(msg):
            msg["elapsed"] = round(_time.time() - _start_time, 1)
            await queue.put(msg)

        async def run_pipeline_task():
            nonlocal pipeline_state

            async def cache_get(pid, stage, input_hash):
                row = db.query(StageCache).filter(
                    StageCache.project_id == pid,
                    StageCache.stage == stage,
                    StageCache.input_hash == input_hash,
                ).first()
                if row and row.output_json:
                    try:
                        return _deserialize_stage_result(stage, row.output_json)
                    except Exception:
                        return None
                return None

            async def cache_put(pid, stage, input_hash, result):
                existing = db.query(StageCache).filter(
                    StageCache.project_id == pid,
                    StageCache.stage == stage,
                    StageCache.input_hash == input_hash,
                ).first()
                if not existing:
                    cache = StageCache(
                        project_id=pid, stage=stage,
                        input_hash=input_hash,
                        output_json=_serialize_stage_result(result),
                    )
                    db.add(cache)
                    db.commit()

            return await run_pipeline(project_id, text, meta, config,
                                      progress_callback=progress_callback,
                                      cache_get=cache_get, cache_put=cache_put)

        task = asyncio.create_task(run_pipeline_task())

        while not task.done() or not queue.empty():
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=0.5)
                _inject_percent(msg)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"

        pipeline_state = task.result()

        project.status = "done" if not pipeline_state.errors else "error"
        db.commit()

        assembly = pipeline_state.stage_results.get("assembly")
        total_elapsed = round(_time.time() - _start_time, 1)
        final_msg = {
            "status": "complete",
            "percent": 100,
            "elapsed": total_elapsed,
            "errors": pipeline_state.errors,
            "yaml_text": assembly.yaml_text if assembly else "",
            "screenplay_text": assembly.screenplay_text if assembly else "",
        }
        yield f"data: {json.dumps(final_msg, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/projects/{project_id}/run-stage/{stage}")
async def run_single_stage(project_id: str, stage: int, request: Request,
                           db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    config = project.config()
    config["script_type"] = project.script_type

    meta = {
        "title": project.title,
        "source_novel": project.source_novel,
        "source_author": project.source_author,
        "script_type": project.script_type,
        "version": "0.1.0",
        "created_at": project.created_at,
        "language": "zh-CN",
    }

    run = db.query(PipelineRun).filter(
        PipelineRun.project_id == project_id
    ).order_by(PipelineRun.started_at.desc()).first()

    if not run:
        run = PipelineRun(project_id=project_id, started_at="")
        db.add(run)
        db.commit()

    project.status = "processing"
    run.paused = 0
    run.paused_at_stage = None
    db.commit()

    run_id = run.id  # save before detach
    body_data = await request.json()
    input_text = body_data.get("text", "") or _load_text(project_id)
    if input_text:
        _save_text(project_id, input_text)

    import time as _time_stage
    _stage_start = _time_stage.time()

    async def event_stream():
        queue: asyncio.Queue = asyncio.Queue()

        async def notify(msg):
            await queue.put({
                "project_id": project_id,
                "current_stage": stage,
                "stage_status": {stage: "running"},
                "message": msg,
                "elapsed": round(_time_stage.time() - _stage_start, 1),
            })

        async def notify_progress(msg: str, percent: int):
            """带细粒度进度的通知（分步模式下按章/按场推进进度条）。"""
            await queue.put({
                "project_id": project_id,
                "current_stage": stage,
                "stage_status": {stage: "running"},
                "message": msg,
                "percent": percent,
                "elapsed": round(_time_stage.time() - _stage_start, 1),
            })

        async def cache_get(pid, stg, input_hash):
            row = db.query(StageCache).filter(
                StageCache.project_id == pid,
                StageCache.stage == stg,
                StageCache.input_hash == input_hash,
            ).first()
            if row and row.output_json:
                try:
                    return _deserialize_stage_result(stg, row.output_json)
                except Exception:
                    return None
            return None

        async def cache_put(pid, stg, input_hash, result):
            existing = db.query(StageCache).filter(
                StageCache.project_id == pid,
                StageCache.stage == stg,
                StageCache.input_hash == input_hash,
            ).first()
            if not existing:
                cache = StageCache(
                    project_id=pid, stage=stg,
                    input_hash=input_hash,
                    output_json=_serialize_stage_result(result),
                )
                db.add(cache)
                db.commit()

        async def run_task():
            """阶段任务：轮转顶尖模型池，单模型失败自动切换下一个。"""
            models = MODEL_POOL or [None]
            n = len(models)
            order = [models[(stage - 1 + i) % n] for i in range(n)]
            last_err = None
            for m in order:
                provider = create_ai_provider(model=m) if m else create_ai_provider()
                try:
                    return await _dispatch(provider)
                except Exception as e:
                    last_err = e
            raise last_err

        async def _dispatch(provider):

            if stage == 0:
                if not input_text:
                    raise ValueError("请提供小说文本")
                return await run_stage_0(project_id, input_text, notify, cache_get, cache_put)

            elif stage == 1:
                s0 = _get_latest_cached(db, project_id, 0)
                if s0 is None:
                    raise ValueError("请先运行 Stage 0")
                if not input_text:
                    raise ValueError("请提供小说文本")
                n_ch = len(s0.chapters)
                s1_done = 0

                async def on_chapter_done():
                    nonlocal s1_done
                    s1_done += 1
                    await notify_progress(f"章节分析 {s1_done}/{n_ch}",
                                          min(5 + int(s1_done / n_ch * 30), 35))

                return await run_stage_1(project_id, input_text, s0.chapters, provider,
                                         notify, on_chapter_done, cache_get, cache_put)

            elif stage == 2:
                s1 = _get_latest_cached(db, project_id, 1)
                if s1 is None:
                    raise ValueError("请先运行 Stage 1")
                return await run_stage_2(project_id, s1, provider, notify, cache_get, cache_put)

            elif stage == 3:
                s2 = _get_latest_cached(db, project_id, 2)
                s0 = _get_latest_cached(db, project_id, 0)
                if s2 is None:
                    raise ValueError("请先运行 Stage 2")
                if s0:
                    config["num_chapters"] = len(s0.chapters)
                return await run_stage_3(project_id, s2, config, provider, notify, cache_get, cache_put)

            elif stage == 4:
                s2 = _get_latest_cached(db, project_id, 2)
                s3 = _get_latest_cached(db, project_id, 3)
                s0 = _get_latest_cached(db, project_id, 0)
                if s2 is None or s3 is None or s0 is None:
                    raise ValueError("请先运行 Stage 0-3")
                chapter_texts = {ch.index: ch.content for ch in s0.chapters}
                n_sc = len(s3.scenes)
                s4_done = 0

                async def on_scene_done():
                    nonlocal s4_done
                    s4_done += 1
                    await notify_progress(f"场景生成 {s4_done}/{n_sc}",
                                          min(55 + int(s4_done / n_sc * 40), 95))

                return await run_stage_4(project_id, s3, s2.characters, chapter_texts, None,
                                         provider, notify, on_scene_done, cache_get, cache_put)

            elif stage == 5:
                s2 = _get_latest_cached(db, project_id, 2)
                s3 = _get_latest_cached(db, project_id, 3)
                s4 = _get_latest_cached(db, project_id, 4)
                if s2 is None or s3 is None or s4 is None:
                    raise ValueError("请先运行 Stage 0-4")
                # 过滤空场景（兜底），正常流程在 run_stage_4 中已处理
                s4_filtered = [s for s in s4 if s.content]
                if len(s4_filtered) < len(s4):
                    skipped = len(s4) - len(s4_filtered)
                    names = ", ".join(s.id for s in s4 if not s.content)
                    await notify(f"⚠ 跳过 {skipped} 个空场景（{names}）")
                return await run_stage_5(project_id, meta, config, s2, s3, s4_filtered,
                                         notify, cache_get, cache_put)

            raise ValueError(f"未知 stage: {stage}")

        task = asyncio.create_task(run_task())

        while not task.done() or not queue.empty():
            try:
                msg = await asyncio.wait_for(queue.get(), timeout=0.5)
                _inject_percent(msg)
                yield f"data: {json.dumps(msg, ensure_ascii=False)}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"

        try:
            result = task.result()
        except Exception as e:
            run_obj = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
            if run_obj:
                run_obj.error_message = str(e)
                run_obj.stage_status_json = json.dumps({stage: "error"})
            project_obj = db.query(Project).filter(Project.id == project_id).first()
            if project_obj:
                project_obj.status = "error"
            db.commit()
            yield f"data: {json.dumps({'status': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
            return

        run_obj = db.query(PipelineRun).filter(PipelineRun.id == run_id).first()
        if run_obj:
            run_obj.current_stage = stage
            statuses = run_obj.stage_status()
            statuses[str(stage)] = "done"
            run_obj.set_stage_status(statuses)

            if stage in (1, 2, 3):
                run_obj.paused = 1
                run_obj.paused_at_stage = stage
            else:
                run_obj.paused = 0
                run_obj.paused_at_stage = None

        project_obj = db.query(Project).filter(Project.id == project_id).first()
        if project_obj:
            if stage in (1, 2, 3):
                project_obj.status = "paused"
            else:
                project_obj.status = "done"

        db.commit()

        total_elapsed_stage = round(_time_stage.time() - _stage_start, 1)
        final_msg = {"status": "complete", "stage": stage, "percent": min((stage + 1) * 100 // 6, 100), "elapsed": total_elapsed_stage}
        if stage == 5 and hasattr(result, 'yaml_text'):
            final_msg["yaml_text"] = result.yaml_text
            final_msg["screenplay_text"] = getattr(result, 'screenplay_text', '')
        yield f"data: {json.dumps(final_msg, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/projects/{project_id}/resume")
async def resume_pipeline(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    run = db.query(PipelineRun).filter(
        PipelineRun.project_id == project_id
    ).order_by(PipelineRun.started_at.desc()).first()

    if not run or not run.paused:
        raise HTTPException(400, "没有暂停的流水线")

    next_stage = (run.paused_at_stage or 0) + 1
    if next_stage > 5:
        raise HTTPException(400, "流水线已完成")

    return {"next_stage": next_stage, "project_id": project_id}


def _get_latest_cached(db: Session, project_id: str, stage: int):
    """Retrieve the latest cached result for a given project+stage."""
    row = db.query(StageCache).filter(
        StageCache.project_id == project_id,
        StageCache.stage == stage,
    ).order_by(StageCache.created_at.desc()).first()
    if row and row.output_json:
        try:
            return _deserialize_stage_result(stage, row.output_json)
        except Exception:
            return None
    return None


def _get_assembly_data(project_id: str, db: Session) -> dict:
    """从 Stage 5 缓存中读取装配结果。"""
    cache_row = db.query(StageCache).filter(
        StageCache.project_id == project_id,
        StageCache.stage == 5,
    ).order_by(StageCache.created_at.desc()).first()

    if cache_row and cache_row.output_json:
        try:
            return json.loads(cache_row.output_json)
        except (json.JSONDecodeError, TypeError):
            pass
    return {}


@router.get("/projects/{project_id}/script.yaml")
async def download_script_yaml(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    data = _get_assembly_data(project_id, db)
    yaml_text = data.get("yaml_text", "")

    if not yaml_text:
        raise HTTPException(404, "剧本 YAML 尚未生成，请先运行流水线")

    safe_name = quote(project.title, safe="")
    return PlainTextResponse(yaml_text, media_type="application/x-yaml",
                             headers={"Content-Disposition":
                                      f"attachment; filename*=UTF-8''{safe_name}.yaml"})


@router.get("/projects/{project_id}/script.pdf")
async def download_script_pdf(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    data = _get_assembly_data(project_id, db)
    yaml_text = data.get("yaml_text", "")

    if not yaml_text:
        raise HTTPException(404, "剧本尚未生成，请先运行流水线")

    import yaml as _yaml
    from app.pipeline.pdf_export import generate_screenplay_pdf
    try:
        parsed = _yaml.safe_load(yaml_text)
        if not isinstance(parsed, dict):
            raise HTTPException(400, "YAML 数据格式无效")
        pdf_bytes = generate_screenplay_pdf(parsed, title=project.title)
    except Exception as e:
        raise HTTPException(500, f"PDF 生成失败: {e}")

    safe_name = quote(project.title, safe="")
    return Response(content=bytes(pdf_bytes), media_type="application/pdf",
                    headers={"Content-Disposition":
                             f"attachment; filename*=UTF-8''{safe_name}.pdf"})


@router.put("/projects/{project_id}/stage/5")
async def save_edited_script(project_id: str, request: Request,
                              db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    body = await request.json()
    yaml_text = body.get("yaml_text", "")
    screenplay_text = body.get("screenplay_text", "")

    cache_row = db.query(StageCache).filter(
        StageCache.project_id == project_id,
        StageCache.stage == 5,
    ).order_by(StageCache.created_at.desc()).first()

    if not cache_row:
        raise HTTPException(404, "剧本尚未生成，无法保存")

    # Update the text fields inside the cached output_json
    try:
        data = json.loads(cache_row.output_json)
    except (json.JSONDecodeError, TypeError):
        data = {}
    if yaml_text:
        data["yaml_text"] = yaml_text
    if screenplay_text:
        data["screenplay_text"] = screenplay_text
    cache_row.output_json = json.dumps(data, ensure_ascii=False)
    db.commit()

    return {"status": "saved"}


# ── Cache helpers ────────────────────────────────────────────────────

def _serialize_stage_result(result) -> str:
    if isinstance(result, list):
        return json.dumps([asdict(item) for item in result], ensure_ascii=False, default=str)
    return json.dumps(asdict(result), ensure_ascii=False, default=str)


def _deserialize_stage_result(stage: int, data: str):
    d = json.loads(data)
    if stage == 0:
        result = PreprocessResult(**{k: v for k, v in d.items() if k != "chapters"})
        result.chapters = [Chapter(**c) for c in d.get("chapters", [])]
        return result
    elif stage == 1:
        return [ChapterAnalysis(**item) for item in d]
    elif stage == 2:
        return GlobalAnalysis(**d)
    elif stage == 3:
        structure = ScriptStructure(**{k: v for k, v in d.items() if k != "scenes"})
        structure.scenes = [ScenePlan(**s) for s in d.get("scenes", [])]
        return structure
    elif stage == 4:
        return [GeneratedScene(**item) for item in d]
    elif stage == 5:
        from app.pipeline.stage5_assembly import AssemblyResult
        # screenplay_text may not exist in old cached data
        d.setdefault("screenplay_text", "")
        return AssemblyResult(**d)
    return d


@router.get("/projects/{project_id}/stage/{stage}")
async def get_stage_result(project_id: str, stage: int, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    caches = db.query(StageCache).filter(
        StageCache.project_id == project_id,
        StageCache.stage == stage,
    ).order_by(StageCache.created_at.desc()).all()

    if not caches:
        return {"stage": stage, "status": "not_run", "data": None}

    latest = caches[0]
    try:
        data = json.loads(latest.output_json)
        return {
            "stage": stage,
            "status": "cached",
            "input_hash": latest.input_hash,
            "created_at": latest.created_at,
            "data": data,
        }
    except (json.JSONDecodeError, TypeError):
        return {"stage": stage, "status": "error", "data": None}


@router.get("/projects/{project_id}/pipeline-status")
async def get_pipeline_status(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    status_map = {}
    for stage in range(6):
        row = db.query(StageCache).filter(
            StageCache.project_id == project_id,
            StageCache.stage == stage,
        ).order_by(StageCache.created_at.desc()).first()
        status_map[str(stage)] = "cached" if row else "pending"

    next_stage = None
    for s in range(6):
        if status_map[str(s)] == "pending":
            next_stage = s
            break
    is_complete = next_stage is None and all(v == "cached" for v in status_map.values())

    # Check if there's an error in the latest run
    last_run = db.query(PipelineRun).filter(
        PipelineRun.project_id == project_id
    ).order_by(PipelineRun.started_at.desc()).first()
    last_error = last_run.error_message if last_run and last_run.error_message else None

    return {
        "stages": status_map,
        "next_stage": next_stage,
        "is_complete": is_complete,
        "project_status": project.status,
        "last_error": last_error,
    }


@router.get("/projects/{project_id}/report")
async def generation_report(project_id: str, db: Session = Depends(get_db)):
    """v3：生成诊断报告——每阶段状态 + 量化指标 + 总体完成结论。"""
    rows = {r.stage: r.output_json for r in db.query(StageCache).filter(
        StageCache.project_id == project_id).all()}
    names = ["文本预处理", "分章节分析", "跨章节综合",
             "剧本结构设计", "逐场内容生成", "组装 & 校验"]
    stages = []
    for i in range(6):
        done = i in rows
        metrics = ""
        if done:
            try:
                metrics = _stage_metrics(i, json.loads(rows[i]))
            except Exception as e:
                metrics = f"指标解析失败: {e}"
        stages.append({"stage": i, "name": names[i],
                       "status": "done" if done else "pending",
                       "metrics": metrics})
    all_done = all(s["status"] == "done" for s in stages)
    return {"stages": stages, "all_done": all_done,
            "progress_percent": sum(s["status"] == "done" for s in stages) * 100 // 6}


def _stage_metrics(i: int, d) -> str:
    if i == 0:
        chs = d.get("chapters", [])
        return f"{len(chs)} 章 / 共 {d.get('total_chars', 0):,} 字"
    if i == 1:
        chars = {c.get("name") for ca in d for c in ca.get("new_characters", [])}
        return f"已分析 {len(d)} 章 / 发现 {len(chars)} 个人物"
    if i == 2:
        return (f"{len(d.get('characters', []))} 人物 / "
                f"{len(d.get('relationships', []))} 关系 / "
                f"主线 {len(d.get('main_plot', ''))} 字")
    if i == 3:
        scenes = d.get("scenes", [])
        eps = {s.get("episode") for s in scenes}
        chs = {s.get("source_chapter") for s in scenes}
        return f"{len(scenes)} 场 / {len(eps)} 集 / 覆盖原著 {len(chs)} 章"
    if i == 4:
        full = [s for s in d if s.get("content")]
        elems = sum(len(s.get("content", [])) for s in d)
        return f"{len(full)}/{len(d)} 场有内容 / {elems} 条剧本元素"
    if i == 5:
        return (f"剧本 {len(d.get('screenplay_text', '')):,} 字 / "
                f"YAML {len(d.get('yaml_text', '')):,} 字")
    return ""


@router.delete("/projects/{project_id}")
async def delete_project(project_id: str, db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    db.delete(project)
    db.commit()
    return {"deleted": project_id}


@router.post("/projects/{project_id}/clear-cache")
async def clear_cache(project_id: str, stage: int = None,
                       db: Session = Depends(get_db)):
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    q = db.query(StageCache).filter(StageCache.project_id == project_id)
    if stage is not None:
        q = q.filter(StageCache.stage == stage)
    count = q.count()
    q.delete()
    db.commit()
    return {"cleared": count, "stage": stage}


# ── Stage 3 场景编排 API ──────────────────────────────────────────

def _renumber_scenes(scenes_data: list) -> list:
    """按 episode 分组后自动重新编号 sequence 和 id。"""
    from collections import defaultdict
    groups = defaultdict(list)
    for s in scenes_data:
        ep = s.get("episode", 1) if isinstance(s, dict) else getattr(s, "episode", 1)
        groups[ep].append(s)

    result = []
    global_seq = 1
    for ep in sorted(groups):
        for i, s in enumerate(groups[ep], 1):
            if isinstance(s, dict):
                s["sequence"] = i
                s["id"] = f"scene_{global_seq:03d}"
            else:
                s.sequence = i
                s.id = f"scene_{global_seq:03d}"
            global_seq += 1
            result.append(s)
    return result


@router.get("/projects/{project_id}/scenes")
async def get_scenes(project_id: str, db: Session = Depends(get_db)):
    """返回 Stage 3 场景列表 JSON，供看板使用。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    structure = _get_latest_cached(db, project_id, 3)
    if structure is None:
        return {"script_type": project.script_type, "scenes": [], "episode_summaries": []}

    scenes_data = [asdict(s) for s in structure.scenes]
    return {
        "script_type": structure.script_type,
        "scenes": scenes_data,
        "episode_summaries": structure.episode_summaries,
        "beat_sheet": structure.beat_sheet,
    }


@router.put("/projects/{project_id}/scenes")
async def save_scenes(project_id: str, request: Request, db: Session = Depends(get_db)):
    """保存完整的场景列表（原子操作），自动重新编号。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    body = await request.json()
    incoming_scenes = body.get("scenes", [])

    # 自动重新编号
    renumbered = _renumber_scenes(incoming_scenes)

    # 查找 Stage 3 缓存行
    cache_row = db.query(StageCache).filter(
        StageCache.project_id == project_id,
        StageCache.stage == 3,
    ).order_by(StageCache.created_at.desc()).first()

    if not cache_row:
        # 如果没有缓存，创建一个新的（罕见但安全处理）
        cache_row = StageCache(project_id=project_id, stage=3, input_hash="manual")
        db.add(cache_row)

    # 重建 ScriptStructure
    structure = _get_latest_cached(db, project_id, 3)
    if structure is None:
        structure = ScriptStructure(script_type=project.script_type)

    structure.scenes = [ScenePlan(**s) for s in renumbered]
    # 更新 episode_summaries（如果前端传了）
    if "episode_summaries" in body:
        structure.episode_summaries = body["episode_summaries"]

    cache_row.output_json = _serialize_stage_result(structure)
    db.commit()

    return {
        "status": "saved",
        "scene_count": len(structure.scenes),
        "scenes": [asdict(s) for s in structure.scenes],
    }


@router.get("/projects/{project_id}/scenes/export")
async def export_scenes(project_id: str, format: str = "json",
                        db: Session = Depends(get_db)):
    """v3：以通用格式导出场景编排（json 机器可读 / md 人类可读）。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    structure = _get_latest_cached(db, project_id, 3)
    if structure is None:
        raise HTTPException(400, "请先运行 Stage 3 生成场景结构")

    scenes_data = [asdict(s) for s in structure.scenes]
    if format == "md":
        md = _storyboard_to_markdown(project, structure, scenes_data)
        return Response(content=md, media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition":
                                 f"attachment; filename=storyboard_{project_id}.md"})
    payload = {
        "format": "script-tool-storyboard",
        "version": 1,
        "project_title": project.title,
        "script_type": structure.script_type,
        "exported_at": datetime.now().isoformat(timespec="seconds"),
        "episode_summaries": structure.episode_summaries,
        "beat_sheet": structure.beat_sheet,
        "scenes": scenes_data,
    }
    return Response(content=json.dumps(payload, ensure_ascii=False, indent=2),
                    media_type="application/json",
                    headers={"Content-Disposition":
                             f"attachment; filename=storyboard_{project_id}.json"})


def _storyboard_to_markdown(project, structure, scenes_data) -> str:
    lines = [f"# 场景编排 — {project.title}", "",
             f"> 类型：{structure.script_type} · 共 {len(scenes_data)} 场 · "
             f"导出时间：{datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    by_ep = {}
    for s in scenes_data:
        by_ep.setdefault(s.get("episode", 1), []).append(s)
    for ep in sorted(by_ep):
        summ = next((e for e in structure.episode_summaries
                     if e.get("episode") == ep), {})
        lines.append(f"## 第 {ep} 集" + (f" 《{summ.get('title','')}》" if summ.get('title') else ""))
        if summ.get("summary"):
            lines.append(f"_{summ.get('summary')}_")
        if summ.get("cliffhanger"):
            lines.append(f"🎬 集末悬念：{summ.get('cliffhanger')}")
        lines.append("")
        for s in by_ep[ep]:
            lines.append(f"### {s['id']}（第{s.get('act',1)}幕 · 来源第{s.get('source_chapter',0)}章）")
            lines.append(f"- 场景：{s.get('location','')} · {s.get('time','')}")
            lines.append(f"- 人物：{'、'.join(s.get('characters_present', [])) or '（无）'}")
            lines.append(f"- 布景：{s.get('setting_description','')}")
            lines.append(f"- 内容概述：{s.get('summary','')}")
            lines.append("")
    return "\n".join(lines)


@router.post("/projects/{project_id}/scenes/import")
async def import_scenes(project_id: str, request: Request,
                        db: Session = Depends(get_db)):
    """v3：导入通用格式的场景编排，覆盖 Stage 3 结构；Stage 4/5 因哈希变化自动重新生成。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")
    body = await request.json()
    incoming = body.get("scenes")
    if not isinstance(incoming, list) or not incoming:
        raise HTTPException(400, "导入内容缺少 scenes 数组")
    required = {"act", "episode", "summary"}
    for i, s in enumerate(incoming):
        if not isinstance(s, dict) or not required.issubset(s.keys()):
            raise HTTPException(400, f"第 {i+1} 个场景缺少必需字段 act/episode/summary")

    renumbered = _renumber_scenes(incoming)
    cache_row = db.query(StageCache).filter(
        StageCache.project_id == project_id, StageCache.stage == 3,
    ).order_by(StageCache.created_at.desc()).first()
    if not cache_row:
        cache_row = StageCache(project_id=project_id, stage=3, input_hash="import")
        db.add(cache_row)
    structure = _get_latest_cached(db, project_id, 3) or ScriptStructure(
        script_type=body.get("script_type", project.script_type))
    structure.scenes = [ScenePlan(**s) for s in renumbered]
    if body.get("episode_summaries"):
        structure.episode_summaries = body["episode_summaries"]
    cache_row.output_json = _serialize_stage_result(structure)
    db.commit()
    return {"status": "imported", "scene_count": len(structure.scenes),
            "note": "编排已覆盖，Stage 4/5 将在下次运行时按新编排重新生成"}


@router.post("/projects/{project_id}/scenes/split/{scene_id}")
async def split_scene(project_id: str, scene_id: str, request: Request,
                      db: Session = Depends(get_db)):
    """拆分场景为两个。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    body = await request.json()
    split_desc = body.get("split_description", "前半部分")

    structure = _get_latest_cached(db, project_id, 3)
    if structure is None:
        raise HTTPException(400, "请先运行 Stage 3")

    target_idx = None
    for i, s in enumerate(structure.scenes):
        if s.id == scene_id:
            target_idx = i
            break

    if target_idx is None:
        raise HTTPException(404, f"场景 {scene_id} 不存在")

    original = structure.scenes[target_idx]

    # 创建两个新场景（前半/后半）
    first_half = ScenePlan(
        id="",  # 由 renumber 生成
        act=original.act,
        episode=original.episode,
        sequence=original.sequence,
        location=original.location,
        time=original.time,
        setting_description=f"（拆分前段：{split_desc}）",
        characters_present=list(original.characters_present),
        summary=f"{original.summary}\n（前半：{split_desc}）",
        source_chapter=original.source_chapter,
    )

    second_half = ScenePlan(
        id="",
        act=original.act,
        episode=original.episode,
        sequence=original.sequence + 1,
        location=original.location,
        time=original.time,
        setting_description="（拆分后段）",
        characters_present=list(original.characters_present),
        summary=f"{original.summary}\n（后半）",
        source_chapter=original.source_chapter,
    )

    # 替换原场景为两个新场景
    structure.scenes[target_idx:target_idx + 1] = [first_half, second_half]
    _renumber_scenes(structure.scenes)

    # 保存
    cache_row = db.query(StageCache).filter(
        StageCache.project_id == project_id,
        StageCache.stage == 3,
    ).order_by(StageCache.created_at.desc()).first()
    if cache_row:
        cache_row.output_json = _serialize_stage_result(structure)
        db.commit()

    return {
        "status": "split",
        "scenes": [asdict(s) for s in structure.scenes],
    }


@router.post("/projects/{project_id}/scenes/merge")
async def merge_scenes(project_id: str, request: Request, db: Session = Depends(get_db)):
    """合并两个场景为一个。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    body = await request.json()
    scene_ids = body.get("scene_ids", [])

    if len(scene_ids) != 2:
        raise HTTPException(400, "请选择恰好 2 个场景进行合并")

    structure = _get_latest_cached(db, project_id, 3)
    if structure is None:
        raise HTTPException(400, "请先运行 Stage 3")

    idx_map = {}
    for i, s in enumerate(structure.scenes):
        idx_map[s.id] = i

    if scene_ids[0] not in idx_map or scene_ids[1] not in idx_map:
        raise HTTPException(404, "场景不存在")

    idx_a, idx_b = idx_map[scene_ids[0]], idx_map[scene_ids[1]]
    if idx_a > idx_b:
        idx_a, idx_b = idx_b, idx_a
        scene_ids[0], scene_ids[1] = scene_ids[1], scene_ids[0]

    scene_a = structure.scenes[idx_a]
    scene_b = structure.scenes[idx_b]

    # 合并 characters_present（去重）
    merged_chars = list(dict.fromkeys(scene_a.characters_present + scene_b.characters_present))

    merged = ScenePlan(
        id="",
        act=scene_a.act,
        episode=scene_a.episode,
        sequence=scene_a.sequence,
        location=scene_a.location or scene_b.location,
        time=scene_a.time or scene_b.time,
        setting_description=f"{scene_a.setting_description}\n{scene_b.setting_description}".strip(),
        characters_present=merged_chars,
        summary=f"{scene_a.summary}\n——\n{scene_b.summary}",
        source_chapter=scene_a.source_chapter or scene_b.source_chapter,
    )

    # 先删后面的，再删前面的
    del structure.scenes[idx_b]
    del structure.scenes[idx_a]
    # 在 idx_a 位置插入合并结果
    structure.scenes.insert(idx_a, merged)
    _renumber_scenes(structure.scenes)

    cache_row = db.query(StageCache).filter(
        StageCache.project_id == project_id,
        StageCache.stage == 3,
    ).order_by(StageCache.created_at.desc()).first()
    if cache_row:
        cache_row.output_json = _serialize_stage_result(structure)
        db.commit()

    return {
        "status": "merged",
        "merged_id": merged.id,
        "scenes": [asdict(s) for s in structure.scenes],
    }


# ── Character Relationship Graph API ─────────────────────────────────

_IMPORTANCE_MAP = {
    "protagonist": 4,
    "antagonist": 3,
    "supporting": 2,
    "cameo": 1,
}

_RELATION_COLORS = {
    "恋人": "#f472b6",
    "夫妻": "#f472b6",
    "情侣": "#f472b6",
    "师徒": "#a78bfa",
    "师傅": "#a78bfa",
    "师父": "#a78bfa",
    "徒弟": "#a78bfa",
    "仇敌": "#ef4444",
    "敌人": "#ef4444",
    "对手": "#ef4444",
    "情敌": "#ef4444",
    "朋友": "#34d399",
    "好友": "#34d399",
    "同伴": "#34d399",
    "父子": "#f59e0b",
    "母子": "#f59e0b",
    "父女": "#f59e0b",
    "母女": "#f59e0b",
    "兄弟": "#f59e0b",
    "姐妹": "#f59e0b",
    "兄妹": "#f59e0b",
    "姐弟": "#f59e0b",
    "亲属": "#f59e0b",
    "主仆": "#60a5fa",
    "上下级": "#60a5fa",
}


def _pick_rel_color(rel_type: str) -> str:
    """Match relationship type to a color, with partial matching."""
    for key, color in _RELATION_COLORS.items():
        if key in rel_type:
            return color
    return "#94a3b8"  # default gray


@router.get("/projects/{project_id}/character-graph")
async def get_character_graph(project_id: str, db: Session = Depends(get_db)):
    """返回角色关系图谱数据（角色 + 关系 + 出场统计 + 关键台词）。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    # Load Stage 2: characters + relationships
    s2 = _get_latest_cached(db, project_id, 2)
    if s2 is None:
        return {"characters": [], "relationships": [], "status": "no_data"}

    # Load Stage 1: chapter analyses for appearance counts + key quotes
    s1 = _get_latest_cached(db, project_id, 1)

    # Build appearance count map from Stage 1
    appear_count: dict[str, int] = {}
    key_quotes_map: dict[str, list] = {}
    if s1:
        for ca in s1:
            for nc in ca.new_characters:
                name = nc.get("name", "") if isinstance(nc, dict) else getattr(nc, "name", "")
                if name:
                    appear_count[name] = appear_count.get(name, 0) + 1
            # Collect dialogue excerpts for key quotes
            for d in ca.dialogue_excerpts:
                speaker = d.get("speaker", "") if isinstance(d, dict) else getattr(d, "speaker", "")
                text = d.get("text", "") if isinstance(d, dict) else getattr(d, "text", "")
                if speaker and text:
                    if speaker not in key_quotes_map:
                        key_quotes_map[speaker] = []
                    if len(key_quotes_map[speaker]) < 3:  # keep max 3 quotes
                        key_quotes_map[speaker].append(text)

    # Enrich characters
    characters_out = []
    for c in s2.characters:
        char_dict = c if isinstance(c, dict) else asdict(c) if hasattr(c, '__dataclass_fields__') else c
        name = char_dict.get("name", "")
        role = char_dict.get("role", "supporting")
        # Try matching by name or aliases for appearance count
        count = appear_count.get(name, 0)
        if count == 0:
            for alias in char_dict.get("aliases", []):
                if appear_count.get(alias, 0) > count:
                    count = appear_count[alias]
        quotes = key_quotes_map.get(name, [])
        if not quotes:
            for alias in char_dict.get("aliases", []):
                if key_quotes_map.get(alias):
                    quotes = key_quotes_map[alias]
                    break

        characters_out.append({
            "name": name,
            "aliases": char_dict.get("aliases", []),
            "role": role,
            "description": char_dict.get("description", ""),
            "traits": char_dict.get("traits", []),
            "first_appearance_chapter": char_dict.get("first_appearance_chapter", 1),
            "appearance_count": count,
            "key_quotes": quotes,
            "importance": _IMPORTANCE_MAP.get(role, 1),
        })

    # Enrich relationships
    relationships_out = []
    for r in s2.relationships:
        rel_dict = r if isinstance(r, dict) else asdict(r) if hasattr(r, '__dataclass_fields__') else r
        rel_type = rel_dict.get("type", "其他")
        relationships_out.append({
            "from": rel_dict.get("from", ""),
            "to": rel_dict.get("to", ""),
            "type": rel_type,
            "description": rel_dict.get("description", ""),
            "color": _pick_rel_color(rel_type),
        })

    return {
        "status": "ok",
        "characters": characters_out,
        "relationships": relationships_out,
    }


@router.post("/projects/{project_id}/scenes/run-stage4")
async def run_stage4_from_kanban(project_id: str, db: Session = Depends(get_db)):
    """从看板直接触发 Stage 4 运行（返回 SSE 流端点 URL）。"""
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(404, "项目不存在")

    structure = _get_latest_cached(db, project_id, 3)
    if structure is None or not structure.scenes:
        raise HTTPException(400, "没有场景数据，请先运行或编辑 Stage 3")

    return {
        "status": "ready",
        "scene_count": len(structure.scenes),
        "run_url": f"/api/projects/{project_id}/run-stage/4",
    }


def _inject_percent(msg: dict):
    """Add percent field based on completed stages.

    如果 executor 已经设置了细粒度的 percent 字段，直接使用；
    否则回退到旧的阶段计数方式（每阶段 16.67%）。
    """
    # 新系统已在 executor 中设置了 percent，无需覆盖
    if "percent" in msg:
        return

    stage_status = msg.get("stage_status", {})
    if stage_status:
        done = sum(1 for v in stage_status.values() if v == "done")
        current = msg.get("current_stage", -1)
        if done == 0 and current >= 0:
            # Step-by-step mode: only current stage in status, assume previous stages done
            msg["percent"] = min(current * 100 // 6, 100)
        else:
            msg["percent"] = min(done * 100 // 6, 100)
    elif msg.get("status") == "complete" and "stage" in msg:
        # Single-stage completion message
        msg["percent"] = (msg["stage"] + 1) * 100 // 6
