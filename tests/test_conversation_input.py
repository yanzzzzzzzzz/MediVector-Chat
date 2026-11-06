import json
import os
import unittest
from uuid import UUID
from unittest.mock import patch

from fastapi.testclient import TestClient
from medivector.server import app
from medivector.schemas import AskRequest


class ConversationInputTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'API_USERS': '{}', 'API_RATE_LIMIT_PER_MINUTE': '10000'})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.client = TestClient(app, client=('127.0.0.1', 1234))

    def test_invalid_ids_are_rejected_before_qa_database_or_deletion(self):
        with patch('medivector.server.ask_question') as ask, patch('medivector.server.load_conversation_history') as load, patch('medivector.server.delete_conversation') as delete:
            for value in ('default', 'not-a-uuid', 'prototype-123', ''):
                self.assertEqual(self.client.post('/api/ask', json={'question': '合成問題', 'conversation_id': value}).status_code, 400)
            for value in ('default', 'not-a-uuid', 'prototype-123'):
                self.assertEqual(self.client.get('/api/conversations/' + value).status_code, 400)
                self.assertEqual(self.client.delete('/api/conversations/' + value).status_code, 400)
        ask.assert_not_called()
        load.assert_not_called()
        delete.assert_not_called()

    def test_omitted_id_is_unique_and_existing_uuid_is_canonicalized(self):
        first = AskRequest(question='first').conversation_id
        second = AskRequest(question='second').conversation_id
        self.assertNotEqual(first, second)
        self.assertEqual(str(UUID(first)), first)
        self.assertEqual(AskRequest(question='test', conversation_id=first.upper()).conversation_id, first)
        with patch('medivector.server.ask_question', return_value={
                'answer': '合成回覆', 'rag_enabled': True, 'references': [], 'memory_messages': 2}) as ask:
            response = self.client.post('/api/ask', json={'question': '合成問題'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(str(UUID(ask.call_args.args[0]['conversation_id'])), ask.call_args.args[0]['conversation_id'])

    def test_workspace_mode_is_authenticated_and_does_not_expose_credentials(self):
        self.assertEqual(self.client.get('/api/session').json(), {'workspace': 'legacy'})
        users = {'test-user': {'role': 'user', 'token': 'synthetic-' + 'a' * 32, 'organization_id': 'synthetic-org'}}
        with patch.dict(os.environ, {'API_USERS': json.dumps(users)}):
            self.assertEqual(self.client.get('/api/session').status_code, 401)
            response = self.client.get('/api/session', headers={'Authorization': 'Bearer ' + users['test-user']['token']})
            self.assertEqual(response.json(), {'workspace': 'institutional'})
            self.assertNotIn(users['test-user']['token'], response.text)
