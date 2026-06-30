from __future__ import annotations

import shutil
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app_state import (
    attach_status,
    create_inbox_item,
    get_inbox_item,
    list_inbox_items,
    mark_inbox_item_packaged,
    package_status_events,
    reset_package_status_from_materials,
    set_package_status,
)
from tools.build_reimbursement_package import OUTPUT_ROOT, build_package, export_package
from tools.cwc_rag import query_policy
from tools.diagnose_return import diagnose, export_diagnosis
from tools.ingest_eml import ingest_eml
from tools.supplement_package import rebuild_with_supplements


ROOT = Path("/Users/hao/Documents/自助报销Agent")
UPLOAD_ROOT = ROOT / "data/uploads"
WEB_STATIC = ROOT / "web/static"
WEB_TEMPLATES = ROOT / "web/templates"

app = FastAPI(title="上海大学自助报销 Agent")
templates = Jinja2Templates(directory=str(WEB_TEMPLATES))
app.mount("/static", StaticFiles(directory=str(WEB_STATIC)), name="static")
app.mount("/package-output", StaticFiles(directory=str(OUTPUT_ROOT)), name="package-output")


@app.get("/favicon.ico")
async def favicon() -> Response:
    return Response(status_code=204)


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


def is_validation_package(package: dict) -> bool:
    title = package.get("title") or package.get("id") or ""
    return any(marker in title for marker in ["验证", "测试", "demo", "Demo"])


@app.get("/", response_class=HTMLResponse)
async def index(request: Request, q: str = "") -> HTMLResponse:
    packages = []
    for path in package_dirs():
        package = load_package(path.name)
        if package and not is_validation_package(package):
            packages.append(attach_status(package))
    recent = packages[:8]
    rag_result = query_policy(q, top_k=5) if q.strip() else None
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "packages": packages,
            "recent": recent,
            "inbox_items": list_inbox_items(),
            "rag_result": rag_result,
            "q": q,
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
