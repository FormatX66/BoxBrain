<?php
declare(strict_types=1);

const PIPELINE_VERSION = '1.0.0';
const PIPELINE_MAX_BODY = 32768;
const PIPELINE_ALLOWED_SOURCES = ['voice_chat', 'gpt', 'webhook', 'manual', 'test'];
const PIPELINE_ALLOWED_TASKS = ['echo', 'repository_status', 'future_branch'];

function pipeline_respond(int $status, array $payload): never
{
    http_response_code($status);
    header('Content-Type: application/json; charset=utf-8');
    header('Cache-Control: no-store');
    header('X-Content-Type-Options: nosniff');
    header('Referrer-Policy: no-referrer');
    echo json_encode($payload, JSON_UNESCAPED_SLASHES | JSON_INVALID_UTF8_SUBSTITUTE);
    exit;
}

function pipeline_home_dir(): string
{
    $home = (string)(getenv('HOME') ?: '');
    if ($home !== '' && str_starts_with($home, '/home')) {
        return rtrim($home, '/');
    }
    return dirname(__DIR__, 4);
}

function pipeline_config_path(): string
{
    $configured = (string)(getenv('CHAT_TO_GIT_CONFIG') ?: '');
    return $configured !== '' ? $configured : pipeline_home_dir() . '/.config/chat-to-git/config.php';
}

function pipeline_load_config(): array
{
    $path = pipeline_config_path();
    $config = is_file($path) && is_readable($path) ? require $path : [];
    if (!is_array($config)) {
        throw new RuntimeException('runtime configuration is invalid');
    }
    return array_merge([
        'github_repository' => 'FormatX66/Chat-to-Git-Pipeline',
        'github_token' => '',
        'bearer_token' => '',
        'shared_secret' => '',
        'state_dir' => pipeline_home_dir() . '/.local/state/chat-to-git',
        'rate_limit_per_minute' => 30,
    ], $config);
}

function pipeline_config_status(array $config): array
{
    return [
        'github_configured' => is_string($config['github_token']) && $config['github_token'] !== '',
        'authentication_configured' =>
            (is_string($config['bearer_token']) && $config['bearer_token'] !== '') ||
            (is_string($config['shared_secret']) && $config['shared_secret'] !== ''),
    ];
}

function pipeline_storage_ready(array $config): bool
{
    $stateDir = (string)$config['state_dir'];
    foreach ([$stateDir, $stateDir . '/rate', $stateDir . '/audit'] as $dir) {
        if (!is_dir($dir) && !@mkdir($dir, 0700, true) && !is_dir($dir)) {
            return false;
        }
        @chmod($dir, 0700);
        if (!is_writable($dir)) return false;
    }
    return true;
}

function pipeline_raw_body(): string
{
    $length = (int)($_SERVER['CONTENT_LENGTH'] ?? 0);
    if ($length <= 0 || $length > PIPELINE_MAX_BODY) {
        pipeline_respond(413, ['error' => 'body-size']);
    }
    $raw = file_get_contents('php://input', false, null, 0, PIPELINE_MAX_BODY + 1);
    if ($raw === false || strlen($raw) > PIPELINE_MAX_BODY) {
        pipeline_respond(413, ['error' => 'body-size']);
    }
    return $raw;
}

function pipeline_request_header(string $name): string
{
    $key = 'HTTP_' . strtoupper(str_replace('-', '_', $name));
    return trim((string)($_SERVER[$key] ?? ''));
}

function pipeline_authorized(array $config, string $rawBody): bool
{
    $authorization = pipeline_request_header('Authorization');
    $bearer = str_starts_with($authorization, 'Bearer ') ? substr($authorization, 7) : '';
    $configuredBearer = (string)$config['bearer_token'];
    if ($configuredBearer !== '' && $bearer !== '' && hash_equals($configuredBearer, $bearer)) {
        return true;
    }

    $sharedSecret = (string)$config['shared_secret'];
    $suppliedSignature = pipeline_request_header('X-Pipeline-Signature');
    if ($sharedSecret !== '' && $suppliedSignature !== '') {
        $expected = 'sha256=' . hash_hmac('sha256', $rawBody, $sharedSecret);
        return hash_equals($expected, $suppliedSignature);
    }
    return false;
}

