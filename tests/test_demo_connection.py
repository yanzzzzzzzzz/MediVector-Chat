import json
import os
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from medivector.api_auth import current_principal
from medivector.server import app


class DemoConnectionTests(unittest.TestCase):
    def setUp(self):
        self.users = {'demo': {'role': 'user', 'token': 'synthetic-' + 'd' * 32,
                               'organization_id': 'fictional-org', 'branch_ids': ['a'], 'department_ids': ['general']}}
        self.env = patch.dict(os.environ, {'API_USERS': json.dumps(self.users), 'DEMO_AUTO_CONNECT_USER': '',
                                         'API_RATE_LIMIT_PER_MINUTE': '10000'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app, client=('127.0.0.1', 1234))

    def test_default_still_requires_token_and_explicit_preview_uses_exact_account(self):
        self.assertEqual(self.client.get('/api/session').status_code, 401)
        with patch.dict(os.environ, {'DEMO_AUTO_CONNECT_USER': 'demo'}):
            self.assertEqual(self.client.get('/api/session').json(),
                             {'workspace': 'institutional', 'connection_mode': 'demo_auto'})
            def owned_conversations():
                principal = current_principal.get()
                self.assertEqual(principal.name, 'demo')
                self.assertEqual(principal.role, 'user')
                self.assertEqual(principal.organization_id, 'fictional-org')
                return []
            with patch('medivector.server.list_conversations', side_effect=owned_conversations):
                self.assertEqual(self.client.get('/api/conversations').status_code, 200)
            self.assertEqual(self.client.get('/api/documents').status_code, 403)
        self.assertEqual(self.client.get('/api/session').status_code, 401)

    def test_unknown_or_noninstitutional_demo_account_does_not_bypass_auth(self):
        with patch.dict(os.environ, {'DEMO_AUTO_CONNECT_USER': 'not-configured'}):
            self.assertEqual(self.client.get('/api/session').status_code, 401)
        personal = {'demo': {'role': 'admin', 'token': 'synthetic-' + 'd' * 32}}
        with patch.dict(os.environ, {'API_USERS': json.dumps(personal), 'DEMO_AUTO_CONNECT_USER': 'demo'}):
            self.assertEqual(self.client.get('/api/session').status_code, 401)

    def test_invalid_supplied_token_is_not_silently_replaced_with_demo_identity(self):
        with patch.dict(os.environ, {'DEMO_AUTO_CONNECT_USER': 'demo'}):
            self.assertEqual(self.client.get('/api/session', headers={'Authorization': 'Bearer invalid'}).status_code, 401)
