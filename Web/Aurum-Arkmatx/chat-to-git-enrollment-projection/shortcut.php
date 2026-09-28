<?php
declare(strict_types=1);

const PIPELINE_SHORTCUT_MAX_CLOCK_SKEW = 120;

function pipeline_shortcut_credentials(array $config): array
{
    $path=rtrim((string)$config['state_dir'],'/').'/shortcut/device.json';
    if(is_file($path)&&is_readable($path)){
        $stored=json_decode((string)file_get_contents($path),true);
        if(is_array($stored)) return $stored;
    }
    return ['device_id'=>(string)($config['shortcut_device_id']??''),'token'=>(string)($config['shortcut_token']??'')];
}
function pipeline_shortcut_configured(array $config): bool
{
    $credentials=pipeline_shortcut_credentials($config);
    return trim((string)($credentials['device_id']??''))!=='' && trim((string)($credentials['token']??''))!=='';
}
function pipeline_shortcut_enrollment_path(array $config): string { return rtrim((string)$config['state_dir'],'/').'/shortcut/enrollment.json'; }
function pipeline_shortcut_enroll(array $config,array $input): bool
{
    if(pipeline_shortcut_configured($config)||!pipeline_shortcut_storage_ready($config)) return false;
    $code=(string)($input['enrollment_code']??'');$device=(string)($input['device_id']??'');$token=(string)($input['token']??'');
    if($code===''||!preg_match('/^[A-Za-z0-9._-]{3,64}$/',$device)||strlen($token)<32||strlen($token)>256) return false;
    $path=pipeline_shortcut_enrollment_path($config);$h=@fopen($path,'r');if($h===false)return false;
    try{if(!flock($h,LOCK_EX))return false;$raw=stream_get_contents($h);@unlink($path);flock($h,LOCK_UN);}finally{fclose($h);}
    $record=json_decode((string)$raw,true);if(!is_array($record)||!isset($record['code_hash'],$record['expires_at']))return false;
    if((int)$record['expires_at']<time()||!hash_equals((string)$record['code_hash'],hash('sha256',$code)))return false;
    $devicePath=rtrim((string)$config['state_dir'],'/').'/shortcut/device.json';
    $payload=json_encode(['device_id'=>$device,'token'=>$token,'enrolled_at'=>gmdate('c')],JSON_UNESCAPED_SLASHES);
    if(@file_put_contents($devicePath,$payload,LOCK_EX)===false)return false;@chmod($devicePath,0600);return true;
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
    $credentials=pipeline_shortcut_credentials($config);
    $device = pipeline_request_header('X-Shortcut-Device-Id');
    $token = pipeline_request_header('X-Shortcut-Token');
    if ($device === '' || $token === '') return false;
    if (!hash_equals((string)$credentials['device_id'], $device) ||
        !hash_equals((string)$credentials['token'], $token)) return false;

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
