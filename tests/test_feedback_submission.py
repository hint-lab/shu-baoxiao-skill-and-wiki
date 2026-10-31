from __future__ import annotations

import copy
import contextlib
import importlib.util
import io
import json
import subprocess
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("feedback_submission", ROOT / "skills/shu-baoxiao/scripts/submit_feedback.py")
feedback = importlib.util.module_from_spec(spec)
spec.loader.exec_module(feedback)


def sample_payload():
    return {"schema_version": 1, "category": "rule", "college": "示例学院", "funding_type": "未说明",
            "item_or_matter": "材料清单差异", "checklist_id": "office",
            "actual_feedback": "模拟问题，仅用于本地测试。", "outcome": "未说明", "privacy_checked": True}


class AnonymousFormTests(unittest.TestCase):
    def test_primary_preview_maps_validated_fields_and_exposes_no_admin_credentials(self):
        payload = {**sample_payload(), "original_claim": "清单要求有差异", "used_version": "未知",
                   "suggested_correction": "请核对范围", "environment": "测试环境"}
        result = feedback.prepare_form_feedback(payload)
        self.assertFalse(result["submitted"])
        self.assertFalse(result["requires_account"])
        self.assertEqual(result["form_fields"]["使用版本"], "未知")
        self.assertIn("office", result["form_fields"]["原判断"])
        self.assertIn(payload["actual_feedback"], result["form_fields"]["实际差异"])
        self.assertIn(payload["suggested_correction"], result["form_fields"]["实际差异"])
        self.assertEqual(result["api"]["status"], "not_configured")
        self.assertIsNone(result["api"]["url"])
        self.assertNotIn("issue_body", result)
        self.assertNotIn("处理状态", result["form_fields"])
        self.assertNotIn("反馈ID", result["form_fields"])

    def test_primary_submit_does_not_silently_use_github_or_fake_http_submission(self):
        with tempfile.TemporaryDirectory() as folder:
            payload = Path(folder) / "case.json"
            payload.write_text(json.dumps(sample_payload()), encoding="utf-8")
            output = io.StringIO()
            with patch("sys.argv", ["submit_feedback.py", "--payload", str(payload), "--submit"]), \
                 patch.object(feedback.subprocess, "run", side_effect=AssertionError("must not invoke gh")), \
                 patch.object(feedback.shutil, "which", side_effect=AssertionError("no account required")), \
                 contextlib.redirect_stdout(output), self.assertRaises(SystemExit) as stopped:
                feedback.main()
            self.assertEqual(stopped.exception.code, 3)
            result = json.loads(output.getvalue())
            self.assertEqual(result["status"], "browser_required")
            self.assertFalse(result["submitted"])
            self.assertEqual(sorted(path.name for path in Path(folder).iterdir()), ["case.json"])

    def test_form_path_applies_the_same_privacy_gate(self):
        for change in ({"privacy_checked": False}, {"actual_feedback": "联系13800138000"},
                       {"attachment": "/private/case.pdf"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                feedback.prepare_form_feedback({**sample_payload(), **change})


class FakeGitHub:
    def __init__(self, mode=""):
        self.mode = mode
        self.create_count = 0
        self.issues = []

    def __call__(self, command, **kwargs):
        if command[1] == "api":
            endpoint = command[-1]
            if endpoint == "user":
                if self.mode == "auth":
                    return subprocess.CompletedProcess(command, 1, "", "HTTP 401")
                data = {"login": "test-feedback"}
            elif "?" in endpoint:
                data = [] if self.mode == "verify-unavailable" else self.issues
            else:
                if self.mode == "verify-unavailable":
                    return subprocess.CompletedProcess(command, 1, "", "HTTP 404")
                data = self.issues[0]
            return subprocess.CompletedProcess(command, 0, json.dumps(data), "")
        if command[1:3] == ["issue", "create"]:
            self.create_count += 1
            body = Path(command[command.index("--body-file") + 1]).read_text()
            if self.mode == "reject":
                return subprocess.CompletedProcess(command, 1, "", "HTTP 403")
            if self.mode != "timeout":
                self.issues = [{"number": 123, "html_url": feedback.ISSUES_URL + "/123",
                                "body": body, "user": {"login": "test-feedback"}}]
            if self.mode in {"timeout", "timeout-created"}:
                raise subprocess.TimeoutExpired(command, 30)
            return subprocess.CompletedProcess(command, 0, feedback.ISSUES_URL + "/123\n", "")
        raise AssertionError("Unexpected command")


class FeedbackSubmissionTests(unittest.TestCase):
    def call(self, payload, folder, github, **kwargs):
        return feedback.submit_github_feedback(payload, Path(folder) / "feedback.json", submit=True,
                                        receipt_path=Path(folder) / "receipt.json",
                                        runner=github, which=lambda _: "gh-mock", **kwargs)

    def test_preview_does_not_probe_network_or_write_receipts(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("Preview must remain offline")
        with tempfile.TemporaryDirectory() as folder:
            result = feedback.submit_github_feedback(sample_payload(), Path(folder) / "feedback.json",
                                              runner=forbidden, which=forbidden)
            self.assertEqual(result["status"], "prepared")
            self.assertFalse(result["submitted"])
            self.assertIn("使用者报告的Skill/资料包版本：未说明", result["issue_body"])
            self.assertIn("反馈整理工具版本：", result["issue_body"])
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_success_returns_verified_url_and_repeated_call_reuses_receipt(self):
        github = FakeGitHub()
        with tempfile.TemporaryDirectory() as folder:
            first = self.call(sample_payload(), folder, github)
            second = self.call(sample_payload(), folder, github)
            self.assertEqual(first["status"], "submitted")
            self.assertTrue(first["submitted"])
            self.assertEqual(second["status"], "already_submitted")
            self.assertEqual(first["issue_url"], second["issue_url"])
            self.assertEqual(github.create_count, 1)
            receipt = json.loads((Path(folder) / "receipt.json").read_text())
            self.assertEqual(receipt["issue_number"], 123)
            self.assertNotIn("issue_body", receipt)
            self.assertNotIn("actual_feedback", receipt)

    def test_missing_cli_or_auth_does_not_attempt_create(self):
        with tempfile.TemporaryDirectory() as folder:
            missing = feedback.submit_github_feedback(sample_payload(), Path(folder) / "feedback.json",
                                               submit=True, which=lambda _: None)
            self.assertFalse(missing["submitted"])
            github = FakeGitHub("auth")
            unauthenticated = self.call(sample_payload(), folder, github)
            self.assertEqual(unauthenticated["status"], "unavailable")
            self.assertEqual(github.create_count, 0)

    def test_shared_skill_directory_is_not_used_for_real_feedback_or_receipts(self):
        def forbidden(*args, **kwargs):
            raise AssertionError("Must reject shared paths before probing GitHub")
        with self.assertRaises(ValueError):
            feedback.submit_github_feedback(sample_payload(), feedback.SKILL_ROOT / "assets/case.json", submit=True, which=forbidden)
        with tempfile.TemporaryDirectory() as folder:
            with self.assertRaises(ValueError):
                feedback.submit_github_feedback(sample_payload(), Path(folder) / "feedback.json", submit=True,
                                         receipt_path=feedback.SKILL_ROOT / "assets/receipt.json", which=forbidden)

    def test_timeout_does_not_blindly_create_again(self):
        github = FakeGitHub("timeout")
        with tempfile.TemporaryDirectory() as folder:
            first = self.call(sample_payload(), folder, github)
            second = self.call(sample_payload(), folder, github)
            self.assertEqual(first["status"], "submission_unknown")
            self.assertIsNone(first["submitted"])
            self.assertEqual(second["status"], "submission_unknown")
            self.assertFalse(second["retry_create"])
            self.assertEqual(github.create_count, 1)

    def test_timeout_can_recover_a_confirmed_server_side_issue(self):
        github = FakeGitHub("timeout-created")
        with tempfile.TemporaryDirectory() as folder:
            result = self.call(sample_payload(), folder, github)
            self.assertTrue(result["submitted"])
            self.assertEqual(result["issue_url"], feedback.ISSUES_URL + "/123")
            self.assertEqual(github.create_count, 1)

    def test_failed_verification_is_not_misreported_as_rejected_creation(self):
        github = FakeGitHub("verify-unavailable")
        with tempfile.TemporaryDirectory() as folder:
            result = self.call(sample_payload(), folder, github)
            self.assertEqual(result["status"], "submission_unknown")
            self.assertIsNone(result["submitted"])
            github.mode = ""
            recovered = self.call(sample_payload(), folder, github)
            self.assertTrue(recovered["submitted"])
            self.assertEqual(github.create_count, 1)

    def test_explicit_rejection_can_be_retried_after_access_is_fixed(self):
        github = FakeGitHub("reject")
        with tempfile.TemporaryDirectory() as folder:
            rejected = self.call(sample_payload(), folder, github)
            self.assertEqual(rejected["status"], "not_submitted")
            self.assertFalse(rejected["submitted"])
            github.mode = ""
            accepted = self.call(sample_payload(), folder, github)
            self.assertTrue(accepted["submitted"])

    def test_private_identifiers_paths_links_and_attachments_are_rejected(self):
        for patch in ({"actual_feedback": "联系someone@example.com"},
                      {"actual_feedback": "联系13800138000"},
                      {"actual_feedback": "凭据：" + "ghp_" + "a" * 24},
                      {"actual_feedback": "/Users/example/private-file.pdf"},
                      {"attachments": ["invoice.pdf"]},
                      {"public_sources": ["https://cwc.shu.edu.cn/x?token=example"]},
                      {"privacy_checked": False}):
            with self.subTest(patch=patch):
                payload = copy.deepcopy(sample_payload())
                payload.update(patch)
                with self.assertRaises(ValueError):
                    feedback.prepare_feedback(payload)


if __name__ == "__main__":
    unittest.main()
