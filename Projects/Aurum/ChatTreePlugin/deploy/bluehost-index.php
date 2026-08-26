<?php
declare(strict_types=1);

const TEMPLATE_URI = 'ui://aurum/chat-tree/v5.html';
const RESOURCE_MIME_TYPE = 'text/html;profile=mcp-app';
const FARMER_REPOSITORY = 'FormatX66/Chat-to-Git-Pipeline';
const FARMER_EVENT_TYPE = 'aurum_farmer_event';

$deploymentRoot = '/home1/madmorri/apps/aurum-chat-tree';
$releaseRoot = $deploymentRoot . '/current';
$sourceCommitFile = $releaseRoot . '/SOURCE_COMMIT';
$sourceCommit = is_file($sourceCommitFile) ? trim((string)file_get_contents($sourceCommitFile)) : 'unknown';
$appRoot = $releaseRoot . '/Projects/Aurum/ChatTreePlugin';
$aurumRoot = dirname($appRoot);
$bridgePath = $aurumRoot . '/Experiments/chat_tree_bridge.py';
$widgetPath = $appRoot . '/public/chat-tree-widget.html';
$treePath = $deploymentRoot . '/state/chat-process-tree.json';
$eventsPath = $deploymentRoot . '/state/shared-state/events.jsonl';
$projectionPath = $deploymentRoot . '/state/shared-state/CURRENT_STATE.json';
$farmerTokenPath = $deploymentRoot . '/secrets/github-token';

header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: POST, GET, OPTIONS, DELETE');
header('Access-Control-Allow-Headers: content-type, mcp-session-id, authorization');
header('Access-Control-Expose-Headers: Mcp-Session-Id');
header('Cache-Control: no-store');

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') === 'OPTIONS') {
    http_response_code(204);
    exit;
}

function send_json(array $payload, int $status = 200): never
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    echo json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
    exit;
}

function rpc_error(mixed $id, int $code, string $message, mixed $data = null): array
{
    $error = ['code' => $code, 'message' => $message];
    if ($data !== null) {
        $error['data'] = $data;
    }
    return ['jsonrpc' => '2.0', 'id' => $id, 'error' => $error];
}

function bridge_call(
    string $bridgePath,
    string $aurumRoot,
    string $treePath,
    string $eventsPath,
    string $projectionPath,
    array $request
): array
{
    $descriptors = [
        0 => ['pipe', 'r'],
        1 => ['pipe', 'w'],
        2 => ['pipe', 'w'],
    ];
    $process = proc_open([
        '/usr/bin/python3',
        $bridgePath,
        '--tree',
        $treePath,
        '--events',
        $eventsPath,
        '--projection',
        $projectionPath,
    ], $descriptors, $pipes, $aurumRoot);
    if (!is_resource($process)) {
        throw new RuntimeException('Unable to start the canonical Chat Tree bridge.');
    }

    fwrite($pipes[0], json_encode($request, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR));
    fclose($pipes[0]);
    $stdout = stream_get_contents($pipes[1]);
    fclose($pipes[1]);
    $stderr = stream_get_contents($pipes[2]);
    fclose($pipes[2]);
    $status = proc_close($process);

    $payload = json_decode($stdout ?: '', true, 512, JSON_THROW_ON_ERROR);
    if ($status !== 0 || !is_array($payload) || !($payload['ok'] ?? false)) {
        $detail = trim($stderr) ?: (is_array($payload) ? (string)($payload['message'] ?? 'Bridge failed.') : 'Bridge failed.');
        throw new RuntimeException($detail);
    }
    return $payload;
}

function snapshot(
    string $bridgePath,
    string $aurumRoot,
    string $treePath,
    string $eventsPath,
    string $projectionPath,
    ?string $focusId
): array
{
    $treeRequest = ['command' => 'get_tree'];
    if ($focusId !== null && $focusId !== '') {
        $treeRequest['focus_id'] = $focusId;
    }
    $treeResponse = bridge_call($bridgePath, $aurumRoot, $treePath, $eventsPath, $projectionPath, $treeRequest);
    $stateResponse = bridge_call(
        $bridgePath,
        $aurumRoot,
        $treePath,
        $eventsPath,
        $projectionPath,
        ['command' => 'get_state']
    );
    $consolidationResponse = bridge_call(
        $bridgePath,
        $aurumRoot,
        $treePath,
        $eventsPath,
        $projectionPath,
        ['command' => 'plan_consolidation']
    );
    $tree = $treeResponse['tree'];
    $focusPath = $tree['focus_path'] ?? [];
    $resolvedFocus = $focusPath ? $focusPath[count($focusPath) - 1] : ($tree['root_id'] ?? null);
    return [
        'tree' => $tree,
        'state' => $stateResponse['state'],
        'consolidation' => $consolidationResponse,
        'focusId' => $resolvedFocus,
    ];
}

