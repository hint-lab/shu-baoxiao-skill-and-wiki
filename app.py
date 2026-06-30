from __future__ import annotations

import shutil
import uuid
from dataclasses import asdict
import os
import json
from pathlib import Path
from collections import Counter

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app_state import (
    attach_status,
    create_inbox_item,
    get_inbox_item,
    get_package_status,
    list_inbox_items,
    mark_inbox_item_packaged,
    package_status_events,
    reset_package_status_from_materials,
    set_package_status,
)
from tools.build_reimbursement_package import OUTPUT_ROOT, build_package, export_package
from tools.cwc_rag import query_policy
from tools.doubao_extractor import api_key as doubao_api_key
from tools.doubao_extractor import base_url as doubao_base_url
from tools.doubao_extractor import enabled as doubao_enabled
from tools.doubao_extractor import model_name as doubao_model_name
from tools.diagnose_return import diagnose, export_diagnosis
from tools.ingest_eml import ingest_eml
from tools.playwright_fill_adapter import ARTIFACT_DIR as PLAYWRIGHT_ARTIFACT_DIR
from tools.playwright_fill_adapter import run_fill
from tools.supplement_package import rebuild_with_supplements


ROOT = Path("/Users/hao/Documents/自助报销Agent")
UPLOAD_ROOT = ROOT / "data/uploads"
WEB_STATIC = ROOT / "web/static"
WEB_TEMPLATES = ROOT / "web/templates"
PLAYWRIGHT_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="上海大学自助报销 Agent")
templates = Jinja2Templates(directory=str(WEB_TEMPLATES))
app.mount("/static", StaticFiles(directory=str(WEB_STATIC)), name="static")
app.mount("/package-output", StaticFiles(directory=str(OUTPUT_ROOT)), name="package-output")
app.mount("/playwright-output", StaticFiles(directory=str(PLAYWRIGHT_ARTIFACT_DIR)), name="playwright-output")


@app.get("/favicon.ico")
async def favicon() -> Response:
    return Response(status_code=204)


@app.get("/api/settings/status")
async def settings_status() -> JSONResponse:
    adapter_path = ROOT / "data/adapters/shu_finance.template.json"
    adapter_text = adapter_path.read_text(encoding="utf-8") if adapter_path.exists() else ""
    index_path = ROOT / "data/cwc/index.json"
    documents_path = ROOT / "data/cwc/documents.jsonl"
    imap_required = {
        "host": os.getenv("REIMBURSEMENT_IMAP_HOST", ""),
        "username": os.getenv("REIMBURSEMENT_IMAP_USERNAME", ""),
        "password": os.getenv("REIMBURSEMENT_IMAP_PASSWORD", ""),
    }
    payload = {
        "doubao": {
            "enabled": doubao_enabled(),
            "has_api_key": bool(doubao_api_key()),
            "has_model": bool(doubao_model_name()),
            "model": doubao_model_name(),
            "base_url": doubao_base_url(),
        },
        "imap": {
            "configured": all(imap_required.values()),
            "host_configured": bool(imap_required["host"]),
            "username_configured": bool(imap_required["username"]),
            "password_configured": bool(imap_required["password"]),
            "mailbox": os.getenv("REIMBURSEMENT_IMAP_MAILBOX", "INBOX"),
            "mark_seen": os.getenv("REIMBURSEMENT_IMAP_MARK_SEEN", "false").lower() == "true",
        },
        "knowledge_base": {
            "index_exists": index_path.exists(),
            "documents_exists": documents_path.exists(),
            "index_size_bytes": index_path.stat().st_size if index_path.exists() else 0,
            "documents_size_bytes": documents_path.stat().st_size if documents_path.exists() else 0,
        },
        "playwright": {
            "mock_adapter_exists": (ROOT / "data/adapters/mock_school.json").exists(),
            "shu_adapter_exists": adapter_path.exists(),
            "shu_adapter_configured": adapter_path.exists() and "填入" not in adapter_text,
        },
    }
    return JSONResponse(payload)


@app.get("/api/knowledge/status")
async def knowledge_status() -> JSONResponse:
    index_path = ROOT / "data/cwc/index.json"
    manifest_path = ROOT / "data/cwc/crawl_manifest.json"
    if not index_path.exists():
        return JSONResponse(
            {
                "index_exists": False,
                "chunk_count": 0,
                "source_types": {},
                "manifest": {},
            }
        )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    source_types = Counter(chunk.get("source_type") or "page" for chunk in index.get("chunks", []))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    return JSONResponse(
        {
            "index_exists": True,
            "chunk_count": index.get("chunk_count", len(index.get("chunks", []))),
            "source_types": dict(source_types),
            "manifest": {
                "base_url": manifest.get("base_url", ""),
                "created_at": manifest.get("created_at", ""),
                "document_count": manifest.get("document_count", 0),
                "page_count": manifest.get("page_count", 0),
                "attachment_count": manifest.get("attachment_count", 0),
            },
        }
    )


