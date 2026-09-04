import copy
import http.client
import json
from pathlib import Path
import subprocess
import tempfile
import threading
import unittest
from unittest.mock import Mock, patch
from monitor import Journal, make_server
from workloads import (LocalCollector, GitHubCollector, GitHubAPI, ProviderError, provider_sample,
                       activity_snapshot, github_row)


class WorkloadTests(unittest.TestCase):
    def test_cpu_denominator_pid_reuse_exit_and_unavailable(self):
        raw = [{'pid': 12, 'name': 'worker', 'created': 1, 'cpu_seconds': 2, 'memory_mb': 50}]
        collector = LocalCollector(lambda: copy.deepcopy(raw), cpu_count=4)
        first = collector.collect(now=10, mono=10)['rows'][0]
        self.assertIsNone(first['cpu_percent'])
        raw[0]['cpu_seconds'] = 6
        second = collector.collect(now=12, mono=12)['rows'][0]
        self.assertEqual(50, second['cpu_percent'])  # 4 CPU seconds / 2 seconds / 4 CPUs
        raw[0].update(created=11, cpu_seconds=.1)
        reused = collector.collect(now=13, mono=13)['rows']
        self.assertNotEqual(first['id'], reused[0]['id'])
        self.assertIsNone(reused[0]['cpu_percent'])
        self.assertEqual('ended', reused[1]['state'])
        raw.clear()
        self.assertTrue(all(r['state'] == 'ended' for r in collector.collect(now=14, mono=14)['rows']))
        self.assertEqual([], collector.collect(now=50, mono=50)['rows'])

    def test_inaccessible_start_time_never_implies_pid_continuity(self):
        collector = LocalCollector(lambda: [{'pid': 2, 'name': 'restricted', 'created': None,
                                            'cpu_seconds': None, 'memory_mb': None}])
        collector.collect(now=10, mono=10)
        self.assertIsNone(collector.collect(now=12, mono=12)['rows'][0]['cpu_percent'])

    def test_failure_retains_evidence_age_and_recovers_with_distinct_empty(self):
        collector = Mock(interval=3)
        collector.collect.return_value = {'rows': [{'id':'a','provider':'local','state':'running',
            'cpu_percent':40,'observed_at':100}], 'status':'ok'}
        good = provider_sample(collector, now=100)
        collector.collect.side_effect = ProviderError('timeout')
        failed = provider_sample(collector, good, now=105)
        self.assertEqual(100, failed['observed_at'])
        data = activity_snapshot({'local': failed}, now=106)
        self.assertEqual('disconnected', data['rows'][0]['freshness'])
        self.assertEqual(0, data['summary']['local_heavy_cpu_count'])
        collector.collect.side_effect = None
        collector.collect.return_value = {'rows':[], 'status':'empty'}
        recovered = provider_sample(collector, failed, now=110)
        self.assertEqual('empty', recovered['status'])
        self.assertEqual([], recovered['rows'])
        self.assertIsNone(recovered['error'])

    def test_browser_refresh_does_not_refresh_source_or_snapshot_identity(self):
        source = {'observed_at':100, 'last_attempt_at':100, 'status':'ok', 'rows':[
            {'id':'x','provider':'local','state':'running','observed_at':100,'cpu_percent':30}]}
        first = activity_snapshot({'local':source}, now=100)
        later = activity_snapshot({'local':source}, now=112)
        self.assertEqual(first['snapshot_id'], later['snapshot_id'])
        self.assertEqual(1, first['summary']['local_heavy_cpu_count'])
        self.assertEqual(0, later['summary']['local_heavy_cpu_count'])
        self.assertEqual('stale', later['rows'][0]['freshness'])

    def test_github_lifecycle_attempts_cache_and_missing_metrics(self):
        api = Mock()
        run = {'id':42,'run_attempt':1,'name':'CI','status':'in_progress','head_sha':'a'*40}
        job = {'id':17,'name':'Tests','status':'queued','labels':['ubuntu-latest'], 'steps':[]}
        api.get.side_effect = lambda path: {'workflow_runs':[run]} if '/runs?' in path else {'jobs':[job]}
        collector = GitHubCollector(api)
        queued = collector.collect(now=100)['rows'][0]
        self.assertIsNone(queued['cpu_percent'])
        self.assertIsNone(queued['memory_mb'])
        self.assertEqual('GitHub cloud', queued['location'])
        job.update(status='in_progress', started_at='2026-09-04T00:00:00Z',
                   steps=[{'name':'Unit tests','status':'in_progress'}])
        running = collector.collect(now=110)['rows'][0]
        self.assertEqual(queued['id'], running['id'])
        self.assertEqual('Unit tests', running['step'])
        run.update(status='completed')
        job.update(status='completed', conclusion='success', completed_at='2026-09-04T00:00:05Z')
        completed = collector.collect(now=120)['rows'][0]
        calls = api.get.call_count
        cached = collector.collect(now=130)['rows'][0]
        self.assertEqual(calls+1, api.get.call_count)
        self.assertEqual(completed, cached)  # cached terminal evidence retains its original time
        run.update(run_attempt=2,status='in_progress')
        self.assertNotEqual(queued['id'], collector.collect(now=140)['rows'][0]['id'])
        job['html_url']='javascript:bad()'
        self.assertTrue(github_row(job,run,150)['url'].startswith('https://github.com/FormatX66/BoxBrain/'))

    def test_github_detail_collection_is_bounded(self):
        api=Mock()
        runs=[{'id':n,'status':'in_progress'} for n in range(20)]
        api.get.side_effect=lambda path:{'workflow_runs':runs} if '/runs?' in path else {'jobs':[]}
        rows=GitHubCollector(api).collect()['rows']
        self.assertEqual(5,api.get.call_count)
        self.assertEqual(20,len(rows))

    def test_rate_limit_backoff_and_no_secret_errors(self):
        api=GitHubAPI()
        api.executable='gh'
        raw=b'HTTP/2.0 429 Too Many Requests\nRetry-After: 120\n\n{"message":"private payload"}'
        with patch('workloads.subprocess.run',return_value=subprocess.CompletedProcess([],1,raw,b'secret')):
            result=provider_sample(GitHubCollector(api),now=100)
        self.assertEqual('rate_limited',result['error'])
        self.assertEqual(429,result['http_status'])
        self.assertGreaterEqual(result['next_poll_seconds'],120)
        self.assertNotIn('secret',json.dumps(result))
        self.assertNotIn('private payload',json.dumps(result))
        self.assertIsNone(result['observed_at'])

    def test_native_collector_is_read_only_and_has_real_identity(self):
        import os
        collector=LocalCollector()
        data=collector.collect()
        own=next(row for row in data['rows'] if row.get('pid')==os.getpid())
        self.assertEqual('running',own['state'])
        self.assertGreater(own['started_at'],0)
        self.assertGreater(own['memory_mb'],0)
        self.assertEqual([],own['controls'])
        self.assertNotIn('command_line',own)

    def test_http_contract_no_writes_host_validation_and_summary_only_feed(self):
        with tempfile.TemporaryDirectory() as root:
            journal=Journal(Path(root)/'monitor.sqlite3')
            server=make_server(journal,0)
            worker=threading.Thread(target=server.serve_forever,daemon=True)
            worker.start()
            try:
                def request(method,path,headers=None):
                    client=http.client.HTTPConnection('127.0.0.1',server.server_port,timeout=2)
                    client.request(method,path,headers=headers or {})
                    response=client.getresponse()
                    body=response.read()
                    status=response.status
                    self.assertIsNone(response.getheader('Access-Control-Allow-Origin'))
                    client.close()
                    return status,body
                code,body=request('GET','/api/activity')
                self.assertEqual(200,code)
                data=json.loads(body)
                self.assertFalse(data['authority_granted'])
                self.assertNotIn('rows',data)
                self.assertEqual(403,request('GET','/api/activity',{'Host':'attacker.example'})[0])
                self.assertEqual(501,request('POST','/api/activity')[0])
                self.assertEqual(404,request('GET','/../workloads.py')[0])
                self.assertEqual(200,request('GET','/activity.js')[0])
            finally:
                server.shutdown()
                server.server_close()
                worker.join(2)


if __name__=='__main__':
    unittest.main()
