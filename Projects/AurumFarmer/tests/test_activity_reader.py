import copy
import json
import time
import unittest
from unittest.mock import patch, MagicMock
from aurum_farmer.activity_reader import ActivityReader, validate_activity, NoRedirect
from aurum_farmer.resource_budget import ResourceGovernor


class ActivityReaderTests(unittest.TestCase):
    def setUp(self):
        self.data={'schema':'aurum.workload-activity.v1','read_only':True,'authority_granted':False,
            'snapshot_id':'a'*64, 'providers':{'local':{'observed_at':100,'status':'ok'}},
            'summary':{'local_heavy_cpu_percent':40,'local_heavy_cpu_count':1,'github_active_observed':3}}

    def test_fresh_contention_changes_actual_budget_with_independent_host_corroboration(self):
        host={'available':True,'cpu_percent':60,'available_memory_mb':4000,'physical_load_percent':60,'commit_headroom_percent':30}
        governor=ResourceGovernor()
        activity=validate_activity(self.data,now=102)
        for _ in range(3):
            result=governor.choose(host,activity)
        self.assertEqual(1,result['cases'])
        self.assertTrue(result['activity_contention'])
        self.assertEqual('a'*64,result['activity_evidence']['snapshot_id'])
        clear={**host,'cpu_percent':20}
        for _ in range(5):
            result=governor.choose(clear,activity)
        self.assertEqual(16,result['cases'])
        self.assertEqual('not_configured',result['external_process_control'])
        self.assertEqual('not_configured',result['cloud_routing'])

    def test_stale_disconnected_forged_or_future_metrics_never_drive_budget(self):
        for change in ('stale','disconnected','future','authority','nan','schema'):
            data=copy.deepcopy(self.data)
            if change=='stale':data['providers']['local']['observed_at']=80
            if change=='disconnected':data['providers']['local']['status']='error'
            if change=='future':data['providers']['local']['observed_at']=200
            if change=='authority':data['authority_granted']=True
            if change=='nan':data['summary']['local_heavy_cpu_percent']=float('nan')
            if change=='schema':data['schema']='other'
            self.assertFalse(validate_activity(data,now=102)['available'],change)

    def test_read_timeout_and_cached_age_are_checked_without_redirects(self):
        reader=ActivityReader()
        response=MagicMock()
        response.__enter__.return_value.read.return_value=json.dumps(self.data).encode()
        with patch.object(reader.opener,'open',return_value=response) as opened, patch('aurum_farmer.activity_reader.time.time',return_value=101):
            self.assertTrue(reader.sample()['available'])
            self.assertEqual(.25,opened.call_args.kwargs['timeout'])
        with patch('aurum_farmer.activity_reader.time.time',return_value=115):
            self.assertFalse(reader.sample()['available'])
        reader.next_read=0
        with patch.object(reader.opener,'open',side_effect=OSError('secret')):
            self.assertFalse(reader.sample()['available'])
        self.assertIsNone(NoRedirect().redirect_request(None,None,None,None,None,None))

    def test_cloud_metrics_cannot_change_local_capacity(self):
        data=copy.deepcopy(self.data)
        data['summary'].update(local_heavy_cpu_count=0,local_heavy_cpu_percent=0,github_active_observed=1000)
        host={'available':True,'cpu_percent':60,'available_memory_mb':4000,'physical_load_percent':60}
        governor=ResourceGovernor()
        for _ in range(5):
            result=governor.choose(host,validate_activity(data,now=102))
        self.assertEqual(16,result['cases'])


if __name__=='__main__':
    unittest.main()
