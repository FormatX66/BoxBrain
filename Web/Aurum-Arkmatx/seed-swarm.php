<?php
$root = __DIR__ . '/state';
$nodesDir = $root . '/nodes';
$workDir = $root . '/work';
if (!is_dir($workDir)) { @mkdir($workDir, 0700, true); }
$nodes = glob($nodesDir . '/*.json');
if ($nodes === false) $nodes = array();
$created = array();
$existing = array();
foreach ($nodes as $nodePath) {
    $node = json_decode((string)@file_get_contents($nodePath), true);
    if (!is_array($node)) continue;
    $nodeId = preg_replace('/[^A-Za-z0-9._-]/', '', (string)($node['node_id'] ?? ''));
    if ($nodeId === '') continue;
    $name = strtolower((string)($node['name'] ?? ''));
    if ($name === 'bbpi4' || strpos($name, 'bbpi4') !== false) continue;
    $workId = 'bbpi4-swarm-' . $nodeId;
    $workPath = $workDir . '/' . $workId . '.json';
    if (is_file($workPath)) { $existing[] = $workId; continue; }
    $work = array(
        'schema' => 'aurum.work.v0',
        'work_id' => $workId,
        'capability' => 'bbpi4-bootstrap',
        'target_node_id' => $nodeId,
        'priority' => 100,
        'status' => 'queued',
        'created' => time(),
        'lease' => null,
        'attempts' => 0,
        'payload' => array(
            'target' => 'BBPI4',
            'desired_state' => 'confirmed-enrolled-heartbeating-with-Aurum-Arkmatx',
            'addresses' => array('10.12.194.1','10.42.194.1','bbpi4.local','192.168.0.194'),
            'safe_carriers' => array('icmp','tcp22','tcp80','tcp443','ssh'),
            'stop_on_fresh_bbpi4_heartbeat' => true
        ),
        'verification' => array(
            'reversible' => true,
            'fresh_bbpi4_heartbeat_required' => true,
            'no_credential_guessing' => true,
            'non_destructive_discovery_only' => true
        )
    );
    @file_put_contents($workPath, json_encode($work, JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT), LOCK_EX);
    $created[] = $workId;
}
echo json_encode(array('ok'=>true,'created'=>$created,'existing'=>$existing,'node_count'=>count($nodes)), JSON_UNESCAPED_SLASHES | JSON_PRETTY_PRINT), "\n";