function dispatch_farmer_objective(array $arguments, string $tokenPath): array
{
    $allowedKeys = ['objective_id', 'objective'];
    foreach (array_keys($arguments) as $key) {
        if (!in_array((string)$key, $allowedKeys, true)) {
            throw new InvalidArgumentException((string)$key . ' is not allowed');
        }
    }
    $objectiveId = (string)($arguments['objective_id'] ?? '');
    $objective = trim((string)($arguments['objective'] ?? ''));
    if (!preg_match('/^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$/D', $objectiveId)) {
        throw new InvalidArgumentException('objective_id is invalid');
    }
    if ($objective === '' || strlen($objective) > 4000) {
        throw new InvalidArgumentException('objective must contain 1 to 4000 characters');
    }
    if (!is_file($tokenPath)) {
        return [
            'status' => 'machine_blocked',
            'human_required' => false,
            'blocker' => ['kind' => 'github_execution_credential_unavailable'],
        ];
    }
    $token = trim((string)file_get_contents($tokenPath));
    if ($token === '') {
        return [
            'status' => 'machine_blocked',
            'human_required' => false,
            'blocker' => ['kind' => 'github_execution_credential_unavailable'],
        ];
    }
    $completionDefinition = [
        'no_further_human_input' => true,
        'no_known_bugs_or_glitches' => true,
        'fully_functional' => true,
        'no_required_changes_remaining' => true,
        'verification_passed' => true,
    ];
    $dispatch = [
        'event_type' => FARMER_EVENT_TYPE,
        'client_payload' => [
            'schema' => 'aurum.farmer.dispatch.v1',
            'objective_id' => $objectiveId,
            'source' => 'chatgpt',
            'completion_definition' => $completionDefinition,
            'constraints' => [
                'continuation' => 'event_driven_no_polling',
                'no_user_relay' => true,
                'no_arbitrary_shell' => true,
                'independent_verification_required' => true,
                'last_known_good_required' => true,
            ],
            'event' => ['type' => 'farmer_request', 'objective' => $objective, 'work' => []],
        ],
    ];
    $body = json_encode($dispatch, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
    $githubRequestId = null;
    $responseHeaders = [];
    $curl = curl_init('https://api.github.com/repos/' . FARMER_REPOSITORY . '/dispatches');
    if ($curl === false) {
        throw new RuntimeException('Unable to initialize the GitHub dispatch client.');
    }
    curl_setopt_array($curl, [
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => $body,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CONNECTTIMEOUT => 10,
        CURLOPT_TIMEOUT => 30,
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $token,
            'Accept: application/vnd.github+json',
            'X-GitHub-Api-Version: 2022-11-28',
            'Content-Type: application/json',
            'User-Agent: aurum-farmer-actuator/1',
        ],
        CURLOPT_HEADERFUNCTION => static function ($handle, string $line) use (&$responseHeaders): int {
            $length = strlen($line);
            $parts = explode(':', $line, 2);
            if (count($parts) === 2) {
                $responseHeaders[strtolower(trim($parts[0]))] = trim($parts[1]);
            }
            return $length;
        },
    ]);
    $responseBody = curl_exec($curl);
    $httpStatus = (int)curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
    $curlError = curl_error($curl);
    curl_close($curl);
    $githubRequestId = $responseHeaders['x-github-request-id'] ?? null;
    if ($responseBody === false || $httpStatus < 200 || $httpStatus >= 300) {
        return [
            'status' => 'machine_blocked',
            'human_required' => false,
            'blocker' => [
                'kind' => 'github_repository_dispatch_failed',
                'http_status' => $httpStatus,
                'detail' => substr($curlError !== '' ? $curlError : (string)$responseBody, 0, 1000),
            ],
        ];
    }
    $receipt = substr(hash('sha256', FARMER_REPOSITORY . "\0" . $objectiveId . "\0" . ($githubRequestId ?? '') . "\0" . $body), 0, 32);
    return [
        'status' => 'dispatch_accepted',
        'human_required' => false,
        'objective_id' => $objectiveId,
        'repository' => FARMER_REPOSITORY,
        'event_type' => FARMER_EVENT_TYPE,
        'github_request_id' => $githubRequestId,
        'dispatch_receipt' => $receipt,
        'continuation' => 'event_driven_no_polling',
        'terminal_states' => ['verified_completion', 'proven_human_only_blocker'],
    ];
}

