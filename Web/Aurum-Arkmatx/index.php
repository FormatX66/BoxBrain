<?php
const NODE_NAME = 'Aurum-Arkmatx';
const SCHEMA = 'aurum.uaf.v0';
const MAX_BODY = 65536;

$stateDir = __DIR__ . '/state';
$inboxDir = $stateDir . '/inbox';
$outboxDir = $stateDir . '/outbox';
foreach (array($stateDir, $inboxDir, $outboxDir) as $d) {
    if (!is_dir($d)) { @mkdir($d, 0700, true); }
}

function ends_with($value, $suffix) {
    if ($suffix === '') return true;
    return substr($value, -strlen($suffix)) === $suffix;
}

function respond_json($code, $body) {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($body, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
    exit;
}

function status_payload() {
    global $inboxDir, $outboxDir;
    $merged = glob($inboxDir . '/*.merged.json'); if ($merged === false) $merged = array();
    $rejected = glob($inboxDir . '/*.rejected.json'); if ($rejected === false) $rejected = array();
    $outbox = glob($outboxDir . '/*.json'); if ($outbox === false) $outbox = array();
    return array(
        'node' => NODE_NAME,
        'status' => 'active-edge-web-node',
        'schema' => SCHEMA,
        'carrier' => 'https',
        'capabilities' => array('uaf_receive','uaf_store','uaf_emit','human_projection','content_addressed_state'),
        'events' => array('merged'=>count($merged),'rejected'=>count($rejected),'outbox'=>count($outbox))
    );
}

$method = isset($_SERVER['REQUEST_METHOD']) ? $_SERVER['REQUEST_METHOD'] : 'GET';
$requestUri = isset($_SERVER['REQUEST_URI']) ? $_SERVER['REQUEST_URI'] : '/';
$path = parse_url($requestUri, PHP_URL_PATH); if (!$path) $path = '/';

if ($method === 'GET' && ($path === '/' || ends_with($path, '/index.php') || ends_with($path, '/status'))) {
    respond_json(200, status_payload());
}
if ($method !== 'POST' || !ends_with($path, '/uaf')) {
    respond_json(404, array('error'=>'not-found'));
}

$length = isset($_SERVER['CONTENT_LENGTH']) ? (int)$_SERVER['CONTENT_LENGTH'] : 0;
if ($length <= 0 || $length > MAX_BODY) respond_json(413, array('error'=>'body-size'));
$raw = file_get_contents('php://input');
if ($raw === false || strlen($raw) > MAX_BODY) respond_json(413, array('error'=>'body-size'));
$frame = json_decode($raw, true);
if (!is_array($frame)) respond_json(400, array('error'=>'invalid-json'));

$required = array('schema','frame_id','origin','target','intent','state_delta','provenance','verification');
foreach ($required as $key) {
    if (!array_key_exists($key, $frame)) respond_json(400, array('error'=>'missing-field','field'=>$key));
}
if ($frame['schema'] !== SCHEMA) respond_json(400, array('error'=>'schema'));
if ($frame['target'] !== NODE_NAME && $frame['target'] !== '*') respond_json(409, array('error'=>'wrong-target'));
if (!isset($frame['verification']['reversible']) || $frame['verification']['reversible'] !== true) {
    $digest = hash('sha256', $raw);
    @file_put_contents($inboxDir . '/' . $digest . '.rejected.json', $raw, LOCK_EX);
    respond_json(409, array('status'=>'rejected','reason'=>'non-reversible'));
}
if (!isset($frame['provenance']['node']) || $frame['provenance']['node'] === '') respond_json(400, array('error'=>'provenance'));

$digest = hash('sha256', $raw);
$file = $inboxDir . '/' . $digest . '.merged.json';
if (!file_exists($file)) @file_put_contents($file, $raw, LOCK_EX);

$receipt = array(
    'schema'=>SCHEMA,
    'frame_id'=>bin2hex(random_bytes(16)),
    'origin'=>NODE_NAME,
    'target'=>(string)$frame['origin'],
    'intent'=>'receipt',
    'state_delta'=>array('received_frame'=>(string)$frame['frame_id'],'sha256'=>$digest,'status'=>'merged'),
    'provenance'=>array('node'=>NODE_NAME,'created'=>time()),
    'verification'=>array('content_addressed'=>true,'reversible'=>true)
);
@file_put_contents($outboxDir . '/' . hash('sha256', json_encode($receipt)) . '.json', json_encode($receipt, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT), LOCK_EX);
respond_json(202, array('status'=>'merged','node'=>NODE_NAME,'sha256'=>$digest,'receipt'=>$receipt));