def package_dirs() -> list[Path]:
    if not OUTPUT_ROOT.exists():
        return []
    return sorted(
        [p for p in OUTPUT_ROOT.iterdir() if p.is_dir() and (p / "package.json").exists()],
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )


def load_package(package_id: str) -> dict | None:
    path = OUTPUT_ROOT / package_id / "package.json"
    if not path.exists():
        return None
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def load_return_diagnosis(package_id: str) -> dict | None:
    path = OUTPUT_ROOT / package_id / "return_diagnosis.json"
    if not path.exists():
        return None
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def load_fill_report(package_id: str) -> dict | None:
    path = PLAYWRIGHT_ARTIFACT_DIR / f"{package_id}-fill_report.json"
    if not path.exists():
        return None
    import json

    return json.loads(path.read_text(encoding="utf-8"))


def is_validation_package(package: dict) -> bool:
    title = package.get("title") or package.get("id") or ""
    return any(marker in title for marker in ["验证", "测试", "demo", "Demo"])


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, q: str = "", source_type: str = "") -> HTMLResponse:
    packages = []
    for path in package_dirs():
        package = load_package(path.name)
        if package and not is_validation_package(package):
            package["has_return_diagnosis"] = (OUTPUT_ROOT / package["id"] / "return_diagnosis.json").exists()
            packages.append(attach_status(package))
    recent = packages[:8]
    allowed_source_type = source_type if source_type in {"page", "attachment", "local_pdf"} else ""
    rag_result = query_policy(q, top_k=5, source_type=allowed_source_type) if q.strip() else None
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "packages": packages,
            "recent": recent,
            "inbox_items": list_inbox_items(),
            "rag_result": rag_result,
            "q": q,
            "source_type": allowed_source_type,
        },
    )


@app.post("/inbox-items", response_class=HTMLResponse)
async def create_chat_inbox_item(title: str = Form(""), note: str = Form(...)) -> RedirectResponse:
    item_id = uuid.uuid4().hex[:12]
    create_inbox_item(item_id, "chat", title, note)
    return RedirectResponse(url="/#collection", status_code=303)


@app.post("/inbox-items/{item_id}/package", response_class=HTMLResponse)
async def package_inbox_item(item_id: str) -> RedirectResponse:
    item = get_inbox_item(item_id)
    if item is None:
        return RedirectResponse(url="/#collection", status_code=303)
    work_dir = ROOT / "data/package_work" / f"inbox-{item_id}"
    work_dir.mkdir(parents=True, exist_ok=True)
    note_path = work_dir / "随手备注.txt"
    note_path.write_text(item["note"], encoding="utf-8")
    package_title = item["title"] or f"随手记报销包-{item_id}"
    package = build_package(work_dir, item["note"], package_title)
    out_dir = OUTPUT_ROOT / package.id
    export_package(package, out_dir)
    reset_package_status_from_materials(asdict(package), "由资料归集随手记生成报销包")
    mark_inbox_item_packaged(item_id, package.id)
    return RedirectResponse(url=f"/packages/{package.id}/view", status_code=303)


@app.post("/packages", response_class=HTMLResponse)
async def create_package(
    title: str = Form(""),
    note: str = Form(""),
    files: list[UploadFile] = File(...),
) -> RedirectResponse:
    upload_id = uuid.uuid4().hex[:12]
    upload_dir = UPLOAD_ROOT / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    for upload in files:
        if not upload.filename:
            continue
        safe_name = Path(upload.filename).name
        target_dir = upload_dir / "raw_emails" if safe_name.lower().endswith(".eml") else upload_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / safe_name
        with target.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        if safe_name.lower().endswith(".eml"):
            metadata = ingest_eml(target, upload_dir)
            if metadata.body_text:
                note = f"{note}\n邮件主题：{metadata.subject}\n邮件正文：{metadata.body_text}".strip()
    package = build_package(upload_dir, note, title or None)
    out_dir = OUTPUT_ROOT / package.id
    export_package(package, out_dir)
    reset_package_status_from_materials(asdict(package))
    return RedirectResponse(url=f"/packages/{package.id}/view", status_code=303)


@app.get("/packages/{package_id}/view", response_class=HTMLResponse)
async def view_package(request: Request, package_id: str) -> HTMLResponse:
    package = load_package(package_id)
    if package is None:
        return templates.TemplateResponse("not_found.html", {"request": request, "package_id": package_id}, status_code=404)
    package = attach_status(package)
    package_path = OUTPUT_ROOT / package_id
    return templates.TemplateResponse(
        "package.html",
        {
            "request": request,
            "package": package,
            "package_id": package_id,
            "markdown_url": f"/package-output/{package_id}/package.md",
            "json_url": f"/package-output/{package_id}/package.json",
            "playwright_plan_url": f"/package-output/{package_id}/playwright_plan.json",
            "fill_demo_url": f"/packages/{package_id}/fill-demo",
            "fill_report": load_fill_report(package_id),
            "fill_report_url": f"/playwright-output/{package_id}-fill_report.json",
            "fill_screenshot_url": f"/playwright-output/{package_id}-fill_demo.png",
            "return_diagnosis": load_return_diagnosis(package_id),
            "return_diagnosis_url": f"/packages/{package_id}/return-diagnosis",
            "status_events": package_status_events(package_id),
            "file_count": len(list((package_path / "files").glob("*"))) if (package_path / "files").exists() else 0,
        },
    )