function tool_descriptors(): array
{
    $showMeta = [
        'ui' => ['resourceUri' => TEMPLATE_URI],
        'openai/outputTemplate' => TEMPLATE_URI,
        'openai/toolInvocation/invoking' => 'Loading Chat Tree…',
        'openai/toolInvocation/invoked' => 'Chat Tree loaded.',
        'ui/resourceUri' => TEMPLATE_URI,
    ];
    $splitMeta = [
        'ui' => ['resourceUri' => TEMPLATE_URI],
        'openai/outputTemplate' => TEMPLATE_URI,
        'openai/toolInvocation/invoking' => 'Splitting topic…',
        'openai/toolInvocation/invoked' => 'Topic split recorded.',
        'ui/resourceUri' => TEMPLATE_URI,
    ];
    return [
        [
            'name' => 'show_chat_tree',
            'title' => 'Show Aurum Chat Tree',
            'description' => 'Use this when the user wants to view, search, organize, or review consolidation candidates in current Aurum conversation/process branches.',
            'inputSchema' => [
                'type' => 'object',
                'properties' => ['focusId' => ['type' => 'string']],
                'additionalProperties' => false,
                '$schema' => 'http://json-schema.org/draft-07/schema#',
            ],
            'annotations' => [
                'readOnlyHint' => true,
                'destructiveHint' => false,
                'idempotentHint' => true,
                'openWorldHint' => false,
            ],
            'execution' => ['taskSupport' => 'forbidden'],
            '_meta' => $showMeta,
        ],
        [
            'name' => 'split_chat_topic',
            'title' => 'Split Aurum Chat Topic',
            'description' => 'Use this when the objective changes enough to create a child subproblem or sibling topic in the durable Chat Tree.',
            'inputSchema' => [
                'type' => 'object',
                'properties' => [
                    'currentId' => ['type' => 'string', 'minLength' => 1],
                    'newNodeId' => ['type' => 'string', 'minLength' => 1],
                    'title' => ['type' => 'string', 'minLength' => 1],
                    'objective' => ['type' => 'string', 'minLength' => 1],
                    'relation' => ['type' => 'string', 'enum' => ['child', 'sibling']],
                    'concepts' => ['type' => 'array', 'items' => ['type' => 'string']],
                    'summary' => ['type' => 'string'],
                ],
                'required' => ['currentId', 'newNodeId', 'title', 'objective', 'relation'],
                'additionalProperties' => false,
                '$schema' => 'http://json-schema.org/draft-07/schema#',
            ],
            'annotations' => [
                'readOnlyHint' => false,
                'destructiveHint' => false,
                'idempotentHint' => false,
                'openWorldHint' => false,
            ],
            'execution' => ['taskSupport' => 'forbidden'],
            '_meta' => $splitMeta,
        ],
        [
            'name' => 'publish_live_state',
            'title' => 'Publish Aurum Cross-Chat Live State',
            'description' => 'Append status, current action, blocker, evidence, and next action to the evidence-backed shared-state bus. Verified runtime/success claims require evidence; the bus grants no execution authority.',
            'inputSchema' => [
                'type' => 'object',
                'properties' => [
                    'subjectId' => ['type' => 'string', 'minLength' => 1],
                    'subjectKind' => ['type' => 'string', 'minLength' => 1],
                    'status' => ['type' => 'string', 'enum' => [
                        'planned', 'queued', 'running_unverified', 'running_verified',
                        'waiting', 'blocked', 'succeeded', 'failed', 'no_change', 'refused',
                    ]],
                    'currentAction' => ['type' => 'string', 'minLength' => 1],
                    'blocker' => ['type' => ['string', 'null']],
                    'evidence' => ['type' => 'array', 'items' => ['type' => 'string', 'minLength' => 1]],
                    'nextAction' => ['type' => 'string', 'minLength' => 1],
                    'actor' => ['type' => 'string', 'minLength' => 1],
                    'source' => ['type' => 'string', 'minLength' => 1],
                    'nodeId' => ['type' => 'string', 'minLength' => 1],
                    'summary' => ['type' => 'string'],
                    'dependencyIds' => ['type' => 'array', 'items' => ['type' => 'string', 'minLength' => 1]],
                    'confidence' => ['type' => 'number', 'minimum' => 0, 'maximum' => 1],
                    'authorityRef' => ['type' => 'string', 'minLength' => 1],
                    'eventId' => ['type' => 'string', 'minLength' => 1],
                    'payload' => ['type' => 'object', 'additionalProperties' => true],
                ],
                'required' => [
                    'subjectId', 'status', 'currentAction', 'blocker', 'evidence',
                    'nextAction', 'actor', 'source',
                ],
                'additionalProperties' => false,
                '$schema' => 'http://json-schema.org/draft-07/schema#',
            ],
            'annotations' => [
                'readOnlyHint' => false,
                'destructiveHint' => false,
                'idempotentHint' => false,
                'openWorldHint' => false,
            ],
            'execution' => ['taskSupport' => 'forbidden'],
        ],
        [
            'name' => 'read_live_state',
            'title' => 'Read Aurum Cross-Chat Live State',
            'description' => 'Read the newest evidence-backed status, current action, blocker, evidence, and next action from the shared-state bus instead of relying on chat memory.',
            'inputSchema' => [
                'type' => 'object',
                'properties' => [
                    'subjectId' => ['type' => 'string', 'minLength' => 1],
                    'nodeId' => ['type' => 'string', 'minLength' => 1],
                    'verifiedOnly' => ['type' => 'boolean'],
                    'includeHistory' => ['type' => 'boolean'],
                    'limit' => ['type' => 'integer', 'minimum' => 1, 'maximum' => 500],
                ],
                'additionalProperties' => false,
                '$schema' => 'http://json-schema.org/draft-07/schema#',
            ],
            'annotations' => [
                'readOnlyHint' => true,
                'destructiveHint' => false,
                'idempotentHint' => true,
                'openWorldHint' => false,
            ],
            'execution' => ['taskSupport' => 'forbidden'],
        ],
        [
            'name' => 'plan_chat_branch_consolidation',
            'title' => 'Plan Chat Branch Consolidation',
            'description' => 'Find completed or failed Chat Tree nodes in the exact same parent group and branch lane. This is read-only and cannot archive conversations in ChatGPT history.',
            'inputSchema' => [
                'type' => 'object',
                'properties' => [
                    'parentId' => ['type' => 'string', 'minLength' => 1],
                    'laneId' => ['type' => 'string', 'minLength' => 1],
                ],
                'additionalProperties' => false,
                '$schema' => 'http://json-schema.org/draft-07/schema#',
            ],
            'annotations' => [
                'readOnlyHint' => true,
                'destructiveHint' => false,
                'idempotentHint' => true,
                'openWorldHint' => false,
            ],
            'execution' => ['taskSupport' => 'forbidden'],
            '_meta' => [
                'ui' => ['resourceUri' => TEMPLATE_URI],
                'openai/outputTemplate' => TEMPLATE_URI,
                'openai/toolInvocation/invoking' => 'Checking branch archives…',
                'openai/toolInvocation/invoked' => 'Branch archive plan ready.',
                'ui/resourceUri' => TEMPLATE_URI,
            ],
        ],
        [
            'name' => 'consolidate_chat_branch',
            'title' => 'Consolidate and Archive Chat Tree Branch',
            'description' => 'Apply one exact reviewed plan: create a provenance-preserving checkpoint and archive its completed/failed source nodes in the Aurum Chat Tree. This does not archive the underlying conversations in ChatGPT history.',
            'inputSchema' => [
                'type' => 'object',
                'properties' => [
                    'sourceNodeIds' => [
                        'type' => 'array',
                        'items' => ['type' => 'string', 'minLength' => 1],
                        'minItems' => 2,
                        'maxItems' => 64,
                    ],
                    'planToken' => ['type' => 'string', 'minLength' => 64, 'maxLength' => 64],
                    'newNodeId' => ['type' => 'string', 'minLength' => 1],
                    'title' => ['type' => 'string', 'minLength' => 1],
                    'summary' => ['type' => 'string'],
                ],
                'required' => ['sourceNodeIds', 'planToken', 'newNodeId', 'title'],
                'additionalProperties' => false,
                '$schema' => 'http://json-schema.org/draft-07/schema#',
            ],
            'annotations' => [
                'readOnlyHint' => false,
                'destructiveHint' => true,
                'idempotentHint' => false,
                'openWorldHint' => false,
            ],
            'execution' => ['taskSupport' => 'forbidden'],
            '_meta' => [
                'ui' => ['resourceUri' => TEMPLATE_URI],
                'openai/outputTemplate' => TEMPLATE_URI,
                'openai/toolInvocation/invoking' => 'Consolidating branch…',
                'openai/toolInvocation/invoked' => 'Chat Tree sources archived.',
                'ui/resourceUri' => TEMPLATE_URI,
            ],
        ],
        [
            'name' => 'dispatch_farmer_objective',
            'title' => 'Dispatch Aurum Farmer Objective',
            'description' => 'Dispatch one bounded Aurum Farmer objective into the verified GitHub event-driven completion controller. This tool never accepts shell commands, code, workflow names, repository names, tokens, URLs, or arbitrary execution payloads.',
            'inputSchema' => [
                'type' => 'object',
                'properties' => [
                    'objective_id' => [
                        'type' => 'string',
                        'minLength' => 3,
                        'maxLength' => 64,
                        'pattern' => '^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$',
                    ],
                    'objective' => ['type' => 'string', 'minLength' => 1, 'maxLength' => 4000],
                ],
                'required' => ['objective_id', 'objective'],
                'additionalProperties' => false,
                '$schema' => 'http://json-schema.org/draft-07/schema#',
            ],
            'annotations' => [
                'readOnlyHint' => false,
                'destructiveHint' => false,
                'idempotentHint' => false,
                'openWorldHint' => true,
            ],
            'execution' => ['taskSupport' => 'forbidden'],
        ],
    ];
}

