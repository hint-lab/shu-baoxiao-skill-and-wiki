from __future__ import annotations

import asyncio
import hashlib
import subprocess
import sys
import uuid
import re
from dataclasses import asdict
import os
import json
import shutil
from pathlib import Path
from collections import Counter

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.responses import StreamingResponse
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
    init_db,
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
from tools.knowledge_seed import (
    PROCESSED_CHUNKS_PATH,
    PROCESSED_DOCS_PATH,
    PROCESSED_MANIFEST_PATH,
    initialize_knowledge_base,
    knowledge_db_status,
)
from tools.llm_settings import save_config as save_rag_llm_config
from tools.llm_settings import status as rag_llm_status
from tools.mail_settings import save_config as save_imap_config
from tools.mail_settings import status as imap_settings_status
from tools.rag_llm import analyze_home_intent
from tools.poll_imap import STATE_PATH as MAIL_STATE_PATH
from tools.poll_imap import load_state as load_mail_state
from tools.poll_imap import poll_imap
from tools.poll_imap import save_state as save_mail_state
from tools.shu_auth_session import check_business_session
from tools.shu_auth_session import saved_status as shu_auth_saved_status
from tools.supplement_package import rebuild_with_supplements


ROOT = Path("/Users/hao/Documents/自助报销Agent")
UPLOAD_ROOT = ROOT / "data/uploads"
MATERIAL_ROOT = ROOT / "data/material_items"
WEB_STATIC = ROOT / "web/static"
WEB_TEMPLATES = ROOT / "web/templates"
VITE_MANIFEST = WEB_STATIC / "dist/.vite/manifest.json"
PLAYWRIGHT_ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
SHU_AUTH_LOGIN_LOG = ROOT / "data/auth_sessions/shu_auth_login.log"
SHU_AUTH_LOGIN_PROCESS: subprocess.Popen | None = None
USER_PROFILE_PATH = ROOT / "data/settings/user_profile.json"

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


@app.on_event("startup")
async def startup() -> None:
    init_db()
    try:
        initialize_knowledge_base()
    except Exception as exc:
        print(f"Knowledge seed import skipped: {type(exc).__name__}: {exc}")


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


def static_version(path: str) -> str:
    target = WEB_STATIC / path.lstrip("/")
    if not target.exists():
        return "0"
    return str(int(target.stat().st_mtime))


templates.env.globals["static_version"] = static_version


def shu_auth_login_pids() -> list[int]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "pid=,command="],
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except Exception:
        return []
    pids: list[int] = []
    for line in result.stdout.splitlines():
        parts = line.strip().split()
        if len(parts) < 4:
            continue
        try:
            pid = int(parts[0])
        except ValueError:
            continue
        command_parts = parts[1:]
        if not command_parts or "python" not in Path(command_parts[0]).name:
            continue
        if "tools/shu_auth_session.py" not in command_parts or "login" not in command_parts:
            continue
        if pid != os.getpid():
            pids.append(pid)
    return pids


def shu_auth_login_running() -> bool:
    global SHU_AUTH_LOGIN_PROCESS
    if SHU_AUTH_LOGIN_PROCESS is None:
        return bool(shu_auth_login_pids())
    if SHU_AUTH_LOGIN_PROCESS.poll() is None:
        return True
    SHU_AUTH_LOGIN_PROCESS = None
    return bool(shu_auth_login_pids())