@app.post("/packages/{package_id}/status", response_class=HTMLResponse)
async def update_package_status(package_id: str, status: str = Form(...), note: str = Form("")) -> RedirectResponse:
    if load_package(package_id) is not None:
        set_package_status(package_id, status, note)
    return RedirectResponse(url=f"/packages/{package_id}/view", status_code=303)


@app.post("/packages/{package_id}/fill-demo", response_class=HTMLResponse)
def run_package_fill_demo(package_id: str) -> RedirectResponse:
    package = load_package(package_id)
    if package is None:
        return RedirectResponse(url=f"/packages/{package_id}/view", status_code=303)
    status = get_package_status(package_id) or {}
    missing = [item for item in package.get("checklist", []) if item.get("status") == "missing"]
    if status.get("status") != "ready_for_school" or missing:
        return RedirectResponse(url=f"/packages/{package_id}/view", status_code=303)
    plan_path = OUTPUT_ROOT / package_id / "playwright_plan.json"
    if not plan_path.exists():
        return RedirectResponse(url=f"/packages/{package_id}/view", status_code=303)
    run_fill(
        plan_path=plan_path,
        adapter_path=ROOT / "data/adapters/mock_school.json",
        allow_auto_login=True,
        headed=False,
        out=PLAYWRIGHT_ARTIFACT_DIR / f"{package_id}-fill_report.json",
        screenshot=PLAYWRIGHT_ARTIFACT_DIR / f"{package_id}-fill_demo.png",
    )
    return RedirectResponse(url=f"/packages/{package_id}/view", status_code=303)


@app.post("/packages/{package_id}/return-diagnosis", response_class=HTMLResponse)
async def create_return_diagnosis(package_id: str, reason: str = Form(...)) -> RedirectResponse:
    package_json = OUTPUT_ROOT / package_id / "package.json"
    if not package_json.exists():
        return RedirectResponse(url=f"/packages/{package_id}/view", status_code=303)
    diagnosis = diagnose(package_json, reason)
    export_diagnosis(diagnosis, package_json.parent)
    return RedirectResponse(url=f"/packages/{package_id}/return-diagnosis", status_code=303)


@app.post("/packages/{package_id}/supplement", response_class=HTMLResponse)
async def supplement_existing_package(
    package_id: str,
    note: str = Form(""),
    files: list[UploadFile] = File(...),
) -> RedirectResponse:
    package_dir = OUTPUT_ROOT / package_id
    if not (package_dir / "package.json").exists():
        return RedirectResponse(url=f"/packages/{package_id}/view", status_code=303)
    upload_id = uuid.uuid4().hex[:12]
    upload_dir = UPLOAD_ROOT / "supplements" / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    paths = []
    for upload in files:
        if not upload.filename:
            continue
        target = upload_dir / Path(upload.filename).name
        with target.open("wb") as f:
            shutil.copyfileobj(upload.file, f)
        if target.name.lower().endswith(".eml"):
            metadata = ingest_eml(target, upload_dir)
            if metadata.body_text:
                note = f"{note}\n邮件主题：{metadata.subject}\n邮件正文：{metadata.body_text}".strip()
            paths.extend(Path(p) for p in metadata.attachment_paths)
        else:
            paths.append(target)
    if paths:
        rebuild_with_supplements(package_dir, paths, note)
        package = load_package(package_id)
        if package is not None:
            reset_package_status_from_materials(package)
    return RedirectResponse(url=f"/packages/{package_id}/view", status_code=303)


@app.get("/packages/{package_id}/return-diagnosis", response_class=HTMLResponse)
async def view_return_diagnosis(request: Request, package_id: str) -> HTMLResponse:
    package = load_package(package_id)
    diagnosis = load_return_diagnosis(package_id)
    if package is None or diagnosis is None:
        return templates.TemplateResponse("not_found.html", {"request": request, "package_id": package_id}, status_code=404)
    return templates.TemplateResponse(
        "return_diagnosis.html",
        {
            "request": request,
            "package": package,
            "diagnosis": diagnosis,
            "package_id": package_id,
            "markdown_url": f"/package-output/{package_id}/return_diagnosis.md",
            "json_url": f"/package-output/{package_id}/return_diagnosis.json",
        },
    )


@app.get("/mock-school", response_class=HTMLResponse)
async def mock_school_login(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("mock_school_login.html", {"request": request})


@app.get("/mock-school/reimburse", response_class=HTMLResponse)
async def mock_school_reimburse(request: Request) -> HTMLResponse:
    return templates.TemplateResponse("mock_school_reimburse.html", {"request": request})
