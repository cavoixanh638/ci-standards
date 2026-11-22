"""No cloud, GitHub, billing, private repository or test-runner side effects."""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
from activation_preflight import GATES, assess
from validate_account_policy import PolicyError


class ActivationPreflightTests(unittest.TestCase):
    def setUp(self):
        self.policy = json.loads((ROOT / 'config' / 'account.defaults.json').read_text())
        self.evidence = json.loads((ROOT / 'examples' / 'activation-evidence.example.json').read_text())

    def test_default_is_hold(self):
        result = assess(self.policy, self.evidence)
        self.assertEqual(result['readiness'], 'HOLD')
        self.assertEqual(result['unresolved_checks'], len(GATES))

    def test_no_side_effects_even_when_all_attested(self):
        self.evidence['checks'] = {name: True for name, _ in GATES}
        result = assess(self.policy, self.evidence)
        self.assertEqual(result['readiness'], 'READY_FOR_OWNER_REVIEW')
        self.assertEqual(result['automatic_enable_allowed'], False)
        self.assertEqual(result['repository_mutations_performed'], 0)
        self.assertEqual(result['github_actions_dispatched'], 0)
        self.assertEqual(result['cloud_deploy_performed'], False)
        self.assertIn('SELF_ATTESTED', result['evidence_origin'])

    def test_missing_gate_fails_closed(self):
        del self.evidence['checks']['emergency_stop_verified']
        with self.assertRaises(PolicyError): assess(self.policy, self.evidence)

    def test_extra_field_does_not_echo_secrets(self):
        self.evidence['checks']['github_token'] = 'SENSITIVE_VALUE'
        with self.assertRaises(PolicyError): assess(self.policy, self.evidence)

    def test_invalid_type_rejected(self):
        self.evidence['checks']['cloudflare_free_confirmed'] = 'yes'
        with self.assertRaises(PolicyError): assess(self.policy, self.evidence)

    def test_wrong_owner_rejected(self):
        self.evidence['owner'] = 'other'
        with self.assertRaises(PolicyError): assess(self.policy, self.evidence)

    def test_unsafe_policy_rejected(self):
        self.policy['ci']['allow_workflow_execution'] = True
        with self.assertRaises(PolicyError): assess(self.policy, self.evidence)

    def test_unknown_envelope_key_rejected(self):
        self.evidence['private_repo_names'] = ['secret']
        with self.assertRaises(PolicyError): assess(self.policy, self.evidence)

    def test_read_only_not_activation(self):
        self.evidence['checks'] = {name: True for name, _ in GATES}
        self.evidence['checks']['owner_approved_readonly'] = False
        result = assess(self.policy, self.evidence)
        self.assertEqual(result['readiness'], 'HOLD')
        self.assertEqual(result['unresolved_checks'], 1)

    def test_never_allows_auto_pr(self):
        self.policy['rollout']['create_pr_automatically'] = True
        with self.assertRaises(PolicyError): assess(self.policy, self.evidence)


if __name__ == '__main__':
    unittest.main()
