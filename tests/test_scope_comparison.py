import unittest
from evaluation.scope_comparison import compare


class ScopeComparisonTests(unittest.TestCase):
    def test_invalid_duplicate_scopes_or_target_are_rejected_before_calls(self):
        class Client:
            def get(self, *args, **kwargs): raise AssertionError('No request expected')
        scope = {'branch_id': 'a', 'department_id': 'general'}
        with self.assertRaises(ValueError):
            compare(Client(), {'question': 'test', 'scopes': [scope, scope], 'target': scope})

    def test_manifest_or_query_contamination_aborts_comparison(self):
        import httpx
        scopes = [{'branch_id': 'a', 'department_id': 'general'}, {'branch_id': 'b', 'department_id': 'general'}]
        for contaminated in ('manifest', 'query'):
            gets = 0
            def handler(request):
                nonlocal gets
                if request.method == 'GET':
                    gets += 1
                    return httpx.Response(200, json={'embedding_model': 'model', 'manifest_sha256': 'changed' if contaminated == 'manifest' and gets > 2 else 'frozen'})
                return httpx.Response(200, json={'settings': {'embedding_model': 'model'}, 'standalone_query': 'changed' if contaminated == 'query' else 'question', 'terms': [], 'results': []})
            with self.subTest(contaminated=contaminated), httpx.Client(base_url='https://example.invalid', transport=httpx.MockTransport(handler)) as client:
                with self.assertRaises(ValueError):
                    compare(client, {'question': 'question', 'scopes': scopes, 'target': scopes[0]})
