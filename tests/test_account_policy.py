"""Safety regression tests for account-wide dry-run bootstrap."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from validate_account_policy import PolicyError, validate
from plan_onboarding import infer_tech, plan


class AccountPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.policy = json.loads((ROOT / "config" / "account.defaults.json").read_text(encoding="utf-8"))
        cls.inv = json.loads((ROOT / "examples" / "inventory.example.json").read_text(encoding="utf-8"))

    def test_valid_safe_defaults(self):
        self.assertTrue(validate(self.policy))
        self.assertEqual(self.policy["ci"]["max_additional_paid_usd"], 0)

    def test_never_auto_execute_in_dry_run(self):
        p = copy.deepcopy(self.policy)
        p["ci"]["allow_workflow_execution"] = True
        with self.assertRaises(PolicyError): validate(p)

    def test_never_auto_mutate_in_dry_run(self):
        p = copy.deepcopy(self.policy)
        p["rollout"]["create_pr_automatically"] = True
        with self.assertRaises(PolicyError): validate(p)

    def test_prohibit_paid_runners(self):
        p = copy.deepcopy(self.policy)
        p["ci"]["allow_paid_runners"] = True
        with self.assertRaises(PolicyError): validate(p)

    def test_prohibit_release_without_review(self):
        p = copy.deepcopy(self.policy)
        p["ci"]["allow_automatic_release"] = True
        with self.assertRaises(PolicyError): validate(p)

    def test_prohibit_positive_paid_budget(self):
        p = copy.deepcopy(self.policy)
        p["ci"]["max_additional_paid_usd"] = 1
        with self.assertRaises(PolicyError): validate(p)

    def test_required_checks_mandatory(self):
        p = copy.deepcopy(self.policy)
        p["ci"]["preserve_required_checks"] = False
        with self.assertRaises(PolicyError): validate(p)

    def test_validation_rejects_unknown_keys(self):
        p = copy.deepcopy(self.policy)
        p["ci"]["unrecognized"] = True
        with self.assertRaises(PolicyError): validate(p)

    def test_no_repository_actions_in_plan(self):
        r = plan(self.policy, self.inv)
        self.assertEqual(len(r["repositories"]), 1)
        self.assertEqual(r["repositories"][0]["tests_scheduled"], 0)
        self.assertEqual(r["repositories"][0]["mutations_performed"], 0)
        self.assertEqual(r["repositories"][0]["detected_technology"], "node")

    def test_reject_foreign_owner(self):
        inv = copy.deepcopy(self.inv)
        inv["repositories"][0]["name"] = "outsider/example-repo"
        with self.assertRaises(PolicyError): plan(self.policy, inv)

    def test_reject_duplicate_repos(self):
        inv = copy.deepcopy(self.inv)
        inv["repositories"].append(inv["repositories"][0])
        with self.assertRaises(PolicyError): plan(self.policy, inv)

    def test_unknown_stack_requires_review(self):
        self.assertEqual(infer_tech(["README.md"]), "unknown-review-required")

    def test_uninspected_repo_does_not_look_empty(self):
        inv = copy.deepcopy(self.inv)
        inv["repositories"][0]["root_files"] = None
        r = plan(self.policy, inv)
        self.assertEqual(r["repositories"][0]["detected_technology"], "unknown-uninspected")
        self.assertFalse(r["repositories"][0]["root_files_inspected"])

    def test_private_repo_never_executed_by_plan(self):
        inv = copy.deepcopy(self.inv)
        inv["repositories"][0]["visibility"] = "private"
        r = plan(self.policy, inv)
        self.assertEqual(r["repositories"][0]["tests_scheduled"], 0)


if __name__ == "__main__":
    unittest.main()