function handle_rpc(
    array $message,
    string $bridgePath,
    string $aurumRoot,
    string $treePath,
    string $eventsPath,
    string $projectionPath,
    string $widgetPath,
    string $farmerTokenPath
): ?array
{
    $id = $message['id'] ?? null;
    $method = $message['method'] ?? null;
    $params = is_array($message['params'] ?? null) ? $message['params'] : [];

    if (!is_string($method)) {
        return rpc_error($id, -32600, 'Invalid Request');
    }

    if ($method === 'notifications/initialized' || str_starts_with($method, 'notifications/')) {
        return null;
    }

    if ($method === 'initialize') {
        $requested = $params['protocolVersion'] ?? '2025-06-18';
        return [
            'jsonrpc' => '2.0',
            'id' => $id,
            'result' => [
                'protocolVersion' => is_string($requested) ? $requested : '2025-06-18',
                'capabilities' => [
                    'resources' => ['listChanged' => true],
                    'tools' => ['listChanged' => true],
                ],
                'serverInfo' => ['name' => 'aurum-chat-tree-plugin', 'version' => '0.3.0'],
            ],
        ];
    }

    if ($method === 'ping') {
        return ['jsonrpc' => '2.0', 'id' => $id, 'result' => (object)[]];
    }

    if ($method === 'tools/list') {
        return ['jsonrpc' => '2.0', 'id' => $id, 'result' => ['tools' => tool_descriptors()]];
    }

    if ($method === 'resources/list') {
        return [
            'jsonrpc' => '2.0',
            'id' => $id,
            'result' => ['resources' => [[
                'uri' => TEMPLATE_URI,
                'name' => 'aurum-chat-tree-widget',
                'mimeType' => RESOURCE_MIME_TYPE,
            ]]],
        ];
    }

    if ($method === 'resources/templates/list' || $method === 'prompts/list') {
        $key = $method === 'prompts/list' ? 'prompts' : 'resourceTemplates';
        return ['jsonrpc' => '2.0', 'id' => $id, 'result' => [$key => []]];
    }

    if ($method === 'resources/read') {
        if (($params['uri'] ?? null) !== TEMPLATE_URI) {
            return rpc_error($id, -32602, 'Unknown resource URI.');
        }
        $widget = file_get_contents($widgetPath);
        if ($widget === false) {
            throw new RuntimeException('Widget resource is unavailable.');
        }
        return [
            'jsonrpc' => '2.0',
            'id' => $id,
            'result' => ['contents' => [[
                'uri' => TEMPLATE_URI,
                'mimeType' => RESOURCE_MIME_TYPE,
                'text' => $widget,
                '_meta' => [
                    'ui' => [
                        'prefersBorder' => true,
                        'csp' => ['connectDomains' => [], 'resourceDomains' => []],
                    ],
                    'openai/widgetDescription' => 'Aurum Chat Tree navigator with strict same-group/same-branch consolidation planning.',
                ],
            ]]],
        ];
    }

    if ($method === 'tools/call') {
        $name = $params['name'] ?? null;
        $arguments = is_array($params['arguments'] ?? null) ? $params['arguments'] : [];
        if ($name === 'show_chat_tree') {
            $data = snapshot(
                $bridgePath,
                $aurumRoot,
                $treePath,
                $eventsPath,
                $projectionPath,
                isset($arguments['focusId']) ? (string)$arguments['focusId'] : null
            );
            return [
                'jsonrpc' => '2.0',
                'id' => $id,
                'result' => [
                    'structuredContent' => $data,
                    'content' => [['type' => 'text', 'text' => 'Showing the current Aurum Chat Tree.']],
                ],
            ];
        }

        if ($name === 'split_chat_topic') {
            foreach (['currentId', 'newNodeId', 'title', 'objective', 'relation'] as $required) {
                if (!isset($arguments[$required]) || trim((string)$arguments[$required]) === '') {
                    return rpc_error($id, -32602, 'Missing required argument: ' . $required);
                }
            }
            $relation = (string)$arguments['relation'];
            if (!in_array($relation, ['child', 'sibling'], true)) {
                return rpc_error($id, -32602, 'relation must be child or sibling');
            }
            $routed = bridge_call($bridgePath, $aurumRoot, $treePath, $eventsPath, $projectionPath, [
                'command' => 'route_topic',
                'current_id' => (string)$arguments['currentId'],
                'new_node_id' => (string)$arguments['newNodeId'],
                'title' => (string)$arguments['title'],
                'objective' => (string)$arguments['objective'],
                'concepts' => is_array($arguments['concepts'] ?? null) ? array_values($arguments['concepts']) : [],
                'relation_hint' => $relation === 'child' ? 'subproblem' : 'new',
                'summary' => (string)($arguments['summary'] ?? ''),
                'evidence_refs' => [],
            ]);
            $data = snapshot(
                $bridgePath,
                $aurumRoot,
                $treePath,
                $eventsPath,
                $projectionPath,
                (string)$routed['focus_id']
            );
            $data['route'] = $routed;
            return [
                'jsonrpc' => '2.0',
                'id' => $id,
                'result' => [
                    'structuredContent' => $data,
                    'content' => [[
                        'type' => 'text',
                        'text' => (string)$arguments['title'] . ' is now a ' . $relation . ' Chat Tree branch.',
                    ]],
                ],
            ];
        }

        if ($name === 'publish_live_state') {
            foreach (['subjectId', 'status', 'currentAction', 'nextAction', 'actor', 'source'] as $required) {
                if (!isset($arguments[$required]) || trim((string)$arguments[$required]) === '') {
                    return rpc_error($id, -32602, 'Missing required argument: ' . $required);
                }
            }
            if (!array_key_exists('blocker', $arguments)) {
                return rpc_error($id, -32602, 'Missing required argument: blocker');
            }
            if (!is_array($arguments['evidence'] ?? null)) {
                return rpc_error($id, -32602, 'evidence must be an array');
            }
            $allowedStatuses = [
                'planned', 'queued', 'running_unverified', 'running_verified',
                'waiting', 'blocked', 'succeeded', 'failed', 'no_change', 'refused',
            ];
            if (!in_array((string)$arguments['status'], $allowedStatuses, true)) {
                return rpc_error($id, -32602, 'Unknown live-state status.');
            }
            $request = [
                'command' => 'publish_live_state',
                'subject_id' => (string)$arguments['subjectId'],
                'subject_kind' => (string)($arguments['subjectKind'] ?? 'chat'),
                'status' => (string)$arguments['status'],
                'current_action' => (string)$arguments['currentAction'],
                'blocker' => $arguments['blocker'] === null ? null : (string)$arguments['blocker'],
                'evidence' => array_values($arguments['evidence']),
                'next_action' => (string)$arguments['nextAction'],
                'actor' => (string)$arguments['actor'],
                'source' => (string)$arguments['source'],
                'summary' => (string)($arguments['summary'] ?? ''),
                'dependency_ids' => is_array($arguments['dependencyIds'] ?? null)
                    ? array_values($arguments['dependencyIds'])
                    : [],
                'payload' => is_array($arguments['payload'] ?? null) ? $arguments['payload'] : [],
            ];
            foreach ([
                'nodeId' => 'node_id',
                'confidence' => 'confidence',
                'authorityRef' => 'authority_ref',
                'eventId' => 'event_id',
            ] as $argumentName => $requestName) {
                if (array_key_exists($argumentName, $arguments)) {
                    $request[$requestName] = $arguments[$argumentName];
                }
            }
            $published = bridge_call(
                $bridgePath,
                $aurumRoot,
                $treePath,
                $eventsPath,
                $projectionPath,
                $request
            );
            return [
                'jsonrpc' => '2.0',
                'id' => $id,
                'result' => [
                    'structuredContent' => $published,
                    'content' => [[
                        'type' => 'text',
                        'text' => 'Live state appended to the evidence-backed bus; no execution authority was granted.',
                    ]],
                ],
            ];
        }

        if ($name === 'read_live_state') {
            $limit = isset($arguments['limit']) ? (int)$arguments['limit'] : 50;
            if ($limit < 1 || $limit > 500) {
                return rpc_error($id, -32602, 'limit must be between 1 and 500');
            }
            $request = [
                'command' => 'read_live_state',
                'verified_only' => (bool)($arguments['verifiedOnly'] ?? false),
                'include_history' => (bool)($arguments['includeHistory'] ?? false),
                'limit' => $limit,
            ];
            if (isset($arguments['subjectId'])) {
                $request['subject_id'] = (string)$arguments['subjectId'];
            }
            if (isset($arguments['nodeId'])) {
                $request['node_id'] = (string)$arguments['nodeId'];
            }
            $consumed = bridge_call(
                $bridgePath,
                $aurumRoot,
                $treePath,
                $eventsPath,
                $projectionPath,
                $request
            );
            return [
                'jsonrpc' => '2.0',
                'id' => $id,
                'result' => [
                    'structuredContent' => $consumed,
                    'content' => [[
                        'type' => 'text',
                        'text' => 'Read the newest matching state from the append-only shared-state bus.',
                    ]],
                ],
            ];
        }

        if ($name === 'plan_chat_branch_consolidation') {
            $request = ['command' => 'plan_consolidation'];
            if (isset($arguments['parentId'])) {
                $request['parent_id'] = (string)$arguments['parentId'];
            }
            if (isset($arguments['laneId'])) {
                $request['lane_id'] = (string)$arguments['laneId'];
            }
            $planned = bridge_call(
                $bridgePath,
                $aurumRoot,
                $treePath,
                $eventsPath,
                $projectionPath,
                $request
            );
            $data = snapshot(
                $bridgePath,
                $aurumRoot,
                $treePath,
                $eventsPath,
                $projectionPath,
                null
            );
            $data['consolidation'] = $planned;
            $count = (int)($planned['candidate_count'] ?? 0);
            $message = $count > 0
                ? 'Found ' . $count . ' exact same-group/same-branch consolidation candidate' . ($count === 1 ? '.' : 's.')
                : 'No exact same-group/same-branch consolidation candidates are ready.';
            return [
                'jsonrpc' => '2.0',
                'id' => $id,
                'result' => [
                    'structuredContent' => $data,
                    'content' => [['type' => 'text', 'text' => $message]],
                ],
            ];
        }

        if ($name === 'consolidate_chat_branch') {
            foreach (['sourceNodeIds', 'planToken', 'newNodeId', 'title'] as $required) {
                if (!array_key_exists($required, $arguments)) {
                    return rpc_error($id, -32602, 'Missing required argument: ' . $required);
                }
            }
            if (!is_array($arguments['sourceNodeIds']) || count($arguments['sourceNodeIds']) < 2 || count($arguments['sourceNodeIds']) > 64) {
                return rpc_error($id, -32602, 'sourceNodeIds must contain between 2 and 64 node IDs.');
            }
            if (strlen((string)$arguments['planToken']) !== 64) {
                return rpc_error($id, -32602, 'planToken must be a 64-character plan token.');
            }
            $consolidated = bridge_call(
                $bridgePath,
                $aurumRoot,
                $treePath,
                $eventsPath,
                $projectionPath,
                [
                    'command' => 'consolidate_branch',
                    'source_node_ids' => array_values($arguments['sourceNodeIds']),
                    'plan_token' => (string)$arguments['planToken'],
                    'new_node_id' => (string)$arguments['newNodeId'],
                    'title' => (string)$arguments['title'],
                    'summary' => (string)($arguments['summary'] ?? ''),
                ]
            );
            $data = snapshot(
                $bridgePath,
                $aurumRoot,
                $treePath,
                $eventsPath,
                $projectionPath,
                (string)$consolidated['focus_id']
            );
            $data['consolidationResult'] = $consolidated;
            $archivedCount = count($consolidated['archived_source_ids'] ?? []);
            return [
                'jsonrpc' => '2.0',
                'id' => $id,
                'result' => [
                    'structuredContent' => $data,
                    'content' => [[
                        'type' => 'text',
                        'text' => 'Consolidated and archived ' . $archivedCount . ' Chat Tree nodes. ChatGPT conversation history was not changed.',
                    ]],
                ],
            ];
        }

        if ($name === 'dispatch_farmer_objective') {
            try {
                $dispatched = dispatch_farmer_objective($arguments, $farmerTokenPath);
            } catch (InvalidArgumentException $error) {
                return rpc_error($id, -32602, $error->getMessage());
            }
            $accepted = ($dispatched['status'] ?? null) === 'dispatch_accepted';
            return [
                'jsonrpc' => '2.0',
                'id' => $id,
                'result' => [
                    'structuredContent' => $dispatched,
                    'content' => [[
                        'type' => 'text',
                        'text' => $accepted
                            ? 'Aurum Farmer accepted the objective and will continue through GitHub executor and verifier receipts.'
                            : 'Aurum Farmer dispatch is machine-blocked; no human relay is required.',
                    ]],
                ],
            ];
        }

        return rpc_error($id, -32602, 'Unknown tool.');
    }

    return rpc_error($id, -32601, 'Method not found.');
}

