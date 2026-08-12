<?php
declare(strict_types=1);

const NODE_NAME = 'Aurum-Arkmatx';
const SCHEMA = 'aurum.uaf.v0';
const MAX_BODY = 65536;

$stateDir = __DIR__ . '/state';
$inboxDir = $stateDir . '/inbox';
$outboxDir = $stateDir . '/outbox';
foreach ([$stateDir, $inboxDir, $outboxDir] as $d) {
    if (!is_dir($d)) { @mkdir($d, 0700, true); }
}

function respond(int $code, array $body): never {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($body, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
    exit;
}

function status_payload(): array {
    global $inboxDir, $outboxDir;
    $merged = glob($inboxDir . '/*.merged.json') ?: [];
    $rejected = glob($inboxDir . '/*.rejected.json') ?: [];
    $outbox = glob($outboxDir . '/*.json') ?: [];
    return [
        'node' => NODE_NAME,
        'status' => 'active-edge-web-node',
        'schema' => SCHEMA,
        'carrier' => 'https',
        'capabilities' => ['uaf_receive','uaf_store','uaf_emit','human_projection','content_addressed_state'],
        'events' => ['merged'=>count($merged),'rejected'=>count($rejected),'outbox'=>count($outbox)]
    ];
}

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$path = parse_url($_SERVER['REQUEST_URI'] ?? '/', PHP_URL_PATH) ?: '/';

if ($method === 'GET' && ($path === '/' || str_ends_with($path, '/index.php') || str_ends_with($path, '/status'))) {
    respond(200, status_payload());
}
if ($method !== 'POST' || !str_ends_with($path, '/uaf')) {
    respond(404, ['error'=>'not-found']);
}

$length = (int)($_SERVER['CONTENT_LENGTH'] ?? 0);
if ($length <= 0 || $length > MAX_BODY) respond(413, ['error'=>'body-size']);
$raw = file_get_contents('php://input', false, null, 0, MAX_BODY + 1);
if ($raw === false || strlen($raw) > MAX_BODY) respond(413, ['error'=>'body-size']);
$frame = json_decode($raw, true);
if (!is_array($frame)) respond(400, ['error'=>'invalid-json']);

$required = ['schema','frame_id','origin','target','intent','state_delta','provenance','verification'];
foreach ($required as $key) if (!array_key_exists($key, $frame)) respond(400, ['error'=>'missing-field','field'=>$key]);
if (($frame['schema'] ?? null) !== SCHEMA) respond(400, ['error'=>'schema']);
if (($frame['target'] ?? null) !== NODE_NAME && ($frame['target'] ?? null) !== '*') respond(409, ['error'=>'wrong-target']);
if (($frame['verification']['reversible'] ?? false) !== true) {
    $digest = hash('sha256', $raw);
    file_put_contents($inboxDir . '/' . $digest . '.rejected.json', $raw, LOCK_EX);
    respond(409, ['status'=>'rejected','reason'=>'non-reversible']);
}
if (!isset($frame['provenance']['node']) || $frame['provenance']['node'] === '') respond(400, ['error'=>'provenance']);

$digest = hash('sha256', $raw);
$file = $inboxDir . '/' . $digest . '.merged.json';
if (!file_exists($file)) file_put_contents($file, $raw, LOCK_EX);

$receipt = [
    'schema'=>SCHEMA,
    'frame_id'=>bin2hex(random_bytes(16)),
    'origin'=>NODE_NAME,
    'target'=>(string)$frame['origin'],
    'intent'=>'receipt',
    'state_delta'=>['received_frame'=>(string)$frame['frame_id'],'sha256'=>$digest,'status'=>'merged'],
    'provenance'=>['node'=>NODE_NAME,'created'=>time()],
    'verification'=>['content_addressed'=>true,'reversible'=>true]
];
file_put_contents($outboxDir . '/' . hash('sha256', json_encode($receipt)) . '.json', json_encode($receipt, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT), LOCK_EX);
respond(202, ['status'=>'merged','node'=>NODE_NAME,'sha256'=>$digest,'receipt'=>$receipt]);
