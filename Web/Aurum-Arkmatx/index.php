<?php
const NODE_NAME = 'Aurum-Arkmatx';
const SCHEMA = 'aurum.uaf.v0';
const MAX_BODY = 65536;

$stateDir = __DIR__ . '/state';
$inboxDir = $stateDir . '/inbox';
$outboxDir = $stateDir . '/outbox';
$nodesDir = $stateDir . '/nodes';
$conversationsDir = $stateDir . '/conversations';
foreach (array($stateDir, $inboxDir, $outboxDir, $nodesDir, $conversationsDir) as $d) {
    if (!is_dir($d)) { @mkdir($d, 0700, true); }
}

function ends_with($value, $suffix) {
    if ($suffix === '') return true;
    return substr($value, -strlen($suffix)) === $suffix;
}
function clean_id($value, $max = 64) {
    $v = preg_replace('/[^A-Za-z0-9._-]/', '', (string)$value);
    return substr($v, 0, $max);
}
function respond_json($code, $body) {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($body, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
    exit;
}
function append_conversation_event($conversationId, $type, $payload) {
    global $conversationsDir;
    $id = clean_id($conversationId);
    if ($id === '') return false;
    $path = $conversationsDir . '/' . $id . '.jsonl';
    $event = array(
        'event_id'=>bin2hex(random_bytes(12)),
        'conversation_id'=>$id,
        'type'=>(string)$type,
        'created'=>time(),
        'payload'=>$payload
    );
    return @file_put_contents($path, json_encode($event, JSON_UNESCAPED_SLASHES) . "\n", FILE_APPEND | LOCK_EX) !== false;
}
function read_conversation_events($conversationId, $after = 0, $limit = 100) {
    global $conversationsDir;
    $id = clean_id($conversationId);
    if ($id === '') return array();
    $path = $conversationsDir . '/' . $id . '.jsonl';
    if (!is_file($path)) return array();
    $lines = @file($path, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    if (!is_array($lines)) return array();
    $out = array();
    $index = 0;
    foreach ($lines as $line) {
        if ($index++ < $after) continue;
        $row = json_decode($line, true);
        if (is_array($row)) {
            $row['cursor'] = $index;
            $out[] = $row;
            if (count($out) >= $limit) break;
        }
    }
    return $out;
}
function list_nodes() {
    global $nodesDir;
    $files = glob($nodesDir . '/*.json'); if ($files === false) $files = array();
    $nodes = array();
    foreach ($files as $path) {
        $d = json_decode((string)@file_get_contents($path), true);
        if (is_array($d)) $nodes[] = $d;
    }
    usort($nodes, function($a,$b){ return ((int)($b['last_seen'] ?? 0)) <=> ((int)($a['last_seen'] ?? 0)); });
    return $nodes;
}
function status_payload() {
    global $inboxDir, $outboxDir, $nodesDir;
    $merged = glob($inboxDir . '/*.merged.json'); if ($merged === false) $merged = array();
    $rejected = glob($inboxDir . '/*.rejected.json'); if ($rejected === false) $rejected = array();
    $outbox = glob($outboxDir . '/*.json'); if ($outbox === false) $outbox = array();
    $nodes = glob($nodesDir . '/*.json'); if ($nodes === false) $nodes = array();
    return array(
        'node' => NODE_NAME,
        'status' => 'active-edge-web-node',
        'schema' => SCHEMA,
        'carrier' => 'https',
        'portal' => 'https://aurum.arkmatx.com/',
        'capabilities' => array('uaf_receive','uaf_store','uaf_emit','human_projection','content_addressed_state','node_enroll','node_heartbeat','prompt_ingest','conversation_stream','node_directory'),
        'events' => array('merged'=>count($merged),'rejected'=>count($rejected),'outbox'=>count($outbox),'nodes'=>count($nodes))
    );
}

$method = isset($_SERVER['REQUEST_METHOD']) ? $_SERVER['REQUEST_METHOD'] : 'GET';
$requestUri = isset($_SERVER['REQUEST_URI']) ? $_SERVER['REQUEST_URI'] : '/';
$path = parse_url($requestUri, PHP_URL_PATH); if (!$path) $path = '/';
$host = isset($_SERVER['HTTP_HOST']) ? strtolower(preg_replace('/:\\d+$/', '', $_SERVER['HTTP_HOST'])) : '';
$isPortalHost = ($host === 'aurum.arkmatx.com');

if ($method === 'GET' && $isPortalHost && ($path === '/' || ends_with($path, '/index.php'))) {
    $portal = __DIR__ . '/portal.html';
    if (!is_file($portal)) respond_json(503, array('error'=>'portal-unavailable'));
    header('Content-Type: text/html; charset=utf-8');
    header('Cache-Control: no-store');
    readfile($portal);
    exit;
}
if ($method === 'GET' && ($path === '/status' || ends_with($path, '/status') || (!$isPortalHost && ($path === '/' || ends_with($path, '/index.php'))))) {
    respond_json(200, status_payload());
}
if ($method === 'GET' && ($path === '/nodes' || ends_with($path, '/nodes'))) {
    respond_json(200, array('nodes'=>list_nodes(),'controller'=>NODE_NAME,'time'=>time()));
}
if ($method === 'GET' && ($path === '/events' || ends_with($path, '/events'))) {
    $conversation = isset($_GET['conversation']) ? clean_id($_GET['conversation']) : '';
    $after = isset($_GET['after']) ? max(0, (int)$_GET['after']) : 0;
    if ($conversation === '') respond_json(400, array('error'=>'conversation-required'));
    $events = read_conversation_events($conversation, $after, 100);
    $cursor = $after;
    if (count($events)) $cursor = (int)$events[count($events)-1]['cursor'];
    respond_json(200, array('conversation_id'=>$conversation,'cursor'=>$cursor,'events'=>$events));
}

$uafPost = ($method === 'POST') && (ends_with($path, '/uaf') || ends_with($path, '/index.php') || ends_with($path, '/enroll'));
if (!$uafPost) respond_json(404, array('error'=>'not-found'));

$length = isset($_SERVER['CONTENT_LENGTH']) ? (int)$_SERVER['CONTENT_LENGTH'] : 0;
if ($length <= 0 || $length > MAX_BODY) respond_json(413, array('error'=>'body-size'));
$raw = file_get_contents('php://input');
if ($raw === false || strlen($raw) > MAX_BODY) respond_json(413, array('error'=>'body-size'));
$frame = json_decode($raw, true);
if (!is_array($frame)) respond_json(400, array('error'=>'invalid-json'));

$required = array('schema','frame_id','origin','target','intent','state_delta','provenance','verification');
foreach ($required as $key) if (!array_key_exists($key, $frame)) respond_json(400, array('error'=>'missing-field','field'=>$key));
if ($frame['schema'] !== SCHEMA) respond_json(400, array('error'=>'schema'));
if ($frame['target'] !== NODE_NAME && $frame['target'] !== '*') respond_json(409, array('error'=>'wrong-target'));
if (ends_with($path, '/enroll') && $frame['intent'] !== 'node_enroll') respond_json(409, array('error'=>'enroll-intent-required'));
if (!isset($frame['verification']['reversible']) || $frame['verification']['reversible'] !== true) {
    $digest = hash('sha256', $raw);
    @file_put_contents($inboxDir . '/' . $digest . '.rejected.json', $raw, LOCK_EX);
    respond_json(409, array('status'=>'rejected','reason'=>'non-reversible'));
}
if (!isset($frame['provenance']['node']) || $frame['provenance']['node'] === '') respond_json(400, array('error'=>'provenance'));

$digest = hash('sha256', $raw);
$file = $inboxDir . '/' . $digest . '.merged.json';
if (!file_exists($file)) @file_put_contents($file, $raw, LOCK_EX);

if ($frame['intent'] === 'node_enroll' || $frame['intent'] === 'node_heartbeat') {
    $delta = is_array($frame['state_delta']) ? $frame['state_delta'] : array();
    $nodeId = isset($delta['node_id']) ? clean_id($delta['node_id']) : '';
    if ($nodeId === '') respond_json(400, array('error'=>'node-id'));
    $nodePath = $nodesDir . '/' . $nodeId . '.json';
    $existing = null;
    if (is_file($nodePath)) { $existing = json_decode((string)@file_get_contents($nodePath), true); if (!is_array($existing)) $existing = null; }
    if ($frame['intent'] === 'node_heartbeat' && $existing === null) respond_json(409, array('status'=>'rejected','reason'=>'node-not-enrolled','node_id'=>$nodeId));
    $now = time();
    if ($frame['intent'] === 'node_enroll') {
        $record = array(
            'schema'=>'aurum.node.v0','node_id'=>$nodeId,
            'name'=>isset($delta['name']) ? substr((string)$delta['name'],0,128) : $nodeId,
            'os'=>isset($delta['os']) ? substr((string)$delta['os'],0,128) : 'unknown',
            'arch'=>isset($delta['arch']) ? substr((string)$delta['arch'],0,64) : 'unknown',
            'carrier'=>isset($delta['carrier']) ? substr((string)$delta['carrier'],0,64) : 'https-outbound',
            'status'=>'online','first_seen'=>($existing && isset($existing['first_seen'])) ? (int)$existing['first_seen'] : $now,
            'last_seen'=>$now,'controller'=>NODE_NAME,'frame_sha256'=>$digest
        );
    } else {
        $record = $existing; $record['last_seen']=$now; $record['status']='online'; $record['frame_sha256']=$digest;
        if (isset($delta['carrier'])) $record['carrier']=substr((string)$delta['carrier'],0,64);
        if (isset($delta['addresses']) && is_array($delta['addresses'])) $record['addresses']=array_slice(array_map('strval',$delta['addresses']),0,8);
    }
    @file_put_contents($nodePath, json_encode($record, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT), LOCK_EX);
}

if ($frame['intent'] === 'user_prompt') {
    $delta = is_array($frame['state_delta']) ? $frame['state_delta'] : array();
    $conversation = isset($delta['conversation_id']) ? clean_id($delta['conversation_id']) : '';
    $prompt = isset($delta['prompt']) ? trim((string)$delta['prompt']) : '';
    if ($conversation === '' || $prompt === '') respond_json(400, array('error'=>'prompt-fields'));
    if (strlen($prompt) > 4000) respond_json(413, array('error'=>'prompt-size'));
    append_conversation_event($conversation, 'user.message', array('text'=>$prompt,'frame_id'=>(string)$frame['frame_id']));
    append_conversation_event($conversation, 'aurum.accepted', array('status'=>'queued','frame_sha256'=>$digest));
}
if (in_array($frame['intent'], array('assistant_delta','assistant_message','tool_event','node_event'), true)) {
    $delta = is_array($frame['state_delta']) ? $frame['state_delta'] : array();
    $conversation = isset($delta['conversation_id']) ? clean_id($delta['conversation_id']) : '';
    if ($conversation !== '') append_conversation_event($conversation, $frame['intent'], $delta);
}

$receipt = array(
    'schema'=>SCHEMA,'frame_id'=>bin2hex(random_bytes(16)),'origin'=>NODE_NAME,'target'=>(string)$frame['origin'],'intent'=>'receipt',
    'state_delta'=>array('received_frame'=>(string)$frame['frame_id'],'sha256'=>$digest,'status'=>'merged','intent'=>(string)$frame['intent']),
    'provenance'=>array('node'=>NODE_NAME,'created'=>time()),'verification'=>array('content_addressed'=>true,'reversible'=>true)
);
@file_put_contents($outboxDir . '/' . hash('sha256', json_encode($receipt)) . '.json', json_encode($receipt, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT), LOCK_EX);
respond_json(202, array('status'=>'merged','node'=>NODE_NAME,'sha256'=>$digest,'receipt'=>$receipt));
