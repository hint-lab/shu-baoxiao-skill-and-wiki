from __future__ import annotations

import copy
import importlib.util
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("checklist_knowledge", ROOT / "skills/shu-baoxiao/scripts/knowledge.py")
knowledge = importlib.util.module_from_spec(spec)
spec.loader.exec_module(knowledge)


class ChecklistTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.bundle = knowledge.load_checklists()
        cls.docs = knowledge.load_documents()
        cls.review_day = date.fromisoformat(cls.bundle["updated_on"])

    def result(self, query, *, bundle=None, docs=None, today=None):
        return knowledge.checklist_result(query, bundle if bundle is not None else self.bundle,
                                          docs if docs is not None else self.docs,
                                          today or self.review_day)

    def test_reviewed_templates_resolve_to_available_source_snapshots(self):
        ids = [item["id"] for item in self.bundle["templates"]]
        self.assertEqual(len(ids), len(set(ids)))
        for key in ids:
            item = self.result(key)["checklist"]
            self.assertEqual(item["source_state"], "reviewed_snapshot", key)
            self.assertTrue(item["context_match_required"])
            self.assertTrue(item["materials"])
            self.assertTrue(item["references"])
            for reference in item["references"]:
                self.assertTrue(reference["locator"])
                self.assertTrue(reference["verified_summary"])

    def test_source_changes_withhold_cached_requirements(self):
        docs = copy.deepcopy(self.docs)
        next(doc for doc in docs if doc["id"] == "1e88716b10c71712")["text"] += "\n新增限制条件。"
        item = self.result("printer", docs=docs)["checklist"]
        self.assertTrue(item["refresh_before_use"])
        self.assertNotIn("materials", item)
        self.assertTrue(item["review_issues"])

    def test_missing_or_incomplete_sources_cannot_be_used_as_cached_rules(self):
        for docs in ([doc for doc in self.docs if doc["id"] != "1e88716b10c71712"], copy.deepcopy(self.docs)):
            for doc in docs:
                if doc["id"] == "1e88716b10c71712":
                    doc["availability"] = "entry_only"
            item = self.result("printer", docs=docs)["checklist"]
            self.assertEqual(item["source_state"], "needs_review")
            self.assertNotIn("materials", item)

    def test_review_deadline_is_inclusive_and_does_not_mark_all_rules_invalid(self):
        item = self.result("printer", today=date(2026, 11, 27))["checklist"]
        self.assertTrue(item["refresh_before_use"])
        self.assertNotIn("materials", item)
        self.assertTrue(item["references"])

    def test_new_policy_can_suspend_reuse_even_when_old_document_is_unchanged(self):
        bundle = copy.deepcopy(self.bundle)
        bundle["source_reviews"]["office-funding"]["status"] = "needs_review"
        item = self.result("printer", bundle=bundle)["checklist"]
        self.assertTrue(item["refresh_before_use"])
        self.assertNotIn("materials", item)

    def test_new_material_without_evidence_is_not_presented_as_a_requirement(self):
        bundle = copy.deepcopy(self.bundle)
        template = next(item for item in bundle["templates"] if item["id"] == "printer")
        template["materials"].append({"name": "无来源新增材料", "kind": "base", "when": "始终", "check": "待核实"})
        item = self.result("printer", bundle=bundle)["checklist"]
        self.assertTrue(item["refresh_before_use"])
        self.assertNotIn("materials", item)

    def test_ambiguous_publication_request_does_not_assume_currency(self):
        result = self.result("版面费")
        self.assertTrue(result["selection_required"])
        self.assertNotIn("checklist", result)
        self.assertEqual({item["id"] for item in result["checklists"]}, {"publication-domestic", "publication-foreign"})

    def test_unknown_business_does_not_fall_back_to_an_unrelated_checklist(self):
        with self.assertRaises(ValueError):
            self.result("uncovered-business")

    def test_college_practice_keeps_user_provenance_and_funding_boundary(self):
        entries = knowledge.reported_practices("计算机学院显卡材料费")
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertEqual(entry["source_type"], "user_statement")
        self.assertFalse(entry["official_document_verified"])
        self.assertEqual(entry["verification_status"], "user_reported_unverified")
        self.assertEqual(set(entry["funding_scope"]["allowed"]), {"横向科研经费", "纵向科研经费"})
        self.assertEqual(entry["funding_scope"]["excluded"], ["办公类经费"])
        self.assertTrue(entry["conflicts"])
        self.assertNotIn(entry["id"], {doc["id"] for doc in self.docs})

    def test_related_checklist_keeps_reported_practice_separate_from_written_evidence(self):
        item = self.result("office")["checklist"]
        entry = item["reported_practices"][0]
        self.assertNotIn(entry["id"], {reference["review_id"] for reference in item["references"]})
        self.assertTrue(item["reported_practices_notice"])
        self.assertFalse(entry["official_document_verified"])

    def test_component_report_does_not_establish_a_whole_nas_device_rule(self):
        self.assertEqual(knowledge.reported_practices("NAS"), [])
        item = self.result("storage")["checklist"]
        entry = item["reported_practices"][0]
        self.assertNotIn("NAS", entry["reported_items"])
        self.assertTrue(any("NAS整机" in note for note in entry["not_established_by_this_report"]))

    def test_data_collection_report_preserves_conditional_questionnaire_and_scope(self):
        entries = knowledge.reported_practices("问卷数据采集报销")
        self.assertEqual(len(entries), 1)
        entry = entries[0]
        self.assertFalse(entry["official_document_verified"])
        self.assertEqual(entry["source_type"], "user_statement")
        materials = {item["id"]: item for item in entry["materials"]}
        self.assertEqual(materials["questionnaire"]["kind"], "conditional")
        self.assertEqual(materials["labor-contract"]["submission_channel"], "薪酬系统")
        self.assertEqual(materials["collection-explanation"]["signature_role"], "负责人")
        self.assertEqual(entry["funding_scope"]["allowed"], [])
        self.assertEqual(entry["related_template_ids"], [])
        self.assertNotIn(entry["id"], {doc["id"] for doc in self.docs})
        self.assertEqual(knowledge.reported_practices("一般学生助研劳务"), [])


if __name__ == "__main__":
    unittest.main()