def read_user_profile_config() -> dict[str, str]:
    if not USER_PROFILE_PATH.exists():
        return {}
    try:
        payload = json.loads(USER_PROFILE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(payload, dict):
        return {}
    return {str(key): str(value) for key, value in payload.items()}


def save_user_profile_config(work_id: str = "") -> dict[str, str]:
    payload = read_user_profile_config()
    clean_work_id = "".join(ch for ch in work_id.strip() if ch.isalnum() or ch in {"-", "_"})
    if clean_work_id:
        payload["work_id"] = clean_work_id
    else:
        payload.pop("work_id", None)
    USER_PROFILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    USER_PROFILE_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def app_user_profile() -> dict[str, str]:
    auth = shu_auth_saved_status()
    auth_status = auth.get("status", "not_checked")
    profile = read_user_profile_config()
    work_id = next(
        (
            value.strip()
            for value in [
                os.getenv("SHU_REIMBURSEMENT_WORK_ID", ""),
                os.getenv("SHU_REIMBURSEMENT_STAFF_ID", ""),
                os.getenv("SHU_REIMBURSEMENT_USER_ID", ""),
                str(profile.get("work_id", "") or ""),
                str(auth.get("work_id", "") or ""),
                str(auth.get("staff_id", "") or ""),
                str(auth.get("employee_id", "") or ""),
                str(auth.get("student_id", "") or ""),
                str(auth.get("account_id", "") or ""),
            ]
            if value and value.strip()
        ),
        "",
    )
    display_name = f"工号 {work_id}" if work_id else "未绑定工号"
    subtitles = {
        "ready": "财务系统会话可用",
        "needs_scan": "需要本人扫码",
        "needs_renew": "需要续登",
        "error": "登录态检查失败",
        "not_checked": "本机模式",
    }
    return {
        "display_name": display_name,
        "work_id": work_id,
        "subtitle": subtitles.get(auth_status, "本机模式"),
        "auth_status": auth_status,
    }


def imap_env_status() -> dict[str, object]:
    settings = imap_settings_status()
    state = load_mail_state(MAIL_STATE_PATH)
    return {
        **settings,
        "host_configured": bool(settings.get("host")),
        "username_configured": bool(settings.get("username")),
        "password_configured": bool(settings.get("has_password")),
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
    shu_auth = shu_auth_saved_status()
    shu_auth["login_running"] = shu_auth_login_running()
    shu_auth["login_pids"] = shu_auth_login_pids()
    payload = {
        "doubao": {
            "enabled": doubao_enabled(),
            "has_api_key": bool(doubao_api_key()),
            "has_model": bool(doubao_model_name()),
            "model": doubao_model_name(),
            "base_url": doubao_base_url(),
        },
        "rag_llm": rag_llm_status(),
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
        "shu_auth": shu_auth,
        "user": app_user_profile(),
    }
    return JSONResponse(payload)


@app.post("/api/shu-auth/login")
async def start_shu_auth_login(dry_run: bool = False) -> JSONResponse:
    global SHU_AUTH_LOGIN_PROCESS
    running = shu_auth_login_running()
    if dry_run:
        return JSONResponse({"ok": True, "started": False, "running": running, "dry_run": True})
    if running:
        return JSONResponse({"ok": True, "started": False, "running": True, "message": "扫码登录窗口已在运行。"})

    SHU_AUTH_LOGIN_LOG.parent.mkdir(parents=True, exist_ok=True)
    log_file = SHU_AUTH_LOGIN_LOG.open("a", encoding="utf-8")
    try:
        SHU_AUTH_LOGIN_PROCESS = subprocess.Popen(
            [sys.executable, "tools/shu_auth_session.py", "login", "--keep-open"],
            cwd=str(ROOT),
            stdout=log_file,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
    except Exception as exc:
        log_file.close()
        return JSONResponse(
            {"ok": False, "error": f"启动扫码登录窗口失败：{exc.__class__.__name__}"},
            status_code=500,
        )
    finally:
        try:
            log_file.close()
        except Exception:
            pass

    return JSONResponse(
        {
            "ok": True,
            "started": True,
            "running": True,
            "pid": SHU_AUTH_LOGIN_PROCESS.pid,
            "message": "已打开上海大学扫码登录窗口。",
        }
    )


@app.post("/api/shu-auth/check")
async def check_shu_auth_session() -> JSONResponse:
    if shu_auth_login_running():
        auth = shu_auth_saved_status()
        auth["login_running"] = True
        auth["login_pids"] = shu_auth_login_pids()
        auth["message"] = "登录窗口已打开，请先在窗口内完成登录或关闭窗口后再实时检查。"
        return JSONResponse({"ok": True, "checked": False, "shu_auth": auth})
    try:
        status = asdict(await asyncio.to_thread(check_business_session, headed=False, timeout_ms=20000))
    except Exception as exc:
        return JSONResponse(
            {"ok": False, "error": f"实时检查财务系统会话失败：{exc.__class__.__name__}: {exc}"},
            status_code=500,
        )
    status["login_running"] = False
    status["login_pids"] = []
    return JSONResponse({"ok": True, "checked": True, "shu_auth": status})


@app.post("/api/settings/rag-llm")
async def save_rag_llm_settings(
    provider: str = Form("deepseek"),
    base_url: str = Form(""),
    model: str = Form(""),
    api_key: str = Form(""),
    enabled: bool = Form(False),
    clear_key: bool = Form(False),
) -> JSONResponse:
    payload = save_rag_llm_config(
        provider=provider,
        base_url=base_url,
        model=model,
        api_key=api_key,
        enabled=enabled,
        clear_key=clear_key,
    )
    return JSONResponse({"ok": True, "rag_llm": payload})


@app.post("/api/settings/user-profile")
async def save_user_profile_settings(work_id: str = Form("")) -> JSONResponse:
    save_user_profile_config(work_id=work_id)
    return JSONResponse({"ok": True, "user": app_user_profile()})


@app.post("/api/settings/imap")
async def save_imap_settings(
    host: str = Form(""),
    port: str = Form("993"),
    username: str = Form(""),
    password: str = Form(""),
    mailbox: str = Form("INBOX"),
    enabled: bool = Form(False),
    mark_seen: bool = Form(False),
    clear_password: bool = Form(False),
) -> JSONResponse:
    payload = save_imap_config(
        host=host,
        port=port,
        username=username,
        password=password,
        mailbox=mailbox,
        enabled=enabled,
        mark_seen=mark_seen,
        clear_password=clear_password,
    )
    return JSONResponse({"ok": True, "imap": {**payload, "processed_count": imap_env_status().get("processed_count", 0)}})


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
                "processed_seed": {
                    "documents_exists": PROCESSED_DOCS_PATH.exists(),
                    "chunks_exists": PROCESSED_CHUNKS_PATH.exists(),
                    "manifest_exists": PROCESSED_MANIFEST_PATH.exists(),
                },
                "knowledge_db": knowledge_db_status(),
                "manifest": {},
            }
        )
    index = json.loads(index_path.read_text(encoding="utf-8"))
    source_types = Counter(chunk.get("source_type") or "page" for chunk in index.get("chunks", []))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8")) if manifest_path.exists() else {}
    corpus_report = index.get("corpus_report") or {}
    processed_manifest = json.loads(PROCESSED_MANIFEST_PATH.read_text(encoding="utf-8")) if PROCESSED_MANIFEST_PATH.exists() else {}
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
            "processed_seed": {
                "documents_exists": PROCESSED_DOCS_PATH.exists(),
                "chunks_exists": PROCESSED_CHUNKS_PATH.exists(),
                "manifest_exists": PROCESSED_MANIFEST_PATH.exists(),
                "document_count": processed_manifest.get("document_count", 0),
                "chunk_count": processed_manifest.get("chunk_count", 0),
                "ingestion_status_counts": processed_manifest.get("ingestion_status_counts", {}),
            },
            "knowledge_db": knowledge_db_status(),
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


def missing_required_items(package: dict) -> list[dict]:
    return [item for item in package.get("checklist", []) if item.get("required") and item.get("status") == "missing"]


def package_amount_total(package: dict) -> float:
    docs = package.get("documents", [])
    preferred = [doc for doc in docs if doc.get("document_type") == "invoice"] or [doc for doc in docs if doc.get("document_type") == "payment_record"]
    total = 0.0
    for doc in preferred:
        fields = doc.get("extracted_fields") if isinstance(doc.get("extracted_fields"), dict) else {}
        amount = fields.get("amount_total") or fields.get("max_amount")
        if isinstance(amount, (int, float)):
            total += float(amount)
    return total


def latest_reimbursement_package_from_context(context_text: str) -> dict | None:
    for path in package_dirs():
        package = load_package(path.name)
        if not package or is_validation_package(package):
            continue
        package_id = package.get("id") or ""
        title = package.get("title") or ""
        if package_id and package_id in context_text:
            return package
        if title and title in context_text:
            return package
    if not re.search(r"餐饮|餐费|接待|招待|工作用餐", context_text):
        return None
    for path in package_dirs():
        package = load_package(path.name)
        if not package or is_validation_package(package):
            continue
        if package.get("reimbursement_type") == "official_reception":
            return package
    return None


def looks_like_project_confirmation(note: str, context_text: str) -> bool:
    combined = f"{context_text}\n{note}"
    if not re.search(r"餐饮|餐费|接待|招待|报销包", combined):
        return False
    return bool(re.search(r"项目|余额|经费|横向|维持性|工作用餐|够|不足|要报销|确认报销", note))


def chat_guidance_for_package(package: dict) -> tuple[str, list[dict[str, str]]]:
    package_type = package.get("reimbursement_type")
    missing = missing_required_items(package)
    missing_names = [item.get("name") for item in missing]
    amount = package_amount_total(package)
    title = package.get("title") or package.get("id") or "这笔报销"
    if package_type == "official_reception":
        lines = [
            f"我识别这笔是餐饮接待/工作用餐类报销，金额 {amount:,.2f} 元。" if amount else "我识别这笔是餐饮接待/工作用餐类报销。",
            "",
            f"我已经先建好工作单：{title}。",
            "接下来你不用打开财务系统，我会在聊天里把材料和项目确认清楚；材料齐后我再打开统一登录和财务系统代填。",
            "",
            "请确认三件事：",
            "1. 这笔餐饮费是否现在要报销？",
            "2. 走哪个经费项目？请发项目名称或项目号。",
            "3. 余额是否足够？如果你知道余额，直接说“余额够/余额不足”。",
            "",
            "经费类型也要确认：如果是横向科研经费且单笔 1000 元以下，通常先补正式发票即可继续；如果是维持性经费工作用餐，还需要公务接待清单或工作用餐审批表，以及邀请函或派出公函。",
        ]
        if missing_names:
            lines.extend(["", "当前系统已知还差：", *[f"- {name}" for name in missing_names]])
        actions = [
            {
                "type": "ask",
                "label": "走横向项目",
                "query": f"确认报销这笔餐饮费，走横向科研经费，项目：，余额足够。",
            },
            {
                "type": "ask",
                "label": "走维持性经费",
                "query": f"确认报销这笔餐饮费，走维持性经费工作用餐，项目：，余额足够。",
            },
            {
                "type": "href",
                "label": "继续补发票",
                "href": f"/packages/{package.get('id')}/view",
            },
        ]
        return "\n".join(lines), actions

    message = f"我已按报销材料生成工作单，材料 {len(package.get('documents', []))} 份，待补 {len(missing)} 项。"
    return message, [{"type": "href", "label": "查看工作单", "href": f"/packages/{package.get('id')}/view"}]


def handle_project_confirmation_from_chat(note: str, context_text: str) -> dict[str, object] | None:
    if not looks_like_project_confirmation(note, context_text):
        return None
    package = latest_reimbursement_package_from_context(context_text)
    if not package:
        return None
    input_dir = Path(package.get("input_dir") or "")
    if not input_dir.exists():
        return None
    combined_note = "\n\n".join(
        part
        for part in [
            str(package.get("user_note") or "").strip(),
            f"用户在聊天中确认：{note.strip()}",
        ]
        if part
    )
    rebuilt = build_package(input_dir, combined_note, package.get("title") or None)
    out_dir = OUTPUT_ROOT / rebuilt.id
    export_package(rebuilt, out_dir)
    package_payload = asdict(rebuilt)
    status = reset_package_status_from_materials(package_payload, "由聊天确认经费项目和余额后重新检查")
    missing = missing_required_items(package_payload)
    actions = [
        {
            "type": "href",
            "label": "上传剩余材料",
            "href": f"/packages/{rebuilt.id}/view",
        }
    ]
    if missing:
        missing_names = [item.get("name") for item in missing]
        message = (
            "我已记录你的项目/余额确认，并重新检查这笔餐饮报销。\n\n"
            + "现在还不能进财务系统提交，因为材料还没齐。\n\n"
            + "当前还差：\n"
            + "\n".join(f"- {name}" for name in missing_names)
            + "\n\n补齐后我会继续在聊天里处理；你不需要自己打开财务系统。"
        )
    else:
        message = (
            "我已记录你的项目/余额确认，并重新检查这笔餐饮报销。\n\n"
            "材料已经通过本地完整性检查。下一步我会打开统一登录，登录完成后进入学校财务系统代填；提交前仍会停下让你最终确认。"
        )
    return {
        "ok": True,
        "action": "project_confirmation",
        "message": message,
        "actions": actions,
        "package": {
            "id": rebuilt.id,
            "title": rebuilt.title,
            "url": f"/packages/{rebuilt.id}/view",
            "document_count": len(package_payload.get("documents", [])),
            "missing_count": len(missing),
            "status": status.get("status"),
        },
    }


def handle_chat_supplement_upload(note: str, uploads: list[UploadFile], context_text: str) -> dict[str, object] | None:
    package = latest_reimbursement_package_from_context(context_text)
    if not package:
        return None
    package_id = package.get("id")
    package_dir = OUTPUT_ROOT / str(package_id)
    if not package_id or not package_dir.exists():
        return None
    upload_id = uuid.uuid4().hex[:12]
    upload_dir = UPLOAD_ROOT / "chat_supplements" / upload_id
    saved_files, note_parts = save_uploaded_files(uploads, upload_dir)
    supplement_paths = [ROOT / item["path"] for item in saved_files]
    supplement_note = "\n".join(part for part in [note.strip(), *note_parts] if part)
    rebuild_with_supplements(package_dir, supplement_paths, supplement_note)
    updated = load_package(str(package_id))
    if not updated:
        return None
    status = reset_package_status_from_materials(updated, "由聊天补传材料后重新检查")
    missing = missing_required_items(updated)
    if missing:
        message = (
            f"我已把新材料合并到「{updated.get('title') or package_id}」，并重新检查。\n\n"
            "当前还差：\n"
            + "\n".join(f"- {item.get('name')}" for item in missing)
            + "\n\n补齐后我会继续代你推进，不需要你自己打开财务系统。"
        )
    else:
        message = (
            f"我已把新材料合并到「{updated.get('title') or package_id}」，并重新检查。\n\n"
            "材料已经通过本地完整性检查。下一步在聊天里确认经费项目和余额后，我会打开统一登录并进入学校财务系统代填。"
        )
    return {
        "ok": True,
        "action": "supplement_package",
        "message": message,
        "actions": [
            {
                "type": "ask",
                "label": "确认项目余额",
                "query": "确认报销这笔餐饮费，项目：，余额足够。",
            },
            {
                "type": "href",
                "label": "查看工作单",
                "href": f"/packages/{package_id}/view",
            },
        ],
        "package": {
            "id": package_id,
            "title": updated.get("title") or package_id,
            "url": f"/packages/{package_id}/view",
            "document_count": len(updated.get("documents", [])),
            "missing_count": len(missing),
            "status": status.get("status"),
        },
    }


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


@app.post("/api/home/assistant")
async def home_assistant(
    title: str = Form(""),
    note: str = Form(""),
    history: str = Form(""),
    files: list[UploadFile] | None = File(None),
) -> JSONResponse:
    payload, status_code = create_home_assistant_payload(title, note, files, history)
    return JSONResponse(payload, status_code=status_code)


def parse_chat_history(raw: str, limit: int = 8) -> list[dict[str, str]]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    items: list[dict[str, str]] = []
    for item in payload[-limit:]:
        if not isinstance(item, dict):
            continue
        role = str(item.get("role") or "").strip()
        text = str(item.get("text") or "").strip()
        if role not in {"user", "assistant"} or not text:
            continue
        items.append({"role": role, "text": text[:800]})
    return items


def conversation_context_text(history: list[dict[str, str]], max_chars: int = 2400) -> str:
    lines = []
    for item in history:
        label = "用户" if item["role"] == "user" else "报销 Agent"
        lines.append(f"{label}：{item['text']}")
    text = "\n".join(lines)
    if len(text) > max_chars:
        text = text[-max_chars:]
    return text


def note_with_context(note: str, context: str) -> str:
    if not context:
        return note
    if not note:
        return f"对话上下文：\n{context}"
    return f"对话上下文：\n{context}\n\n本轮输入：\n{note}"


def create_home_assistant_payload(
    title: str,
    note: str,
    files: list[UploadFile] | None,
    history: str = "",
) -> tuple[dict[str, object], int]:
    uploads = [upload for upload in (files or []) if upload.filename]
    clean_title = title.strip()
    clean_note = note.strip()
    if not clean_note and not uploads:
        return {"ok": False, "error": "请先输入问题、报销事项，或者上传发票和附件。"}, 400

    file_names = [Path(upload.filename or "").name for upload in uploads]
    chat_history = parse_chat_history(history)
    context_text = conversation_context_text(chat_history)
    note_for_reasoning = note_with_context(clean_note, context_text)
    if uploads and context_text:
        supplement_payload = handle_chat_supplement_upload(clean_note, uploads, context_text)
        if supplement_payload:
            return supplement_payload, 200
    if not uploads:
        project_confirmation = handle_project_confirmation_from_chat(clean_note, context_text)
        if project_confirmation:
            return project_confirmation, 200
    intent = analyze_home_intent(clean_note, clean_title, file_names, conversation_context=context_text)
    action = intent.get("action") or "ask_clarification"
    if uploads and action in {"create_inbox", "ask_clarification"}:
        action = "create_package"
    if action == "create_package" and not uploads:
        action = "create_inbox" if clean_note else "ask_clarification"

    if action == "answer_policy":
        query = intent.get("search_query") or note_for_reasoning
        policy = query_policy(query, top_k=5)
        return {
            "ok": True,
            "action": "answer_policy",
            "intent": intent,
            "used_context": bool(context_text),
            "message": intent.get("reply") or "我查了财务处资料库，下面是可追溯回答。",
            "policy": policy,
        }, 200

    if action == "create_package":
        upload_id = uuid.uuid4().hex[:12]
        upload_dir = UPLOAD_ROOT / upload_id
        _, note_parts = save_uploaded_files(uploads, upload_dir)
        package_note = "\n".join(part for part in [note_for_reasoning, *note_parts] if part)
        package = build_package(upload_dir, package_note, clean_title or intent.get("title") or None)
        out_dir = OUTPUT_ROOT / package.id
        export_package(package, out_dir)
        package_payload = asdict(package)
        reset_package_status_from_materials(package_payload)
        guided_message, guided_actions = chat_guidance_for_package(package_payload)
        return {
            "ok": True,
            "action": "create_package",
            "intent": intent,
            "used_context": bool(context_text),
            "message": guided_message or intent.get("reply") or "我已按报销材料生成报销包，下一步由你复核。",
            "actions": guided_actions,
            "package": {
                "id": package.id,
                "title": package.title,
                "url": f"/packages/{package.id}/view",
                "document_count": len(package_payload.get("documents", [])),
                "missing_count": len([item for item in package_payload.get("checklist", []) if item.get("status") == "missing"]),
            },
        }, 200

    if action == "create_inbox":
        item_id = uuid.uuid4().hex[:12]
        create_inbox_item(item_id, "chat", clean_title or intent.get("title") or "", note_for_reasoning)
        return {
            "ok": True,
            "action": "create_inbox",
            "intent": intent,
            "used_context": bool(context_text),
            "message": intent.get("reply") or "我已放进资料归集，后面补材料后再生成报销包。",
            "item": {"id": item_id, "url": "/#collection"},
        }, 200

    return {
        "ok": True,
        "action": "ask_clarification",
        "intent": intent,
        "message": intent.get("reply") or "你是想查政策依据、记录一个待报销事项，还是整理已有发票？",
    }, 200


def assistant_text_from_payload(payload: dict[str, object]) -> str:
    action = payload.get("action")
    if action == "answer_policy":
        policy = payload.get("policy") if isinstance(payload.get("policy"), dict) else {}
        answer = policy.get("answer") if isinstance(policy, dict) else ""
        return f"{payload.get('message') or '我先查了财务处资料库。'}\n\n{answer or '没有检索到足够可靠的依据。'}"
    if action in {"create_package", "project_confirmation"}:
        package = payload.get("package") if isinstance(payload.get("package"), dict) else {}
        message = str(payload.get("message") or "已生成报销工作单。")
        if "材料 " not in message and package:
            message += f"\n\n材料 {package.get('document_count') or 0} 份；待补 {package.get('missing_count') or 0} 项。"
        return message
    return str(payload.get("message") or "你是想查政策依据、记录一个待报销事项，还是整理已有发票？")


def sse_event(event: str, data: dict[str, object]) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def stream_text_chunks(text: str, size: int = 12) -> list[str]:
    chunks: list[str] = []
    buffer = ""
    for char in text:
        buffer += char
        if len(buffer) >= size or char in "\n。！？；":
            chunks.append(buffer)
            buffer = ""
    if buffer:
        chunks.append(buffer)
    return chunks


async def home_assistant_payload_with_heartbeat(
    title: str,
    note: str,
    files: list[UploadFile] | None,
    history: str,
):
    task = asyncio.create_task(asyncio.to_thread(create_home_assistant_payload, title, note, files, history))
    messages = [
        "正在分析报销意图",
        "正在检索财务处资料库",
        "正在整理材料和依据",
        "正在生成答复",
    ]
    index = 0
    while not task.done():
        await asyncio.sleep(1.0)
        if task.done():
            break
        yield sse_event("status", {"message": messages[index % len(messages)]})
        index += 1
    try:
        payload, status_code = await task
    except Exception as exc:
        yield sse_event("error", {"error": f"处理失败：{type(exc).__name__}"})
        return
    yield payload, status_code


@app.post("/api/home/assistant/stream")
async def home_assistant_stream(
    title: str = Form(""),
    note: str = Form(""),
    history: str = Form(""),
    files: list[UploadFile] | None = File(None),
) -> StreamingResponse:
    async def generate():
        yield sse_event("status", {"message": "正在判断报销意图"})
        payload = None
        status_code = 500
        async for item in home_assistant_payload_with_heartbeat(title, note, files, history):
            if isinstance(item, str):
                yield item
            else:
                payload, status_code = item
        if payload is None:
            yield sse_event("error", {"error": "处理失败"})
            return
        if status_code >= 400 or not payload.get("ok"):
            yield sse_event("error", {"error": payload.get("error") or "处理失败"})
            return
        yield sse_event("meta", {"action": payload.get("action") or ""})
        text = assistant_text_from_payload(payload)
        for chunk in stream_text_chunks(text):
            yield sse_event("delta", {"text": chunk})
            await asyncio.sleep(0.018)
        yield sse_event("done", {"payload": payload})

    return StreamingResponse(generate(), media_type="text/event-stream")


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
            "user": app_user_profile(),
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
            "user": app_user_profile(),
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
    missing_item_id: str = Form(""),
    missing_item_name: str = Form(""),
    files: list[UploadFile] = File(...),
) -> RedirectResponse:
    package_dir = OUTPUT_ROOT / package_id
    if not (package_dir / "package.json").exists():
        return RedirectResponse(url=f"/packages/{package_id}/view", status_code=303)
    upload_id = uuid.uuid4().hex[:12]
    upload_dir = UPLOAD_ROOT / "supplements" / upload_id
    upload_dir.mkdir(parents=True, exist_ok=True)
    if missing_item_name:
        note = "\n".join(part for part in [f"补充缺项：{missing_item_name}", note.strip()] if part)
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
