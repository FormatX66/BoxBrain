import test from 'node:test';
import assert from 'node:assert/strict';
import { buildFarmerDispatch, dispatchFarmerObjective, validateFarmerObjective, FARMER_TOOL } from '../farmer-actuator.mjs';

test('tool surface is objective-only and rejects arbitrary execution fields', () => {
  assert.equal(FARMER_TOOL.name, 'dispatch_farmer_objective');
  assert.throws(() => validateFarmerObjective({ objective_id: 'abc', objective: 'do work', command: 'rm -rf /' }), /not allowed/);
  assert.throws(() => validateFarmerObjective({ objective_id: 'abc', objective: 'do work', repository: 'other/repo' }), /not allowed/);
});

test('dispatch contract is fixed to aurum_farmer_event and strict completion definition', () => {
  const value = buildFarmerDispatch({ objective_id: 'farmer-001', objective: 'Reach verified completion.' });
  assert.equal(value.event_type, 'aurum_farmer_event');
  assert.equal(value.client_payload.event.type, 'farmer_request');
  assert.deepEqual(value.client_payload.event.work, []);
  assert.equal(value.client_payload.constraints.continuation, 'event_driven_no_polling');
  assert.equal(value.client_payload.constraints.no_user_relay, true);
  assert.equal(value.client_payload.completion_definition.verification_passed, true);
});

test('missing credential stays machine-only rather than asking the human', async () => {
  const result = await dispatchFarmerObjective({ objective_id: 'farmer-002', objective: 'Continue.' }, { token: '' });
  assert.equal(result.status, 'machine_blocked');
  assert.equal(result.human_required, false);
  assert.equal(result.blocker.kind, 'github_execution_credential_unavailable');
});

test('accepted GitHub repository dispatch returns concrete ingress receipt', async () => {
  let seen;
  const fetchImpl = async (url, init) => {
    seen = { url, init };
    return {
      ok: true,
      status: 204,
      headers: { get: (name) => name.toLowerCase() === 'x-github-request-id' ? 'REQ_123' : null },
      text: async () => ''
    };
  };
  const result = await dispatchFarmerObjective(
    { objective_id: 'farmer-003', objective: 'Finish the Farmer objective.' },
    { token: 'test-token', repository: 'FormatX66/Chat-to-Git-Pipeline', fetchImpl }
  );
  assert.equal(result.status, 'dispatch_accepted');
  assert.equal(result.human_required, false);
  assert.equal(result.github_request_id, 'REQ_123');
  assert.equal(result.dispatch_receipt.length, 32);
  assert.equal(seen.url, 'https://api.github.com/repos/FormatX66/Chat-to-Git-Pipeline/dispatches');
  const body = JSON.parse(seen.init.body);
  assert.equal(body.event_type, 'aurum_farmer_event');
  assert.equal(body.client_payload.objective_id, 'farmer-003');
  assert.equal(body.client_payload.event.objective, 'Finish the Farmer objective.');
});

test('GitHub rejection is a machine blocker and preserves HTTP evidence', async () => {
  const fetchImpl = async () => ({
    ok: false,
    status: 403,
    headers: { get: () => null },
    text: async () => '{"message":"Resource not accessible"}'
  });
  const result = await dispatchFarmerObjective(
    { objective_id: 'farmer-004', objective: 'Continue.' },
    { token: 'bad-token', fetchImpl }
  );
  assert.equal(result.status, 'machine_blocked');
  assert.equal(result.human_required, false);
  assert.equal(result.blocker.http_status, 403);
});