$route = (string)($_GET['route'] ?? 'health');
if ($route !== 'mcp') {
    send_json([
        'ok' => true,
        'service' => 'aurum-chat-tree-plugin',
        'source_commit' => $sourceCommit,
        'mcp' => '/chat-tree/mcp',
        'canonical_state_sha256' => is_file($treePath) ? hash_file('sha256', $treePath) : null,
        'event_journal_sha256' => is_file($eventsPath) ? hash_file('sha256', $eventsPath) : null,
        'event_count' => is_file($eventsPath)
            ? count(file($eventsPath, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES))
            : 0,
        'tree_exists' => is_file($treePath),
        'events_exists' => is_file($eventsPath),
        'projection_exists' => is_file($projectionPath),
        'bridge_exists' => is_file($bridgePath),
        'widget_exists' => is_file($widgetPath),
        'farmer_dispatch_ready' => is_file($farmerTokenPath) && filesize($farmerTokenPath) > 0,
        'farmer_repository' => FARMER_REPOSITORY,
        'farmer_event_type' => FARMER_EVENT_TYPE,
    ]);
}

if (($_SERVER['REQUEST_METHOD'] ?? 'GET') !== 'POST') {
    header('Allow: POST, OPTIONS');
    send_json(rpc_error(null, -32600, 'Use POST for MCP JSON-RPC requests.'), 405);
}

