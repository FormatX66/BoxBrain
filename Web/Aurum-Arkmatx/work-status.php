<?php
const MAX_WORK_ID = 64;
$workDir = __DIR__ . '/state/work';

function respond_json($code, $body) {
    http_response_code($code);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    echo json_encode($body, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT);
    exit;
}

function clean_work_id($value) {
    return substr(preg_replace('/[^A-Za-z0-9._-]/', '', (string)$value), 0, MAX_WORK_ID);
}

$id = isset($_GET['id']) ? clean_work_id($_GET['id']) : '';
if ($id === '') respond_json(400, array('error' => 'work-id'));

$path = $workDir . '/' . $id . '.json';
if (!is_file($path)) respond_json(404, array('error' => 'work-not-found', 'work_id' => $id));

$work = json_decode((string)@file_get_contents($path), true);
if (!is_array($work)) respond_json(409, array('error' => 'work-state', 'work_id' => $id));

$last = is_array($work['last_result'] ?? null) ? $work['last_result'] : null;
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

respond_json(200, array(
    'work_id' => (string)($work['work_id'] ?? $id),
    'target_node_id' => (string)($work['target_node_id'] ?? ''),
    'capability' => (string)($work['capability'] ?? ''),
    'status' => (string)($work['status'] ?? ''),
    'attempts' => (int)($work['attempts'] ?? 0),
    'ap_ssh_open' => $apSshOpen,
    'last_result_status' => $last ? (string)($last['status'] ?? '') : null,
    'completed_at' => $last ? (int)($last['completed_at'] ?? 0) : null,
    'probe_mode' => 'read-only',
));