function pipeline_client_bucket(): string
{
    $ip = (string)($_SERVER['REMOTE_ADDR'] ?? 'unknown');
    return hash('sha256', $ip . '|' . gmdate('Y-m-d-H-i'));
}

function pipeline_rate_limit(array $config): bool
{
    $limit = max(1, min(120, (int)$config['rate_limit_per_minute']));
    $path = rtrim((string)$config['state_dir'], '/') . '/rate/' . pipeline_client_bucket() . '.count';
    $handle = @fopen($path, 'c+');
    if ($handle === false) return false;
    try {
        if (!flock($handle, LOCK_EX)) return false;
        rewind($handle);
        $current = (int)trim((string)stream_get_contents($handle));
        if ($current >= $limit) return false;
        ftruncate($handle, 0);
        rewind($handle);
        fwrite($handle, (string)($current + 1));
        fflush($handle);
        @chmod($path, 0600);
        flock($handle, LOCK_UN);
        return true;
    } finally {
        fclose($handle);
    }
}

function pipeline_audit(array $config, array $record): void
{
    $path = rtrim((string)$config['state_dir'], '/') . '/audit/' . gmdate('Y-m-d') . '.jsonl';
    $safe = array_intersect_key($record, array_flip([
        'request_id', 'event', 'status', 'http_status', 'route', 'github_status'
    ]));
    $safe['observed_at'] = gmdate('c');
    @file_put_contents($path, json_encode($safe, JSON_UNESCAPED_SLASHES) . "\n", FILE_APPEND | LOCK_EX);
    @chmod($path, 0600);
}

function pipeline_plain_object(mixed $value): bool
{
    return is_array($value) && !array_is_list($value);
}

function pipeline_reject_unknown(array $value, array $allowed, string $path): void
{
    foreach (array_keys($value) as $key) {
        if (!is_string($key) || !in_array($key, $allowed, true)) {
            throw new InvalidArgumentException($path . '.' . (string)$key . ' is not allowed');
        }
    }
}

function pipeline_bounded_string(mixed $value, string $path, int $max): string
{
    if (!is_string($value) || trim($value) === '' || strlen($value) > $max) {
        throw new InvalidArgumentException($path . ' is invalid');
    }
    return $value;
}

function pipeline_unit_number(mixed $value, string $path): float
{
    if (!is_int($value) && !is_float($value)) {
        throw new InvalidArgumentException($path . ' must be numeric');
    }
    $number = (float)$value;
    if ($number < 0 || $number > 1) throw new InvalidArgumentException($path . ' must be between 0 and 1');
    return $number;
}

function pipeline_validate_future_branch(array $branch, int $index): array
{
    $path = 'task.parameters.branches[' . $index . ']';
    pipeline_reject_unknown($branch, [
        'id', 'summary', 'confidence', 'evidence_quality', 'risk', 'cost',
        'reversibility', 'authority', 'fresh'
    ], $path);
    $reversibility = (string)($branch['reversibility'] ?? '');
    $authority = (string)($branch['authority'] ?? '');
    if (!in_array($reversibility, ['full', 'partial', 'none'], true)) {
        throw new InvalidArgumentException($path . '.reversibility is invalid');
    }
    if (!in_array($authority, ['authorized', 'pending', 'denied'], true)) {
        throw new InvalidArgumentException($path . '.authority is invalid');
    }
    return [
        'id' => pipeline_bounded_string($branch['id'] ?? null, $path . '.id', 64),
        'summary' => pipeline_bounded_string($branch['summary'] ?? null, $path . '.summary', 500),
        'confidence' => pipeline_unit_number($branch['confidence'] ?? null, $path . '.confidence'),
        'evidence_quality' => pipeline_unit_number($branch['evidence_quality'] ?? null, $path . '.evidence_quality'),
        'risk' => pipeline_unit_number($branch['risk'] ?? null, $path . '.risk'),
        'cost' => pipeline_unit_number($branch['cost'] ?? null, $path . '.cost'),
        'reversibility' => $reversibility,
        'authority' => $authority,
        'fresh' => ($branch['fresh'] ?? false) === true,
    ];
}

