import copy
import importlib.util
import json
from pathlib import Path
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('plan', Path(__file__).resolve().parents[1] / 'scripts/plan.py')
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)


class PlanTests(unittest.TestCase):
    def test_no_ci_result_is_not_success(self):
        self.assertFalse(plan.passed_ci([]))
        self.assertFalse(plan.passed_ci([{'name': 'build_test_deploy', 'status': 'in_progress', 'conclusion': None}]))
        self.assertFalse(plan.passed_ci([{'name': 'build_test_deploy', 'status': 'completed', 'conclusion': 'failure'}]))
        self.assertTrue(plan.passed_ci([{'name': 'build_test_deploy', 'status': 'completed', 'conclusion': 'success'}]))

    def test_hash_is_stable_and_changes_with_parent_or_base_digest(self):
        data = {'published_upstream': {'monolithic': 'sha256:' + 'a'*64, 'ubuntu': 'sha256:' + 'b'*64}, 'base': 'base-a', 'recipe': 'one'}
        original = plan.fingerprint(data)
        self.assertEqual(original, plan.fingerprint(dict(reversed(list(data.items())))))
        for key in ['base', 'recipe']:
            changed = copy.deepcopy(data)
            changed[key] += '-changed'
            self.assertNotEqual(original, plan.fingerprint(changed))
        changed = copy.deepcopy(data)
        changed['published_upstream']['ubuntu'] = 'sha256:' + 'c'*64
        self.assertNotEqual(original, plan.fingerprint(changed))

    def fake_github(self, path):
        if '/' not in path:
            return {'default_branch': 'master'}
        if '/commits?' in path:
            return [{'sha': 'a'*40}, {'sha': 'b'*40}]
        return {'check_runs': [{'name': 'build_test_deploy', 'status': 'completed', 'conclusion': 'failure' if 'a'*40 in path else 'success'}]}

    def fake_request(self, url, github=False):
        if 'raw.githubusercontent.com' in url:
            return b'FROM ubuntu:26.04\n'
        if '/library/ubuntu/' in url:
            return json.dumps({'images': [{'architecture': 'arm64', 'os': 'linux', 'digest': 'sha256:' + 'c'*64}]}).encode()
        return json.dumps({'digest': 'sha256:' + 'd'*64}).encode()

    def test_selects_green_source_and_tracks_published_hash_without_dates(self):
        with patch.object(plan, 'github', side_effect=self.fake_github), patch.object(plan, 'request', side_effect=self.fake_request):
            result = plan.resolve()
            self.assertEqual(result, plan.resolve())
        self.assertEqual(set(result), {'key', 'upstream_digest', 'plan'})
        self.assertEqual(result['plan']['sources']['monolithic'], 'b'*40)
        self.assertNotIn('date', result['plan'])
        self.assertTrue(result['plan']['base'].endswith('c'*64))

    def test_refuses_missing_published_digest(self):
        with patch.object(plan, 'github', side_effect=self.fake_github), patch.object(plan, 'request', return_value=b'{"digest": null}'):
            with self.assertRaisesRegex(ValueError, 'missing published'):
                plan.resolve()

    def test_refuses_build_if_upstream_ci_is_not_green(self):
        def no_green(path):
            if '/' not in path:
                return {'default_branch': 'master'}
            if '/commits?' in path:
                return [{'sha': 'a'*40}]
            return {'check_runs': []}
        with patch.object(plan, 'github', side_effect=no_green):
            with self.assertRaisesRegex(ValueError, 'no CI-passing'):
                plan.resolve()
