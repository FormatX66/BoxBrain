import { createHash } from 'node:crypto';

const DEFAULT_REPOSITORY = 'FormatX66/Chat-to-Git-Pipeline';
const EVENT_TYPE = 'aurum_farmer_event';
const OBJECTIVE_ID = /^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$/;

export const FARMER_TOOL = Object.freeze({
  name: 'dispatch_farmer_objective',
  description: 'Dispatch one bounded Aurum Farmer objective into the verified GitHub event-driven completion controller. This tool never accepts shell commands, code, workflow names, repository names, tokens, URLs, or arbitrary execution payloads.',
  inputSchema: {
    type: 'object',
    additionalProperties: false,
    required: ['objective_id', 'objective'],
    properties: {
      objective_id: {
        type: 'string',
        minLength: 3,
        maxLength: 64,
        pattern: '^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$'
      },
      objective: {
        type: 'string',
        minLength: 1,
        maxLength: 4000
      }
    }
  }
});

export const COMPLETION_DEFINITION = Object.freeze({
  no_further_human_input: true,
  no_known_bugs_or_glitches: true,
  fully_functional: true,
  no_required_changes_remaining: true,
  verification_passed: true
});

function boundedString(value, field, max) {
  if (typeof value !== 'string' || !value.trim()) throw new Error(`${field} must be a non-empty string`);
  if (value.length > max) throw new Error(`${field} exceeds ${max} characters`);
  return value.trim();
}

export function validateFarmerObjective(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('input must be an object');
  const keys = Object.keys(input);
  for (const key of keys) if (!['objective_id', 'objective'].includes(key)) throw new Error(`${key} is not allowed`);
  const objectiveId = String(input.objective_id ?? '');
  if (!OBJECTIVE_ID.test(objectiveId)) throw new Error('objective_id is invalid');
  const objective = boundedString(input.objective, 'objective', 4000);
  return { objective_id: objectiveId, objective };
}

export function buildFarmerDispatch(input, { source = 'chatgpt' } = {}) {
  const { objective_id, objective } = validateFarmerObjective(input);
  return {
    event_type: EVENT_TYPE,
    client_payload: {
      schema: 'aurum.farmer.dispatch.v1',
      objective_id,
      source,
      completion_definition: COMPLETION_DEFINITION,
      constraints: {
        continuation: 'event_driven_no_polling',
        no_user_relay: true,
        no_arbitrary_shell: true,
        independent_verification_required: true,
        last_known_good_required: true
      },
      event: {
        type: 'farmer_request',
        objective,
        work: []
      }
    }
  };
}

function normalizeRepository(value) {
  const repository = value || DEFAULT_REPOSITORY;
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repository)) throw new Error('AURUM_FARMER_REPOSITORY must be owner/name');
  return repository;
}

export async function dispatchFarmerObjective(input, {
  token = process.env.GITHUB_TOKEN,
  repository = process.env.AURUM_FARMER_REPOSITORY || DEFAULT_REPOSITORY,
  fetchImpl = fetch,
  source = 'chatgpt'
} = {}) {
  if (!token) {
    return {
      status: 'machine_blocked',
      human_required: false,
      blocker: { kind: 'github_execution_credential_unavailable' }
    };
  }
  repository = normalizeRepository(repository);
  const dispatch = buildFarmerDispatch(input, { source });
  const body = JSON.stringify(dispatch);
  const response = await fetchImpl(`https://api.github.com/repos/${repository}/dispatches`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: 'application/vnd.github+json',
      'X-GitHub-Api-Version': '2022-11-28',
      'Content-Type': 'application/json',
      'User-Agent': 'aurum-farmer-actuator/1'
    },
    body
  });
  let errorText = '';
  if (!response.ok) {
    try { errorText = (await response.text()).slice(0, 1000); } catch {}
    return {
      status: 'machine_blocked',
      human_required: false,
      blocker: {
        kind: 'github_repository_dispatch_failed',
        http_status: response.status,
        detail: errorText
      }
    };
  }
  const objectiveId = dispatch.client_payload.objective_id;
  const githubRequestId = response.headers?.get?.('x-github-request-id') ?? null;
  const receiptId = createHash('sha256')
    .update(`${repository}\0${objectiveId}\0${githubRequestId ?? ''}\0${body}`)
    .digest('hex')
    .slice(0, 32);
  return {
    status: 'dispatch_accepted',
    human_required: false,
    objective_id: objectiveId,
    repository,
    event_type: EVENT_TYPE,
    github_request_id: githubRequestId,
    dispatch_receipt: receiptId,
    continuation: 'event_driven_no_polling',
    terminal_states: ['verified_completion', 'proven_human_only_blocker']
  };
}

// Framework-neutral MCP handler. Existing Aurum Chat Tree server only needs to expose
// FARMER_TOOL in tools/list and route tools/call for its name here.
export async function handleFarmerToolCall(name, args, options = {}) {
  if (name !== FARMER_TOOL.name) return null;
  return dispatchFarmerObjective(args, options);
}