function pipeline_validate_task(mixed $task): array
{
    if (!pipeline_plain_object($task)) throw new InvalidArgumentException('task must be an object');
    pipeline_reject_unknown($task, ['type', 'parameters'], 'task');
    $type = (string)($task['type'] ?? '');
    if (!in_array($type, PIPELINE_ALLOWED_TASKS, true)) throw new InvalidArgumentException('task.type is unsupported');
    $parameters = $task['parameters'] ?? [];
    if (!pipeline_plain_object($parameters) && $parameters !== []) {
        throw new InvalidArgumentException('task.parameters must be an object');
    }

    if ($type === 'echo') {
        pipeline_reject_unknown($parameters, ['message'], 'task.parameters');
        return ['type' => $type, 'parameters' => [
            'message' => pipeline_bounded_string($parameters['message'] ?? null, 'task.parameters.message', 1000),
        ]];
    }
    if ($type === 'repository_status') {
        pipeline_reject_unknown($parameters, [], 'task.parameters');
        return ['type' => $type, 'parameters' => (object)[]];
    }

    pipeline_reject_unknown($parameters, [
        'verified_state', 'last_known_good', 'branches', 'ambiguity_threshold'
    ], 'task.parameters');
    $branches = $parameters['branches'] ?? null;
    if (!is_array($branches) || !array_is_list($branches) || count($branches) < 1 || count($branches) > 5) {
        throw new InvalidArgumentException('task.parameters.branches must contain 1 to 5 branches');
    }
    $normalized = [];
    foreach ($branches as $index => $branch) {
        if (!pipeline_plain_object($branch)) throw new InvalidArgumentException('future branch must be an object');
        $normalized[] = pipeline_validate_future_branch($branch, $index);
    }
    $threshold = $parameters['ambiguity_threshold'] ?? 0.08;
    if ((!is_int($threshold) && !is_float($threshold)) || $threshold < 0 || $threshold > 0.25) {
        throw new InvalidArgumentException('task.parameters.ambiguity_threshold is invalid');
    }
    return ['type' => $type, 'parameters' => [
        'verified_state' => pipeline_bounded_string($parameters['verified_state'] ?? null, 'task.parameters.verified_state', 500),
        'last_known_good' => pipeline_bounded_string($parameters['last_known_good'] ?? null, 'task.parameters.last_known_good', 500),
        'branches' => $normalized,
        'ambiguity_threshold' => (float)$threshold,
    ]];
}

function pipeline_validate_request(mixed $input, string $repository): array
{
    if (!pipeline_plain_object($input)) throw new InvalidArgumentException('request must be an object');
    pipeline_reject_unknown($input, [
        'request_id', 'source', 'issued_at', 'prompt', 'target', 'task', 'feedback'
    ], 'request');

    $requestId = (string)($input['request_id'] ?? '');
    if (!preg_match('/^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$/', $requestId)) {
        throw new InvalidArgumentException('request_id is invalid');
    }
    $source = (string)($input['source'] ?? '');
    if (!in_array($source, PIPELINE_ALLOWED_SOURCES, true)) throw new InvalidArgumentException('source is invalid');
    $target = $input['target'] ?? null;
    if (!pipeline_plain_object($target)) throw new InvalidArgumentException('target must be an object');
    pipeline_reject_unknown($target, ['repository', 'mode'], 'target');
    if (($target['repository'] ?? null) !== $repository || ($target['mode'] ?? null) !== 'same_repository') {
        throw new InvalidArgumentException('target must be the configured same repository');
    }

    $feedback = $input['feedback'] ?? [];
    if (!pipeline_plain_object($feedback) && $feedback !== []) throw new InvalidArgumentException('feedback must be an object');
    pipeline_reject_unknown($feedback, ['issue_number', 'callback_url'], 'feedback');
    if (isset($feedback['issue_number']) && (!is_int($feedback['issue_number']) || $feedback['issue_number'] < 1)) {
        throw new InvalidArgumentException('feedback.issue_number is invalid');
    }
    if (isset($feedback['callback_url'])) {
        $callback = pipeline_bounded_string($feedback['callback_url'], 'feedback.callback_url', 1000);
        if (!str_starts_with($callback, 'https://') || filter_var($callback, FILTER_VALIDATE_URL) === false) {
            throw new InvalidArgumentException('feedback.callback_url must use HTTPS');
        }
    }

    $issuedAt = (string)($input['issued_at'] ?? gmdate('c'));
    if (strtotime($issuedAt) === false) throw new InvalidArgumentException('issued_at is invalid');
    $normalized = [
        'request_id' => $requestId,
        'source' => 'webhook',
        'issued_at' => gmdate('c', (int)strtotime($issuedAt)),
        'target' => ['repository' => $repository, 'mode' => 'same_repository'],
        'task' => pipeline_validate_task($input['task'] ?? null),
        'feedback' => $feedback === [] ? (object)[] : $feedback,
    ];
    if (isset($input['prompt'])) {
        $normalized['prompt'] = pipeline_bounded_string($input['prompt'], 'prompt', 4000);
    }
    return $normalized;
}

