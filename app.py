from __future__ import annotations

import hashlib
import uuid
from dataclasses import asdict
import os
import json
import shutil
from pathlib import Path
from collections import Counter

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from app_state import (
    attach_status,
    create_inbox_item,
    create_material_item,
    get_inbox_item,
    get_material_item,
    get_package_status,
    list_material_items,
    list_inbox_items,
    mark_material_item_packaged,
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
from tools.poll_imap import STATE_PATH as MAIL_STATE_PATH
from tools.poll_imap import load_state as load_mail_state
from tools.poll_imap import poll_imap
from tools.poll_imap import save_state as save_mail_state
from tools.shu_auth_session import saved_status as shu_auth_saved_status
from tools.supplement_package import rebuild_with_supplements


ROOT = Path("/Users/hao/Documents/自助报销Agent")
UPLOAD_ROOT = ROOT / "data/uploads"
MATERIAL_ROOT = ROOT / "data/material_items"
WEB_STATIC = ROOT / "web/static"
WEB_TEMPLATES = ROOT / "web/templates"
VITE_MANIFEST = WEB_STATIC / "dist/.vite/manifest.json"
PLAYWRIGHT_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

RESPONSIBILITY_CONFIRMATIONS = {
    "funding_project",
    "payment_account",
    "invoice_truth",
    "no_auto_submit",
    "review_before_submit",
}

app = FastAPI(title="上海大学自助报销 Agent")
templates = Jinja2Templates(directory=str(WEB_TEMPLATES))
app.mount("/static", StaticFiles(directory=str(WEB_STATIC)), name="static")
app.mount("/package-output", StaticFiles(directory=str(OUTPUT_ROOT)), name="package-output")
app.mount("/playwright-output", StaticFiles(directory=str(PLAYWRIGHT_ARTIFACT_DIR)), name="playwright-output")


def vite_assets(entry: str) -> Markup:
    dev_server = os.getenv("VITE_DEV_SERVER", "").rstrip("/")
    if dev_server:
        return Markup(
            "\n".join(
                [
                    f'<script type="module" src="{dev_server}/@vite/client"></script>',
                    f'<script type="module" src="{dev_server}/src/{entry}"></script>',
                ]
            )
        )

    fallback = {
        "index.jsx": "/static/app-index.js",
        "package.jsx": "/static/app-package.js",
    }
    if not VITE_MANIFEST.exists():
        return Markup(f'<script src="{fallback[entry]}"></script>')

    manifest = json.loads(VITE_MANIFEST.read_text(encoding="utf-8"))
    entry_key = f"src/{entry}"
    chunk = manifest[entry_key]
    seen_css: set[str] = set()
    css_files: list[str] = []

    def collect_css(chunk_key: str) -> None:
        item = manifest.get(chunk_key, {})
        for imported in item.get("imports", []):
            collect_css(imported)
        for css in item.get("css", []):
            if css not in seen_css:
                seen_css.add(css)
                css_files.append(css)

    collect_css(entry_key)
    tags = [f'<link rel="stylesheet" href="/static/dist/{css}">' for css in css_files]
    tags.append(f'<script type="module" src="/static/dist/{chunk["file"]}"></script>')
    return Markup("\n".join(tags))


templates.env.globals["vite_assets"] = vite_assets


def imap_env_status() -> dict[str, object]:
    required = {
        "host": os.getenv("REIMBURSEMENT_IMAP_HOST", ""),
        "username": os.getenv("REIMBURSEMENT_IMAP_USERNAME", ""),
        "password": os.getenv("REIMBURSEMENT_IMAP_PASSWORD", ""),
    }
    state = load_mail_state(MAIL_STATE_PATH)
    return {
        "configured": all(required.values()),
        "host_configured": bool(required["host"]),
        "username_configured": bool(required["username"]),
        "password_configured": bool(required["password"]),
        "mailbox": os.getenv("REIMBURSEMENT_IMAP_MAILBOX", "INBOX"),
        "mark_seen": os.getenv("REIMBURSEMENT_IMAP_MARK_SEEN", "false").lower() == "true",
        "processed_count": len(state.get("processed", [])),
    }


@app.get("/favicon.ico")
@app.head("/favicon.ico")
async def favicon():
    favicon_path = WEB_STATIC / "icons/favicon.ico"
    if favicon_path.exists():
        return FileResponse(favicon_path)
    return Response(status_code=204)


@app.get("/logo.png")
async def logo() -> FileResponse:
    return FileResponse(ROOT / "logo.png")


@app.get("/icon.png")
async def icon_source() -> FileResponse:
    return FileResponse(ROOT / "icon.png")


@app.get("/api/settings/status")
async def settings_status() -> JSONResponse:
    adapter_path = ROOT / "data/adapters/shu_finance.template.json"
    adapter_text = adapter_path.read_text(encoding="utf-8") if adapter_path.exists() else ""
    index_path = ROOT / "data/cwc/index.json"
    documents_path = ROOT / "data/cwc/documents.jsonl"
    payload = {
        "doubao": {
            "enabled": doubao_enabled(),
            "has_api_key": bool(doubao_api_key()),
            "has_model": bool(doubao_model_name()),
            "model": doubao_model_name(),
            "base_url": doubao_base_url(),
        },
        "imap": imap_env_status(),
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
        "shu_auth": shu_auth_saved_status(),
    }
    return JSONResponse(payload)


@app.post("/api/mail/poll")
async def poll_mailbox(limit: int = Form(10), force: bool = Form(False)) -> JSONResponse:
    imap = imap_env_status()
    if not imap["configured"]:
        return JSONResponse(
            {
                "ok": False,
                "error": "IMAP 未配置完整，请先在本机环境变量中配置邮箱服务器、账号和授权密码。",
                "missing": {
                    "host": not imap["host_configured"],
                    "username": not imap["username_configured"],
                    "password": not imap["password_configured"],
                },
            },
            status_code=400,
        )
    safe_limit = max(1, min(int(limit or 10), 50))
    state = load_mail_state(MAIL_STATE_PATH)
    try:
        results = poll_imap(state, safe_limit, force=bool(force))
        save_mail_state(state, MAIL_STATE_PATH)
    except Exception as exc:
        return JSONResponse(
            {
                "ok": False,
                "error": "邮箱连接或邮件解析失败，请检查本机 IMAP 配置、邮箱授权和网络状态。",
                "error_type": exc.__class__.__name__,
            },
            status_code=502,
        )
    processed = []
    for result in results:
        payload = asdict(result)
        payload["package_id"] = Path(result.package_path).name
        payload.pop("eml_path", None)
        payload.pop("package_path", None)
        processed.append(payload)
    return JSONResponse({"ok": True, "count": len(processed), "processed": processed, "processed_total": len(state.get("processed", []))})


@app.get("/api/knowledge/status")
async def knowledge_status() -> JSONResponse:
    index_path = ROOT / "data/cwc/index.json"
    documents_path = ROOT / "data/cwc/documents.jsonl"
    manifest_path = ROOT / "data/cwc/crawl_manifest.json"
    documents_exists = documents_path.exists()
    if not index_path.exists():
        return JSONResponse(
            {
                "index_exists": False,
                "documents_exists": documents_exists,
                "chunk_count": 0,
                "source_types": {},
                "corpus_report": {},
                "manifest": {},
            }
        )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    source_types = Counter(chunk.get("source_type") or "page" for chunk in index.get("chunks", []))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    corpus_report = index.get("corpus_report") or {}
    return JSONResponse(
        {
            "index_exists": True,
            "documents_exists": documents_exists,
            "index_version": index.get("version", 1),
            "created_at": index.get("created_at", ""),
            "tokenizer": index.get("tokenizer", ""),
            "chunk_count": index.get("chunk_count", len(index.get("chunks", []))),
            "source_types": dict(source_types),
            "corpus_report": corpus_report,
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


def save_uploaded_files(files: list[UploadFile], upload_dir: Path) -> tuple[list[dict], list[str]]:
    upload_dir.mkdir(parents=True, exist_ok=True)
    saved_files = []
    note_parts = []
    for upload in files:
        if not upload.filename:
            continue
        safe_name = Path(upload.filename).name
        target_dir = upload_dir / "raw_emails" if safe_name.lower().endswith(".eml") else upload_dir
        target_dir.mkdir(parents=True, exist_ok=True)
        target = target_dir / safe_name
        hasher = hashlib.sha256()
        size = 0
        with target.open("wb") as f:
            while chunk := upload.file.read(1024 * 1024):
                size += len(chunk)
                hasher.update(chunk)
                f.write(chunk)
        saved_files.append(
            {
                "file_name": safe_name,
                "path": str(target.relative_to(ROOT)),
                "size": size,
                "sha256": hasher.hexdigest(),
            }
        )
        if safe_name.lower().endswith(".eml"):
            metadata = ingest_eml(target, upload_dir)
            if metadata.body_text:
                note_parts.append(f"邮件主题：{metadata.subject}\n邮件正文：{metadata.body_text}")
    return saved_files, note_parts


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
            "material_items": list_material_items(),
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


@app.post("/materials", response_class=HTMLResponse)
async def create_material_pool_item(
    title: str = Form(""),
    note: str = Form(""),
    files: list[UploadFile] = File(...),
) -> RedirectResponse:
    item_id = uuid.uuid4().hex[:12]
    material_dir = MATERIAL_ROOT / item_id
    saved_files, note_parts = save_uploaded_files(files, material_dir)
    full_note = "\n".join(part for part in [note.strip(), *note_parts] if part)
    create_material_item(item_id, "upload", title, full_note, str(material_dir), saved_files)
    return RedirectResponse(url="/#collection", status_code=303)


@app.post("/materials/{item_id}/package", response_class=HTMLResponse)
async def package_material_item(item_id: str) -> RedirectResponse:
    item = get_material_item(item_id)
    if item is None:
        return RedirectResponse(url="/#collection", status_code=303)
    package_title = item["title"] or f"资料归集报销包-{item_id}"
    package = build_package(Path(item["material_dir"]), item["note"], package_title)
    out_dir = OUTPUT_ROOT / package.id
    export_package(package, out_dir)
    reset_package_status_from_materials(asdict(package), "由资料归集未归类材料生成报销包")
    mark_material_item_packaged(item_id, package.id)
    return RedirectResponse(url=f"/packages/{package.id}/view", status_code=303)


@app.post("/packages", response_class=HTMLResponse)
async def create_package(
    title: str = Form(""),
    note: str = Form(""),
    files: list[UploadFile] = File(...),
) -> RedirectResponse:
    upload_id = uuid.uuid4().hex[:12]
    upload_dir = UPLOAD_ROOT / upload_id
    _, note_parts = save_uploaded_files(files, upload_dir)
    if note_parts:
        note = "\n".join(part for part in [note.strip(), *note_parts] if part)
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
async def update_package_status(
    package_id: str,
    status: str = Form(...),
    note: str = Form(""),
    confirm_items: list[str] = Form(default=[]),
) -> RedirectResponse:
    package = load_package(package_id)
    if package is not None:
        if status == "ready_for_school":
            missing = [item for item in package.get("checklist", []) if item.get("status") == "missing"]
            if missing or set(confirm_items) != RESPONSIBILITY_CONFIRMATIONS:
                return RedirectResponse(url=f"/packages/{package_id}/view", status_code=303)
            note = f"{note}；本人已逐项确认经费项目、收款账号、票据真实性和提交前人工复核".strip("；")
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
    set_package_status(package_id, "returned", "根据财务系统退回意见生成退回诊断")
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
