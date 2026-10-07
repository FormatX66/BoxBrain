<?php
declare(strict_types=1);
const PIPELINE_SIRI_CHALLENGE_TTL = 120;
const PIPELINE_SIRI_MAX_CLOCK_SKEW = 120;
function pipeline_siri_configured(array $config): bool { return trim((string)($config['siri_device_id'] ?? '')) !== '' && trim((string)($config['siri_public_key_base64'] ?? '')) !== ''; }
function pipeline_siri_state_dir(array $config): string { return rtrim((string)$config['state_dir'], '/') . '/siri/challenges'; }
function pipeline_siri_storage_ready(array $config): bool { $dir=pipeline_siri_state_dir($config); if(!is_dir($dir)&&!@mkdir($dir,0700,true)&&!is_dir($dir))return false; @chmod($dir,0700); return is_writable($dir); }
function pipeline_siri_b64url(int $bytes=32): string { return rtrim(strtr(base64_encode(random_bytes($bytes)),'+/','-_'),'='); }
function pipeline_siri_challenge_path(array $config,string $challenge): string { return pipeline_siri_state_dir($config).'/'.hash('sha256',$challenge).'.json'; }
function pipeline_siri_issue(array $config,string $requestedDevice): array {
    $device=(string)($config['siri_device_id']??'');
    if(!pipeline_siri_configured($config)||!hash_equals($device,$requestedDevice)) throw new InvalidArgumentException('unknown siri device');
    if(!pipeline_siri_storage_ready($config)) throw new RuntimeException('siri storage unavailable');
    $challenge=pipeline_siri_b64url(); $expires=time()+PIPELINE_SIRI_CHALLENGE_TTL; $path=pipeline_siri_challenge_path($config,$challenge);
    $record=json_encode(['device_id'=>$device,'expires_at'=>$expires],JSON_UNESCAPED_SLASHES);
    if(@file_put_contents($path,$record,LOCK_EX)===false) throw new RuntimeException('challenge write failed'); @chmod($path,0600);
    return ['challenge'=>$challenge,'expires_at'=>gmdate('Y-m-d\TH:i:s\Z',$expires)];
}
function pipeline_siri_public_key_pem(string $base64Der): string {
    $der=base64_decode($base64Der,true); if($der===false||$der==='') throw new RuntimeException('siri public key is invalid');
    return "-----BEGIN PUBLIC KEY-----\n".chunk_split(base64_encode($der),64,"\n")."-----END PUBLIC KEY-----\n";
}
function pipeline_siri_canonical_path(string $requestUri): string { $path=(string)(parse_url($requestUri,PHP_URL_PATH)?:'/'); $offset=strpos($path,'/siri/'); return $offset===false?$path:substr($path,$offset); }
function pipeline_siri_consume(array $config,string $challenge,string $device): ?array {
    if($challenge===''||!pipeline_siri_storage_ready($config))return null; $path=pipeline_siri_challenge_path($config,$challenge); $handle=@fopen($path,'r'); if($handle===false)return null;
    try { if(!flock($handle,LOCK_EX))return null; $raw=stream_get_contents($handle); @unlink($path); flock($handle,LOCK_UN); } finally { fclose($handle); }
    $record=json_decode((string)$raw,true); if(!is_array($record)||!isset($record['device_id'],$record['expires_at']))return null;
    if(!hash_equals((string)$record['device_id'],$device)||(int)$record['expires_at']<time())return null; return $record;
}
function pipeline_siri_authenticate(array $config,string $method,string $requestUri,string $rawBody): bool {
    if(!pipeline_siri_configured($config))return false;
    $device=pipeline_request_header('X-Siri-Device-Id'); $challenge=pipeline_request_header('X-Siri-Challenge'); $timestamp=pipeline_request_header('X-Siri-Timestamp'); $signature64=pipeline_request_header('X-Siri-Signature');
    $configured=(string)$config['siri_device_id'];
    if($device===''||!hash_equals($configured,$device)||$challenge===''||$timestamp===''||$signature64==='')return false;
    if(pipeline_siri_consume($config,$challenge,$device)===null)return false;
    $when=strtotime($timestamp); if($when===false||abs(time()-$when)>PIPELINE_SIRI_MAX_CLOCK_SKEW)return false;
    $signature=base64_decode($signature64,true); if($signature===false)return false;
    $canonical=strtoupper($method)."\n".pipeline_siri_canonical_path($requestUri)."\n".$challenge."\n".$timestamp."\n".$rawBody;
    try { $key=openssl_pkey_get_public(pipeline_siri_public_key_pem((string)$config['siri_public_key_base64'])); if($key===false)return false; return openssl_verify($canonical,$signature,$key,OPENSSL_ALGO_SHA256)===1; } catch(Throwable){ return false; }
}
function pipeline_siri_dispatch_request(mixed $input,string $repository): array {
    if(!pipeline_plain_object($input))throw new InvalidArgumentException('request must be an object');
    pipeline_reject_unknown($input,['request_id','issued_at','prompt','target','task'],'request');
    if(($input['target']??null)!==$repository)throw new InvalidArgumentException('siri target not authorized');
    if(($input['task']??null)!=='repository_status')throw new InvalidArgumentException('siri task not authorized');
    $request=pipeline_validate_request(['request_id'=>$input['request_id']??null,'source'=>'voice_chat','issued_at'=>$input['issued_at']??null,'prompt'=>$input['prompt']??null,'target'=>['repository'=>$repository,'mode'=>'same_repository'],'task'=>['type'=>'repository_status','parameters'=>[]]],$repository);
    $request['source']='voice_chat';
    return $request;
}
