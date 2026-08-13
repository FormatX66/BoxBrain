<?php
const NODE_NAME = 'Aurum-Arkmatx';
const SCHEMA = 'aurum.uaf.v0';
const MAX_BODY = 65536;

$stateDir = __DIR__ . '/state';
$inboxDir = $stateDir . '/inbox';
$outboxDir = $stateDir . '/outbox';
$nodesDir = $stateDir . '/nodes';
$conversationsDir = $stateDir . '/conversations';
$workDir = $stateDir . '/work';
foreach (array($stateDir, $inboxDir, $outboxDir, $nodesDir, $conversationsDir, $workDir) as $d) {
    if (!is_dir($d)) {
        @mkdir($d, 0700, true);
    }
}

function ends_with($v, $s) {
    if ($s === '') return true;
    return substr($v, -strlen($s)) === $s;
}

function clean_id($v, $m = 64) {
    return substr(preg_replace('/[^A-Za-z0-9._-]/', '', (string)$v), 0, $m);
}

function respond_json($c, $b) {
    http_response_code($c);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($b, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
    exit;
}

function read_body() {
    $l = isset($_SERVER['CONTENT_LENGTH']) ? (int)$_SERVER['CONTENT_LENGTH'] : 0;
    if ($l <= 0 || $l > MAX_BODY) respond_json(413, array('error' => 'body-size'));
    $r = file_get_contents('php://input');
    if ($r === false || strlen($r) > MAX_BODY) respond_json(413, array('error' => 'body-size'));
    $j = json_decode($r, true);
    if (!is_array($j)) respond_json(400, array('error' => 'invalid-json'));
    return array($r, $j);
}

function append_conversation_event($id, $type, $payload) {
    global $conversationsDir;
    $id = clean_id($id);
    if ($id === '') return false;
    $event = array(
        'event_id' => bin2hex(random_bytes(12)),
        'conversation_id' => $id,
        'type' => (string)$type,
        'created' => time(),
        'payload' => $payload,
    );
    return @file_put_contents(
        $conversationsDir . '/' . $id . '.jsonl',
        json_encode($event, JSON_UNESCAPED_SLASHES) . "\n",
        FILE_APPEND | LOCK_EX
    ) !== false;
}

function read_conversation_events($id, $after = 0, $limit = 100) {
    global $conversationsDir;
    $id = clean_id($id);
    $p = $conversationsDir . '/' . $id . '.jsonl';
    if ($id === '' || !is_file($p)) return array();
    $lines = @file($p, FILE_IGNORE_NEW_LINES | FILE_SKIP_EMPTY_LINES);
    if (!is_array($lines)) return array();
    $o = array();
    $i = 0;
    foreach ($lines as $line) {
        if ($i++ < $after) continue;
        $r = json_decode($line, true);
        if (is_array($r)) {
            $r['cursor'] = $i;
            $o[] = $r;
            if (count($o) >= $limit) break;
        }
    }
    return $o;
}

function list_nodes() {
    global $nodesDir;
    $fs = glob($nodesDir . '/*.json');
    if ($fs === false) $fs = array();
    $o = array();
    foreach ($fs as $p) {
        $d = json_decode((string)@file_get_contents($p), true);
        if (is_array($d)) $o[] = $d;
    }
    usort($o, function ($a, $b) {
        return ((int)($b['last_seen'] ?? 0)) <=> ((int)($a['last_seen'] ?? 0));
    });
    return $o;
}

function write_work_if_missing($work) {
    global $workDir;
    $id = clean_id($work['work_id'] ?? '');
    if ($id === '') return;
    $p = $workDir . '/' . $id . '.json';
    if (is_file($p)) return;
    @file_put_contents(
        $p,
        json_encode($work, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT),
        LOCK_EX
    );
}

function seed_bbpi4_work() {
    write_work_if_missing(array(
        'schema' => 'aurum.work.v0',
        'work_id' => 'bbpi4-bootstrap-v1',
        'capability' => 'bbpi4-bootstrap',
        'target_node_id' => '825e5a7b7d4a7aed',
        'priority' => 100,
        'status' => 'queued',
        'created' => time(),
        'lease' => null,
        'attempts' => 0,
        'payload' => array(
            'target' => 'BBPI4',
            'desired_state' => 'enrolled-heartbeating',
            'addresses' => array('10.12.194.1', '10.42.194.1', 'bbpi4.local', '192.168.0.194'),
        ),
        'verification' => array(
            'reversible' => true,
            'fresh_bbpi4_heartbeat_required' => true,
        ),
    ));
}

function seed_bbpi4_ap_probe_work() {
    $targets = array(
        'bbpi4-ap-probe-morris-v1' => '825e5a7b7d4a7aed',
        'bbpi4-ap-probe-bruce-v1' => '85404f41d5507372',
    );
    foreach ($targets as $workId => $nodeId) {
        write_work_if_missing(array(
            'schema' => 'aurum.work.v0',
            'work_id' => $workId,
            'capability' => 'connectivity-observation',
            'target_node_id' => $nodeId,
            'priority' => 110,
            'status' => 'queued',
            'created' => time(),
            'lease' => null,
            'attempts' => 0,
            'payload' => array(
                'target' => 'BBPI4-AP',
                'addresses' => array('10.42.194.1'),
                'ports' => array(22),
            ),
            'verification' => array(
                'reversible' => true,
                'connect_only' => true,
                'private_target_only' => true,
            ),
        ));
    }
}

function work_probe_status($id) {
    global $workDir;
    $id = clean_id($id);
    if ($id === '') respond_json(400, array('error' => 'work-id'));
    $p = $workDir . '/' . $id . '.json';
    if (!is_file($p)) respond_json(404, array('error' => 'work-not-found'));
    $w = json_decode((string)@file_get_contents($p), true);
    if (!is_array($w)) respond_json(409, array('error' => 'work-state'));

    $last = is_array($w['last_result'] ?? null) ? $w['last_result'] : null;
    $detail = ($last && is_array($last['detail'] ?? null)) ? $last['detail'] : array();
    $open = is_array($detail['open'] ?? null) ? $detail['open'] : array();
    $apSshOpen = false;
    foreach ($open as $entry) {
        if (!is_array($entry)) continue;
        if (($entry['address'] ?? '') === '10.42.194.1' && (int)($entry['port'] ?? 0) === 22) {
            $apSshOpen = true;
            break;
        }
    }

    return array(
        'work_id' => (string)($w['work_id'] ?? $id),
        'target_node_id' => (string)($w['target_node_id'] ?? ''),
        'capability' => (string)($w['capability'] ?? ''),
        'status' => (string)($w['status'] ?? ''),
        'attempts' => (int)($w['attempts'] ?? 0),
        'ap_ssh_open' => $apSshOpen,
        'last_result_status' => $last ? (string)($last['status'] ?? '') : null,
        'completed_at' => $last ? (int)($last['completed_at'] ?? 0) : null,
    );
}

function status_payload() {
    global $inboxDir, $outboxDir, $nodesDir, $workDir;
    $m = glob($inboxDir . '/*.merged.json');
    if ($m === false) $m = array();
    $r = glob($inboxDir . '/*.rejected.json');
    if ($r === false) $r = array();
    $o = glob($outboxDir . '/*.json');
    if ($o === false) $o = array();
    $n = glob($nodesDir . '/*.json');
    if ($n === false) $n = array();
    $w = glob($workDir . '/*.json');
    if ($w === false) $w = array();
    return array(
        'node' => NODE_NAME,
        'status' => 'active-edge-web-node',
        'schema' => SCHEMA,
        'carrier' => 'https',
        'portal' => 'https://aurum.arkmatx.com/',
        'capabilities' => array(
            'uaf_receive', 'uaf_store', 'uaf_emit', 'human_projection',
            'content_addressed_state', 'node_enroll', 'node_heartbeat',
            'prompt_ingest', 'conversation_stream', 'node_directory',
            'work_lease', 'work_result', 'work_status',
        ),
        'events' => array(
            'merged' => count($m),
            'rejected' => count($r),
            'outbox' => count($o),
            'nodes' => count($n),
            'work' => count($w),
        ),
    );
}

seed_bbpi4_work();
seed_bbpi4_ap_probe_work();

$method = $_SERVER['REQUEST_METHOD'] ?? 'GET';
$requestUri = $_SERVER['REQUEST_URI'] ?? '/';
$path = parse_url($requestUri, PHP_URL_PATH);
if (!$path) $path = '/';
$host = isset($_SERVER['HTTP_HOST']) ? strtolower(preg_replace('/:\\d+$/', '', $_SERVER['HTTP_HOST'])) : '';
$isPortalHost = ($host === 'aurum.arkmatx.com');

if ($method === 'GET' && $isPortalHost && ($path === '/' || ends_with($path, '/index.php'))) {
    $portal = __DIR__ . '/portal.html';
    if (!is_file($portal)) respond_json(503, array('error' => 'portal-unavailable'));
    header('Content-Type: text/html; charset=utf-8');
    header('Cache-Control: no-store');
    readfile($portal);
    exit;
}

if ($method === 'GET' && ($path === '/status' || ends_with($path, '/status') || (!$isPortalHost && ($path === '/' || ends_with($path, '/index.php'))))) {
    respond_json(200, status_payload());
}

if ($method === 'GET' && ($path === '/nodes' || ends_with($path, '/nodes'))) {
    respond_json(200, array('nodes' => list_nodes(), 'controller' => NODE_NAME, 'time' => time()));
}

if ($method === 'GET' && ends_with($path, '/work/status')) {
    $id = isset($_GET['id']) ? clean_id($_GET['id']) : '';
    respond_json(200, work_probe_status($id));
}

if ($method === 'GET' && ($path === '/events' || ends_with($path, '/events'))) {
    $c = isset($_GET['conversation']) ? clean_id($_GET['conversation']) : '';
    $a = isset($_GET['after']) ? max(0, (int)$_GET['after']) : 0;
    if ($c === '') respond_json(400, array('error' => 'conversation-required'));
    $e = read_conversation_events($c, $a, 100);
    $cursor = $a;
    if (count($e)) $cursor = (int)$e[count($e) - 1]['cursor'];
    respond_json(200, array('conversation_id' => $c, 'cursor' => $cursor, 'events' => $e));
}

if ($method === 'GET' && ends_with($path, '/work/lease')) {
    global $workDir;
    $node = isset($_GET['node_id']) ? clean_id($_GET['node_id']) : '';
    $caps = isset($_GET['capabilities'])
        ? array_filter(array_map('trim', explode(',', (string)$_GET['capabilities'])))
        : array();
    if ($node === '') respond_json(400, array('error' => 'node-id'));
    $now = time();
    $files = glob($workDir . '/*.json');
    if ($files === false) $files = array();
    foreach ($files as $p) {
        $w = json_decode((string)@file_get_contents($p), true);
        if (!is_array($w)) continue;
        if (($w['target_node_id'] ?? '') !== $node) continue;
        if (!in_array($w['capability'] ?? '', $caps, true)) continue;
        $lease = $w['lease'] ?? null;
        if (($w['status'] ?? '') === 'completed') continue;
        if (($w['status'] ?? '') === 'leased' && is_array($lease) && ($lease['expires'] ?? 0) > $now) continue;
        $w['status'] = 'leased';
        $w['attempts'] = (int)($w['attempts'] ?? 0) + 1;
        $w['lease'] = array('node_id' => $node, 'leased_at' => $now, 'expires' => $now + 120);
        @file_put_contents($p, json_encode($w, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT), LOCK_EX);
        respond_json(200, array('work' => $w, 'controller' => NODE_NAME, 'time' => $now));
    }
    respond_json(200, array('work' => null, 'controller' => NODE_NAME, 'time' => $now));
}

if ($method === 'POST' && ends_with($path, '/work/result')) {
    global $workDir;
    list($raw, $j) = read_body();
    $node = clean_id($j['node_id'] ?? '');
    $wid = clean_id($j['work_id'] ?? '');
    $status = (string)($j['status'] ?? '');
    $p = $workDir . '/' . $wid . '.json';
    if ($node === '' || $wid === '' || !is_file($p)) respond_json(400, array('error' => 'work-result-fields'));
    $w = json_decode((string)@file_get_contents($p), true);
    if (!is_array($w)) respond_json(409, array('error' => 'work-state'));
    $lease = $w['lease'] ?? array();
    if (($w['target_node_id'] ?? '') !== $node || ($lease['node_id'] ?? '') !== $node) {
        respond_json(409, array('error' => 'work-owner'));
    }
    $w['last_result'] = array(
        'status' => $status,
        'detail' => $j['detail'] ?? null,
        'completed_at' => (int)($j['completed_at'] ?? time()),
    );
    $w['lease'] = null;
    $w['status'] = ($status === 'completed') ? 'completed' : 'queued';
    @file_put_contents($p, json_encode($w, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT), LOCK_EX);
    respond_json(202, array('status' => 'recorded', 'work_id' => $wid, 'work_status' => $w['status']));
}

$uafPost = ($method === 'POST') && (ends_with($path, '/uaf') || ends_with($path, '/index.php') || ends_with($path, '/enroll'));
if (!$uafPost) respond_json(404, array('error' => 'not-found'));

list($raw, $frame) = read_body();
$required = array('schema', 'frame_id', 'origin', 'target', 'intent', 'state_delta', 'provenance', 'verification');
foreach ($required as $k) {
    if (!array_key_exists($k, $frame)) respond_json(400, array('error' => 'missing-field', 'field' => $k));
}
if ($frame['schema'] !== SCHEMA) respond_json(400, array('error' => 'schema'));
if ($frame['target'] !== NODE_NAME && $frame['target'] !== '*') respond_json(409, array('error' => 'wrong-target'));
if (ends_with($path, '/enroll') && $frame['intent'] !== 'node_enroll') respond_json(409, array('error' => 'enroll-intent-required'));
if (!isset($frame['verification']['reversible']) || $frame['verification']['reversible'] !== true) {
    $digest = hash('sha256', $raw);
    @file_put_contents($inboxDir . '/' . $digest . '.rejected.json', $raw, LOCK_EX);
    respond_json(409, array('status' => 'rejected', 'reason' => 'non-reversible'));
}
if (!isset($frame['provenance']['node']) || $frame['provenance']['node'] === '') {
    respond_json(400, array('error' => 'provenance'));
}

$digest = hash('sha256', $raw);
$file = $inboxDir . '/' . $digest . '.merged.json';
if (!file_exists($file)) @file_put_contents($file, $raw, LOCK_EX);

if ($frame['intent'] === 'node_enroll' || $frame['intent'] === 'node_heartbeat') {
    $d = is_array($frame['state_delta']) ? $frame['state_delta'] : array();
    $nodeId = clean_id($d['node_id'] ?? '');
    if ($nodeId === '') respond_json(400, array('error' => 'node-id'));
    $nodePath = $nodesDir . '/' . $nodeId . '.json';
    $existing = null;
    if (is_file($nodePath)) {
        $existing = json_decode((string)@file_get_contents($nodePath), true);
        if (!is_array($existing)) $existing = null;
    }
    if ($frame['intent'] === 'node_heartbeat' && $existing === null) {
        respond_json(409, array('status' => 'rejected', 'reason' => 'node-not-enrolled', 'node_id' => $nodeId));
    }
    $now = time();
    if ($frame['intent'] === 'node_enroll') {
        $record = array(
            'schema' => 'aurum.node.v0',
            'node_id' => $nodeId,
            'name' => isset($d['name']) ? substr((string)$d['name'], 0, 128) : $nodeId,
            'os' => isset($d['os']) ? substr((string)$d['os'], 0, 128) : 'unknown',
            'arch' => isset($d['arch']) ? substr((string)$d['arch'], 0, 64) : 'unknown',
            'carrier' => isset($d['carrier']) ? substr((string)$d['carrier'], 0, 64) : 'https-outbound',
            'status' => 'online',
            'first_seen' => ($existing && isset($existing['first_seen'])) ? (int)$existing['first_seen'] : $now,
            'last_seen' => $now,
            'controller' => NODE_NAME,
            'frame_sha256' => $digest,
        );
    } else {
        $record = $existing;
        $record['last_seen'] = $now;
        $record['status'] = 'online';
        $record['frame_sha256'] = $digest;
        if (isset($d['carrier'])) $record['carrier'] = substr((string)$d['carrier'], 0, 64);
        if (isset($d['addresses']) && is_array($d['addresses'])) {
            $record['addresses'] = array_slice(array_map('strval', $d['addresses']), 0, 8);
        }
    }
    @file_put_contents($nodePath, json_encode($record, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT), LOCK_EX);
}

if ($frame['intent'] === 'user_prompt') {
    $d = is_array($frame['state_delta']) ? $frame['state_delta'] : array();
    $c = clean_id($d['conversation_id'] ?? '');
    $p = trim((string)($d['prompt'] ?? ''));
    if ($c === '' || $p === '') respond_json(400, array('error' => 'prompt-fields'));
    if (strlen($p) > 4000) respond_json(413, array('error' => 'prompt-size'));
    append_conversation_event($c, 'user.message', array('text' => $p, 'frame_id' => (string)$frame['frame_id']));
    append_conversation_event($c, 'aurum.accepted', array('status' => 'queued', 'frame_sha256' => $digest));
}

if (in_array($frame['intent'], array('assistant_delta', 'assistant_message', 'tool_event', 'node_event'), true)) {
    $d = is_array($frame['state_delta']) ? $frame['state_delta'] : array();
    $c = clean_id($d['conversation_id'] ?? '');
    if ($c !== '') append_conversation_event($c, $frame['intent'], $d);
}

$receipt = array(
    'schema' => SCHEMA,
    'frame_id' => bin2hex(random_bytes(16)),
    'origin' => NODE_NAME,
    'target' => (string)$frame['origin'],
    'intent' => 'receipt',
    'state_delta' => array(
        'received_frame' => (string)$frame['frame_id'],
        'sha256' => $digest,
        'status' => 'merged',
        'intent' => (string)$frame['intent'],
    ),
    'provenance' => array('node' => NODE_NAME, 'created' => time()),
    'verification' => array('content_addressed' => true, 'reversible' => true),
);
@file_put_contents(
    $outboxDir . '/' . hash('sha256', json_encode($receipt)) . '.json',
    json_encode($receipt, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT),
    LOCK_EX
);
respond_json(202, array('status' => 'merged', 'node' => NODE_NAME, 'sha256' => $digest, 'receipt' => $receipt));
