<?php
declare(strict_types=1);

const PIPELINE_SHORTCUT_MAX_CLOCK_SKEW = 120;

function pipeline_shortcut_configured(array $config): bool
{
    return trim((string)($config['shortcut_device_id'] ?? '')) !== '' &&
        trim((string)($config['shortcut_token'] ?? '')) !== '';
}

function pipeline_shortcut_replay_dir(array $config): string
{
    return rtrim((string)$config['state_dir'], '/') . '/shortcut/replay';
}

function pipeline_shortcut_storage_ready(array $config): bool
{
    $dir = pipeline_shortcut_replay_dir($config);
    if (!is_dir($dir) && !@mkdir($dir, 0700, true) && !is_dir($dir)) return false;
    @chmod($dir, 0700);
    return is_writable($dir);
}

function pipeline_shortcut_authenticate(array $config, array $input): bool
{
    if (!pipeline_shortcut_configured($config) || !pipeline_shortcut_storage_ready($config)) return false;
    $device = pipeline_request_header('X-Shortcut-Device-Id');
    $token = pipeline_request_header('X-Shortcut-Token');
    if ($device === '' || $token === '') return false;
    if (!hash_equals((string)$config['shortcut_device_id'], $device) ||
        !hash_equals((string)$config['shortcut_token'], $token)) return false;

    $requestId = (string)($input['request_id'] ?? '');
    $issuedAt = (string)($input['issued_at'] ?? '');
    if (!preg_match('/^[A-Za-z0-9][A-Za-z0-9._-]{2,63}$/', $requestId)) return false;
    $when = strtotime($issuedAt);
    if ($when === false || abs(time() - $when) > PIPELINE_SHORTCUT_MAX_CLOCK_SKEW) return false;

    $path = pipeline_shortcut_replay_dir($config) . '/' . hash('sha256', $device . '|' . $requestId) . '.used';
    $handle = @fopen($path, 'x');
    if ($handle === false) return false;
    fwrite($handle, gmdate('c'));
    fclose($handle);
    @chmod($path, 0600);
    return true;
}

function pipeline_shortcut_request(mixed $input, string $repository): array
{
    if (!pipeline_plain_object($input)) throw new InvalidArgumentException('request must be an object');
    pipeline_reject_unknown($input, ['request_id', 'issued_at', 'prompt', 'target', 'task'], 'request');
    if (($input['target'] ?? null) !== $repository) throw new InvalidArgumentException('shortcut target not authorized');
    if (($input['task'] ?? null) !== 'repository_status') throw new InvalidArgumentException('shortcut task not authorized');
    $request = pipeline_validate_request([
        'request_id' => $input['request_id'] ?? null,
        'source' => 'voice_chat',
        'issued_at' => $input['issued_at'] ?? null,
        'prompt' => $input['prompt'] ?? null,
        'target' => ['repository' => $repository, 'mode' => 'same_repository'],
        'task' => ['type' => 'repository_status', 'parameters' => []],
    ], $repository);
    $request['source'] = 'voice_chat';
    return $request;
}