function pipeline_github_request(array $config, string $method, string $path, ?array $body = null): array
{
    $token = (string)$config['github_token'];
    if ($token === '') throw new RuntimeException('github credential is not configured');
    $handle = curl_init('https://api.github.com' . $path);
    if ($handle === false) throw new RuntimeException('github transport unavailable');
    $headers = [
        'Accept: application/vnd.github+json',
        'Authorization: Bearer ' . $token,
        'Content-Type: application/json',
        'User-Agent: FormatX66-Chat-to-Git-Bluehost/1.0',
        'X-GitHub-Api-Version: 2022-11-28',
    ];
    curl_setopt_array($handle, [
        CURLOPT_CUSTOMREQUEST => $method,
        CURLOPT_HTTPHEADER => $headers,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CONNECTTIMEOUT => 5,
        CURLOPT_TIMEOUT => 20,
        CURLOPT_FOLLOWLOCATION => false,
    ]);
    if ($body !== null) curl_setopt($handle, CURLOPT_POSTFIELDS, json_encode($body, JSON_UNESCAPED_SLASHES));
    $responseBody = curl_exec($handle);
    $status = (int)curl_getinfo($handle, CURLINFO_RESPONSE_CODE);
    $transportError = curl_error($handle);
    curl_close($handle);
    if ($responseBody === false) throw new RuntimeException('github transport failed: ' . $transportError);
    $decoded = $responseBody === '' ? null : json_decode($responseBody, true);
    return ['status' => $status, 'body' => $decoded];
}

function pipeline_dispatch(array $config, array $request): void
{
    $repository = rawurlencode((string)$config['github_repository']);
    $repository = str_replace('%2F', '/', $repository);
    $response = pipeline_github_request($config, 'POST', '/repos/' . $repository . '/dispatches', [
        'event_type' => 'voice_chat_request',
        'client_payload' => ['request' => $request],
    ]);
    if ($response['status'] !== 204) {
        throw new RuntimeException('github dispatch failed with HTTP ' . $response['status']);
    }
}

function pipeline_feedback_status(array $config, string $requestId): ?array
{
    $repository = rawurlencode((string)$config['github_repository']);
    $repository = str_replace('%2F', '/', $repository);
    $issues = pipeline_github_request($config, 'GET', '/repos/' . $repository . '/issues?state=all&labels=pipeline-feedback&per_page=100');
    if ($issues['status'] !== 200 || !is_array($issues['body'])) {
        throw new RuntimeException('github status lookup failed with HTTP ' . $issues['status']);
    }
    $issue = null;
    foreach ($issues['body'] as $candidate) {
        if (str_starts_with((string)($candidate['title'] ?? ''), '[pipeline:' . $requestId . ']')) {
            $issue = $candidate;
            break;
        }
    }
    if ($issue === null) return null;
    $comments = pipeline_github_request($config, 'GET', '/repos/' . $repository . '/issues/' . (int)$issue['number'] . '/comments?per_page=100');
    if ($comments['status'] !== 200 || !is_array($comments['body'])) {
        throw new RuntimeException('github feedback lookup failed with HTTP ' . $comments['status']);
    }
    $status = 'accepted';
    foreach ($comments['body'] as $comment) {
        if (preg_match('/pipeline-status:' . preg_quote($requestId, '/') . ':([a-z_]+)/', (string)($comment['body'] ?? ''), $match)) {
            $status = $match[1];
        }
    }
    return [
        'request_id' => $requestId,
        'status' => $status,
        'route' => 'webhook_to_github',
        'issue_url' => (string)($issue['html_url'] ?? ''),
    ];
}
