<?php
declare(strict_types=1);

const TEMPLATE_URI = 'ui://aurum/chat-tree/v4.html';
const RESOURCE_MIME_TYPE = 'text/html;profile=mcp-app';

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
    $tree = $treeResponse['tree'];
    $focusPath = $tree['focus_path'] ?? [];
    $resolvedFocus = $focusPath ? $focusPath[count($focusPath) - 1] : ($tree['root_id'] ?? null);
    return ['tree' => $tree, 'state' => $stateResponse['state'], 'focusId' => $resolvedFocus];
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
            'description' => 'Use this when the user wants to view or organize current Aurum conversation/process branches.',
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
    ];
}

function handle_rpc(
    array $message,
    string $bridgePath,
    string $aurumRoot,
    string $treePath,
    string $eventsPath,
    string $projectionPath,
    string $widgetPath
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
                'serverInfo' => ['name' => 'aurum-chat-tree-plugin', 'version' => '0.1.0'],
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
                    'openai/widgetDescription' => 'Aurum Chat Tree navigator for focused, child, and sibling work lanes.',
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
                $widgetPath
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
        $widgetPath
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