try {
    $raw = file_get_contents('php://input');
    $payload = json_decode($raw ?: '', true, 512, JSON_THROW_ON_ERROR);
    if (!is_array($payload)) {
        send_json(rpc_error(null, -32600, 'Invalid Request'), 400);
    }

    if (array_is_list($payload)) {
        $responses = [];
        foreach ($payload as $message) {
            if (!is_array($message)) {
                $responses[] = rpc_error(null, -32600, 'Invalid Request');
                continue;
            }
            $response = handle_rpc(
                $message,
                $bridgePath,
                $aurumRoot,
                $treePath,
                $eventsPath,
                $projectionPath,
                $widgetPath,
                $farmerTokenPath
            );
            if ($response !== null) {
                $responses[] = $response;
            }
        }
        if (!$responses) {
            http_response_code(202);
            exit;
        }
        send_json($responses);
    }

    $response = handle_rpc(
        $payload,
        $bridgePath,
        $aurumRoot,
        $treePath,
        $eventsPath,
        $projectionPath,
        $widgetPath,
        $farmerTokenPath
    );
    if ($response === null) {
        http_response_code(202);
        exit;
    }
    send_json($response);
} catch (JsonException $error) {
    send_json(rpc_error(null, -32700, 'Parse error.'), 400);
} catch (Throwable $error) {
    error_log('Aurum Chat Tree MCP: ' . $error->getMessage());
    send_json(rpc_error($payload['id'] ?? null, -32603, 'Internal error.'), 500);
}
