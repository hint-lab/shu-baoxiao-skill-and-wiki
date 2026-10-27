#!/usr/bin/env python3
"""Submit one PDF to an existing authenticated MinerU gateway through SSH.

The gateway credential stays inside its container. This maintenance tool does
not change server configuration, cancel other jobs, or use a cloud parser.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import shlex
import subprocess
import time
from pathlib import Path


REMOTE = r'''import base64,json,re,sys,urllib.error,urllib.request
req=json.load(sys.stdin)
key=open('/run/secrets/api-key',encoding='utf-8').read().strip()
if not key: raise SystemExit('empty gateway credential')
operation=req['operation']
if operation=='health': path='/v1/health'; method='GET'; payload=None
elif operation=='submit': path='/v1/parse/jobs'; method='POST'; payload=req['payload']
elif operation in ('job','content'):
 ident=req['id']
 if not re.fullmatch(r'[A-Za-z0-9_-]+',ident): raise SystemExit('invalid identifier')
 path=('/v1/parse/jobs/'+ident) if operation=='job' else ('/v1/files/'+ident+'/content')
 method='GET';payload=None
else: raise SystemExit('invalid operation')
data=json.dumps(payload).encode() if payload is not None else None
request=urllib.request.Request('http://127.0.0.1:8080'+path,data=data,method=method,
 headers={'Authorization':'Bearer '+key,'Content-Type':'application/json','Accept':'application/json'})
try:
 with urllib.request.urlopen(request,timeout=32) as response:
  raw=response.read(); ctype=response.headers.get('Content-Type','')
  print(json.dumps({'status':response.status,'content_type':ctype,'body':base64.b64encode(raw).decode()}))
except urllib.error.HTTPError as error:
 raw=error.read(4096)
 print(json.dumps({'status':error.code,'content_type':error.headers.get('Content-Type',''),'body':base64.b64encode(raw).decode()}))
'''


def call(host: str, container: str, operation: str, *, ident: str = "", payload: dict | None = None) -> tuple[int, bytes]:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.@-]*", host):
        raise ValueError("SSH 主机名不合法。")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", container):
        raise ValueError("容器名称不合法。")
    remote = shlex.join(["docker", "exec", "-i", container, "python3", "-c", REMOTE])
    request = {"operation": operation, "id": ident, "payload": payload}
    try:
        proc = subprocess.run(["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=8", host, remote],
                              input=json.dumps(request), capture_output=True, text=True, timeout=45)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError("P330 请求超时；如果是提交操作，任务可能已被接收，请先核对已有任务，不要盲目重试。") from exc
    if proc.returncode:
        raise RuntimeError("SSH/MinerU 调用失败：" + proc.stderr.strip()[:250])
    result = json.loads(proc.stdout)
    return result["status"], base64.b64decode(result["body"])


def parse_pdf(path: Path, output: Path, host: str, container: str, tier: str, pages: str, timeout: int) -> dict:
    raw = path.read_bytes()
    if not raw.startswith(b"%PDF-"):
        raise ValueError("输入不是 PDF。")
    if len(raw) > 20 * 1024 * 1024:
        raise ValueError("网关上限是 20 MiB；请按页拆分后分别处理，保留原始页码。")
    output.mkdir(parents=True, exist_ok=True)
    pending = output / "submission-uncertain.json"
    request_file = output / "request.json"
    source_sha = hashlib.sha256(raw).hexdigest()
    if request_file.exists():
        request = json.loads(request_file.read_text())
        if (request.get("source_sha256"), request.get("pages"), request.get("tier")) != (source_sha, pages, tier):
            raise ValueError("输出目录属于另一项任务；请指定新的目录。")
        job_id = request["job_id"]
        print("继续检查已有 MinerU 任务：", job_id, flush=True)
    else:
        if pending.exists():
            raise RuntimeError("上次提交结果未知；请先核对 P330 任务状态，不要重复提交。")
        pending.write_text(json.dumps({"source_sha256": source_sha, "pages": pages, "tier": tier}, indent=2) + "\n")
        payload = {"files": [{"source": {"type": "inline", "name": "school-document.pdf",
                                      "data": base64.b64encode(raw).decode("ascii")}, "page_range": pages}],
                   "tier": tier, "ocr_mode": "auto", "output_formats": ["markdown", "structured_content"]}
        status, body = call(host, container, "submit", payload=payload)
        if status != 202:
            raise RuntimeError(f"MinerU 未确认接受任务（HTTP {status}）：{body.decode('utf-8','replace')[:300]}")
        job = json.loads(body)
        job_id = job["job_id"]
        request_file.write_text(json.dumps({"job_id": job_id, "source_sha256": source_sha,
                                           "pages": pages, "tier": tier}, indent=2) + "\n")
        pending.unlink()
        print("MinerU 任务已提交：", job_id, "；页码：", pages, flush=True)
    checkpoint = output / "job.json"
    deadline = time.monotonic() + timeout
    last_status = ""
    while time.monotonic() < deadline:
        status, body = call(host, container, "job", ident=job_id)
        if status != 200:
            raise RuntimeError(f"无法读取任务状态（HTTP {status}）。")
        job = json.loads(body)
        current = job.get("status", "")
        if current != last_status:
            print("MinerU 状态：", current, flush=True)
            last_status = current
        if current in {"completed", "partial", "failed", "canceled"}:
            break
        time.sleep(4)
    else:
        raise TimeoutError("任务仍在 P330 运行；已保存任务 ID，不会重复提交或取消。")
    checkpoint.write_text(json.dumps(job, ensure_ascii=False, indent=2) + "\n")
    if job.get("status") != "completed":
        raise RuntimeError("MinerU 任务未完整完成：" + str(job.get("status")))
    files = job.get("files") or []
    if len(files) != 1 or files[0].get("status") != "completed":
        raise RuntimeError("MinerU 返回文件状态不完整。")
    artifacts = files[0].get("output_files") or {}
    for name, target in [("markdown", "result.md"), ("structured_content", "structured.json")]:
        descriptor = artifacts.get(name)
        if not descriptor:
            raise RuntimeError("MinerU 缺少输出：" + name)
        code, data = call(host, container, "content", ident=descriptor["file_id"])
        if code != 200 or len(data) != descriptor["bytes"]:
            raise RuntimeError("MinerU 输出下载不完整：" + name)
        (output / target).write_bytes(data)
    return {"job_id": job_id, "status": job["status"], "source_sha256": source_sha,
            "pages": pages, "tier": tier, "markdown_bytes": (output / "result.md").stat().st_size,
            "structured_bytes": (output / "structured.json").stat().st_size}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ssh-host", required=True)
    parser.add_argument("--gateway-container", default="hintlab-mineru-public-gateway-1")
    parser.add_argument("--tier", choices=["flash", "basic", "standard"], default="basic")
    parser.add_argument("--pages", default="all")
    parser.add_argument("--timeout", type=int, default=900)
    args = parser.parse_args()
    try:
        result = parse_pdf(args.pdf, args.output, args.ssh_host, args.gateway_container, args.tier, args.pages, args.timeout)
        print(json.dumps(result, ensure_ascii=False))
    except (OSError, ValueError, KeyError, RuntimeError, TimeoutError, subprocess.TimeoutExpired) as exc:
        parser.exit(1, f"P330 MinerU 解析未完成：{exc}\n")


if __name__ == "__main__":
    main()
