<?php
declare(strict_types=1);

/*
 * Aurum contributor onboarding portal.
 * Runtime configuration (server environment):
 *   AURUM_GITHUB_CLIENT_ID        GitHub OAuth App client ID
 *   AURUM_GITHUB_CLIENT_SECRET    GitHub OAuth App client secret
 *   AURUM_GITHUB_ADMIN_TOKEN      Fine-grained/PAT or GitHub App token able to manage collaborators/issues on FormatX66/BoxBrain
 *   AURUM_HELP_INVITE_CODE        Shared private invite code; send as ?invite=CODE so family does not type it
 * Optional:
 *   AURUM_HELP_OPEN_SIGNUP=1      Allow anyone who signs in with GitHub to run onboarding
 *   AURUM_GITHUB_PERMISSION       triage (default) or push
 */

$https = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') || (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https');
header('Cache-Control: no-store, max-age=0');
header('Pragma: no-cache');
header('Referrer-Policy: no-referrer');
header('X-Content-Type-Options: nosniff');
header('X-Frame-Options: DENY');
header("Content-Security-Policy: default-src 'self'; img-src 'self' https://avatars.githubusercontent.com data:; style-src 'self' 'unsafe-inline'; form-action 'self' https://github.com; base-uri 'none'; frame-ancestors 'none'");
header('Permissions-Policy: camera=(), microphone=(), geolocation=()');

session_name('aurum_help');
session_set_cookie_params([
    'lifetime' => 0,
    'path' => '/',
    'secure' => $https,
    'httponly' => true,
    'samesite' => 'Lax',
]);
session_start();

$cfg = [
    'client_id' => trim((string)getenv('AURUM_GITHUB_CLIENT_ID')),
    'client_secret' => trim((string)getenv('AURUM_GITHUB_CLIENT_SECRET')),
    'admin_token' => trim((string)getenv('AURUM_GITHUB_ADMIN_TOKEN')),
    'invite_code' => trim((string)getenv('AURUM_HELP_INVITE_CODE')),
    'open_signup' => getenv('AURUM_HELP_OPEN_SIGNUP') === '1',
    'permission' => in_array(getenv('AURUM_GITHUB_PERMISSION'), ['triage', 'push'], true) ? getenv('AURUM_GITHUB_PERMISSION') : 'triage',
    'owner' => 'FormatX66',
    'repo' => 'BoxBrain',
];

function h(?string $value): string {
    return htmlspecialchars((string)$value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8');
}

function self_url(): string {
    $proto = ((!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') || (($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https')) ? 'https' : 'http';
    $host = $_SERVER['HTTP_HOST'] ?? 'aurum.arkmatx.com';
    $path = strtok($_SERVER['REQUEST_URI'] ?? '/helpaurum.php', '?');
    return $proto . '://' . $host . $path;
}

function flash(string $type, string $message): void {
    $_SESSION['flash'][] = ['type' => $type, 'message' => $message];
}

function redirect_self(array $params = []): never {
    $url = self_url();
    if ($params) {
        $url .= '?' . http_build_query($params);
    }
    header('Location: ' . $url, true, 303);
    exit;
}

function github_api(string $method, string $path, ?string $token = null, ?array $payload = null, ?array $basic = null): array {
    $url = str_starts_with($path, 'http') ? $path : 'https://api.github.com' . $path;
    $headers = [
        'Accept: application/vnd.github+json',
        'User-Agent: Aurum-Helper/1.0',
        'X-GitHub-Api-Version: 2026-03-10',
    ];
    if ($token !== null && $token !== '') {
        $headers[] = 'Authorization: Bearer ' . $token;
    }
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_FOLLOWLOCATION => false,
        CURLOPT_CONNECTTIMEOUT => 8,
        CURLOPT_TIMEOUT => 15,
        CURLOPT_CUSTOMREQUEST => strtoupper($method),
        CURLOPT_HTTPHEADER => $headers,
    ]);
    if ($basic !== null) {
        curl_setopt($ch, CURLOPT_USERPWD, $basic[0] . ':' . $basic[1]);
    }
    if ($payload !== null) {
        curl_setopt($ch, CURLOPT_POSTFIELDS, json_encode($payload, JSON_UNESCAPED_SLASHES));
        $headers[] = 'Content-Type: application/json';
        curl_setopt($ch, CURLOPT_HTTPHEADER, $headers);
    }
    $body = curl_exec($ch);
    $status = (int)curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
    $error = curl_error($ch);
    curl_close($ch);
    $json = is_string($body) && $body !== '' ? json_decode($body, true) : null;
    return ['status' => $status, 'body' => is_string($body) ? $body : '', 'json' => $json, 'error' => $error];
}

function oauth_exchange(string $code, string $redirectUri, array $cfg): array {
    $ch = curl_init('https://github.com/login/oauth/access_token');
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CONNECTTIMEOUT => 8,
        CURLOPT_TIMEOUT => 15,
        CURLOPT_POST => true,
        CURLOPT_HTTPHEADER => ['Accept: application/json', 'User-Agent: Aurum-Helper/1.0'],
        CURLOPT_POSTFIELDS => http_build_query([
            'client_id' => $cfg['client_id'],
            'client_secret' => $cfg['client_secret'],
            'code' => $code,
            'redirect_uri' => $redirectUri,
        ]),
    ]);
    $body = curl_exec($ch);
    $status = (int)curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
    $error = curl_error($ch);
    curl_close($ch);
    $json = is_string($body) ? json_decode($body, true) : null;
    return ['status' => $status, 'json' => $json, 'error' => $error];
}

function authorized_invite(array $cfg): bool {
    return $cfg['open_signup'] || (!empty($_SESSION['invite_ok']));
}

function invite_and_accept(array $cfg, string $username, string $userToken): array {
    if ($cfg['admin_token'] === '') {
        return ['ok' => false, 'message' => 'Aurum is connected to GitHub login, but the server admin token is not configured yet.'];
    }
    if (!authorized_invite($cfg)) {
        return ['ok' => false, 'message' => 'This GitHub account is signed in, but this browser does not have an Aurum invite link.'];
    }

    $repo = rawurlencode($cfg['owner']) . '/' . rawurlencode($cfg['repo']);
    $user = rawurlencode($username);
    $invite = github_api('PUT', "/repos/{$repo}/collaborators/{$user}", $cfg['admin_token'], ['permission' => $cfg['permission']]);
    if (!in_array($invite['status'], [201, 204], true)) {
        $msg = is_array($invite['json']) ? ($invite['json']['message'] ?? 'GitHub rejected the repository invitation.') : 'GitHub rejected the repository invitation.';
        return ['ok' => false, 'message' => $msg];
    }

    if ($invite['status'] === 204) {
        return ['ok' => true, 'message' => 'Your GitHub account is already connected to Aurum.'];
    }

    $invites = github_api('GET', '/user/repository_invitations?per_page=100', $userToken);
    if ($invites['status'] !== 200 || !is_array($invites['json'])) {
        return ['ok' => true, 'message' => 'Aurum sent the GitHub invitation. GitHub may ask you to accept it once.'];
    }

    foreach ($invites['json'] as $row) {
        if (($row['repository']['full_name'] ?? '') === $cfg['owner'] . '/' . $cfg['repo'] && isset($row['id'])) {
            $accept = github_api('PATCH', '/user/repository_invitations/' . rawurlencode((string)$row['id']), $userToken);
            if ($accept['status'] === 204) {
                return ['ok' => true, 'message' => 'Connected. Aurum sent and accepted the repository invitation automatically.'];
            }
        }
    }
    return ['ok' => true, 'message' => 'Aurum sent the repository invitation. If GitHub shows an invitation banner, accept it to finish connecting.'];
}

function collaborator_permission(array $cfg, string $username): ?string {
    if ($cfg['admin_token'] === '') {
        return null;
    }
    $repo = rawurlencode($cfg['owner']) . '/' . rawurlencode($cfg['repo']);
    $user = rawurlencode($username);
    $r = github_api('GET', "/repos/{$repo}/collaborators/{$user}/permission", $cfg['admin_token']);
    return ($r['status'] === 200 && is_array($r['json'])) ? (string)($r['json']['permission'] ?? 'connected') : null;
}

function find_starter_task(array $cfg, string $username): ?array {
    $repo = rawurlencode($cfg['owner']) . '/' . rawurlencode($cfg['repo']);
    $token = $cfg['admin_token'] !== '' ? $cfg['admin_token'] : ($_SESSION['github_token'] ?? '');
    $r = github_api('GET', "/repos/{$repo}/issues?state=open&per_page=100&sort=updated&direction=desc", $token);
    if ($r['status'] !== 200 || !is_array($r['json'])) {
        return null;
    }

    $candidates = [];
    foreach ($r['json'] as $issue) {
        if (isset($issue['pull_request'])) {
            continue;
        }
        $labels = array_map(static fn($l) => strtolower((string)($l['name'] ?? '')), $issue['labels'] ?? []);
        $score = 0;
        foreach ($labels as $label) {
            if (str_contains($label, 'good first')) $score += 100;
            if (str_contains($label, 'help wanted')) $score += 60;
            if (str_contains($label, 'aurum')) $score += 40;
            if (str_contains($label, 'documentation') || str_contains($label, 'docs')) $score += 20;
            if (str_contains($label, 'test')) $score += 15;
        }
        if (!empty($issue['assignees'])) {
            $score -= 50;
        }
        $issue['_score'] = $score;
        $candidates[] = $issue;
    }
    usort($candidates, static fn($a, $b) => ($b['_score'] <=> $a['_score']) ?: (($a['number'] ?? 0) <=> ($b['number'] ?? 0)));
    $task = $candidates[0] ?? null;
    if (!$task) {
        return null;
    }

    if ($cfg['admin_token'] !== '' && empty($task['assignees'])) {
        $assign = github_api('PATCH', "/repos/{$repo}/issues/" . rawurlencode((string)$task['number']), $cfg['admin_token'], ['assignees' => [$username]]);
        if ($assign['status'] === 200 && is_array($assign['json'])) {
            $task = $assign['json'];
        }
    }
    return $task;
}

function revoke_oauth_token(array $cfg, string $token): void {
    if ($token === '' || $cfg['client_id'] === '' || $cfg['client_secret'] === '') {
        return;
    }
    github_api('DELETE', '/applications/' . rawurlencode($cfg['client_id']) . '/token', null, ['access_token' => $token], [$cfg['client_id'], $cfg['client_secret']]);
}

if (isset($_GET['invite']) && $cfg['invite_code'] !== '') {
    $provided = (string)$_GET['invite'];
    if (hash_equals($cfg['invite_code'], $provided)) {
        $_SESSION['invite_ok'] = true;
        flash('ok', 'Aurum invite recognized. Continue with GitHub.');
    } else {
        flash('bad', 'That Aurum invite link is not valid.');
    }
    redirect_self();
}

$action = (string)($_GET['action'] ?? '');

if ($action === 'login') {
    if ($cfg['client_id'] === '' || $cfg['client_secret'] === '') {
        flash('bad', 'GitHub sign-in is not configured on the Aurum server yet.');
        redirect_self();
    }
    if (!authorized_invite($cfg) && $cfg['invite_code'] !== '') {
        flash('bad', 'Use the private Aurum invite link you were sent before signing in.');
        redirect_self();
    }
    $_SESSION['oauth_state'] = bin2hex(random_bytes(24));
    $params = [
        'client_id' => $cfg['client_id'],
        'redirect_uri' => self_url(),
        'scope' => 'read:user repo:invite',
        'state' => $_SESSION['oauth_state'],
    ];
    header('Location: https://github.com/login/oauth/authorize?' . http_build_query($params), true, 302);
    exit;
}

if (isset($_GET['code'])) {
    $state = (string)($_GET['state'] ?? '');
    if (empty($_SESSION['oauth_state']) || !hash_equals((string)$_SESSION['oauth_state'], $state)) {
        flash('bad', 'GitHub sign-in could not be verified. Please try again.');
        unset($_SESSION['oauth_state']);
        redirect_self();
    }
    unset($_SESSION['oauth_state']);
    $exchange = oauth_exchange((string)$_GET['code'], self_url(), $cfg);
    $token = is_array($exchange['json']) ? (string)($exchange['json']['access_token'] ?? '') : '';
    if ($token === '') {
        flash('bad', 'GitHub did not return a usable sign-in token.');
        redirect_self();
    }
    $user = github_api('GET', '/user', $token);
    if ($user['status'] !== 200 || !is_array($user['json']) || empty($user['json']['login'])) {
        revoke_oauth_token($cfg, $token);
        flash('bad', 'Aurum could not read your GitHub profile.');
        redirect_self();
    }
    session_regenerate_id(true);
    $_SESSION['github_token'] = $token;
    $_SESSION['github_user'] = [
        'login' => (string)$user['json']['login'],
        'name' => (string)($user['json']['name'] ?? ''),
        'avatar_url' => (string)($user['json']['avatar_url'] ?? ''),
        'html_url' => (string)($user['json']['html_url'] ?? ''),
    ];
    $connect = invite_and_accept($cfg, $_SESSION['github_user']['login'], $token);
    flash($connect['ok'] ? 'ok' : 'warn', $connect['message']);
    redirect_self();
}

if ($action === 'connect' && !empty($_SESSION['github_user']['login']) && !empty($_SESSION['github_token'])) {
    $connect = invite_and_accept($cfg, (string)$_SESSION['github_user']['login'], (string)$_SESSION['github_token']);
    flash($connect['ok'] ? 'ok' : 'warn', $connect['message']);
    redirect_self();
}

if ($action === 'task' && !empty($_SESSION['github_user']['login'])) {
    $task = find_starter_task($cfg, (string)$_SESSION['github_user']['login']);
    if ($task) {
        $_SESSION['starter_task'] = [
            'number' => (int)($task['number'] ?? 0),
            'title' => (string)($task['title'] ?? 'Aurum starter task'),
            'html_url' => (string)($task['html_url'] ?? ''),
            'body' => (string)($task['body'] ?? ''),
        ];
        flash('ok', 'Aurum picked a starter task for you.');
    } else {
        flash('warn', 'No open starter issue is available right now. You can still test Aurum, improve documentation, or open a new idea.');
    }
    redirect_self();
}

if ($action === 'logout') {
    $token = (string)($_SESSION['github_token'] ?? '');
    revoke_oauth_token($cfg, $token);
    $_SESSION = [];
    if (ini_get('session.use_cookies')) {
        $p = session_get_cookie_params();
        setcookie(session_name(), '', time() - 42000, $p['path'], $p['domain'] ?? '', (bool)$p['secure'], (bool)$p['httponly']);
    }
    session_destroy();
    header('Location: ' . self_url(), true, 303);
    exit;
}

$flashes = $_SESSION['flash'] ?? [];
unset($_SESSION['flash']);
$user = $_SESSION['github_user'] ?? null;
$task = $_SESSION['starter_task'] ?? null;
$permission = is_array($user) ? collaborator_permission($cfg, (string)$user['login']) : null;
$oauthReady = $cfg['client_id'] !== '' && $cfg['client_secret'] !== '';
$automationReady = $oauthReady && $cfg['admin_token'] !== '';
$inviteReady = $cfg['open_signup'] || $cfg['invite_code'] !== '';
$invitedThisBrowser = authorized_invite($cfg);
?>
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Help Aurum</title>
<style>
:root{color-scheme:dark;--bg:#080b10;--panel:#101720e8;--line:#253246;--text:#eef3f8;--muted:#9fb0c2;--gold:#e0bd62;--green:#62d990;--red:#ff8d8d;--blue:#72b7ff;font-family:Inter,ui-sans-serif,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}*{box-sizing:border-box}body{margin:0;min-height:100vh;background:radial-gradient(circle at 18% 0,#1b2738 0,transparent 38%),var(--bg);color:var(--text)}a{color:inherit}.wrap{width:min(1040px,94vw);margin:0 auto;padding:30px 0 64px}.brand{display:flex;align-items:center;gap:14px;margin-bottom:24px}.orb{width:48px;height:48px;border-radius:50%;background:radial-gradient(circle at 32% 28%,#fff7cf 0,#d8b85b 22%,#6d5120 55%,#17140c 76%);box-shadow:0 0 34px #d9b65a55}.brand h1{font-size:29px;margin:0;letter-spacing:.08em}.brand small{display:block;color:#8fa0b2;margin-top:3px}.hero{background:linear-gradient(145deg,#131d29e8,#0e151ee8);border:1px solid var(--line);border-radius:22px;padding:26px;box-shadow:0 18px 60px #0008;margin-bottom:18px}.hero h2{font-size:clamp(26px,5vw,48px);line-height:1.05;margin:0 0 12px;max-width:760px}.hero p{font-size:17px;line-height:1.6;color:var(--muted);max-width:780px}.steps{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-top:22px}.step{padding:13px;border:1px solid #29384c;background:#0b1119;border-radius:14px;color:#a8b7c6;font-size:13px}.step b{display:block;color:#f2f6fa;font-size:14px;margin-bottom:4px}.step.done{border-color:#2f5f46;background:#0f1c17}.grid{display:grid;grid-template-columns:1.2fr .8fr;gap:18px}.card{background:var(--panel);border:1px solid var(--line);border-radius:18px;padding:21px;box-shadow:0 18px 50px #0005}.card h3{margin:0 0 8px;font-size:19px}.card p{color:var(--muted);line-height:1.55}.button{display:inline-flex;align-items:center;justify-content:center;min-height:46px;padding:0 18px;border-radius:12px;background:var(--gold);color:#171309;text-decoration:none;font-weight:850;border:0;cursor:pointer}.button.secondary{background:#1b2735;color:#edf4fb;border:1px solid #35465d}.button.ghost{background:transparent;color:#bfd0e1;border:1px solid #31445b}.button.danger{background:#301a1e;color:#ffb9bf;border:1px solid #63313a}.actions{display:flex;flex-wrap:wrap;gap:10px;margin-top:16px}.statusline{display:flex;gap:10px;align-items:center;padding:11px 12px;border-radius:12px;background:#0a1118;border:1px solid #223044;margin:12px 0}.dot{width:9px;height:9px;border-radius:50%;background:#6f7f90}.dot.ok{background:var(--green);box-shadow:0 0 13px #62d99088}.dot.warn{background:#e5b95e}.profile{display:flex;gap:14px;align-items:center;margin:14px 0}.profile img{width:56px;height:56px;border-radius:50%;border:1px solid #394b61}.profile b{display:block;font-size:18px}.profile span{color:var(--muted);font-size:13px}.flash{padding:12px 14px;border-radius:12px;border:1px solid #314056;margin-bottom:12px;background:#111923}.flash.ok{border-color:#2f6046;background:#102019}.flash.warn{border-color:#6b5729;background:#241e11}.flash.bad{border-color:#71363e;background:#261417}.task{padding:15px;border:1px solid #334762;background:#0b121b;border-radius:14px;margin-top:13px}.task small{color:#8fa3b7}.task h4{font-size:18px;margin:7px 0 8px}.task p{margin:0}.checklist{display:grid;gap:10px;margin:14px 0 0;padding:0;list-style:none}.checklist li{display:flex;gap:9px;color:#b9c7d5}.check{width:21px;height:21px;flex:0 0 21px;border-radius:50%;background:#173426;color:#91e9b4;display:inline-grid;place-items:center;font-weight:900}.mini{font-size:12px;color:#8194a7;margin-top:12px}.setup{border-top:1px solid #26364a;margin-top:16px;padding-top:14px}.code{font:12px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace;background:#080d13;border:1px solid #26364b;border-radius:10px;padding:10px;overflow:auto;color:#cbd8e5}.badge{display:inline-block;padding:3px 8px;border-radius:999px;background:#19314c;color:#9dccff;font-size:11px;margin-left:6px}@media(max-width:800px){.grid{grid-template-columns:1fr}.steps{grid-template-columns:1fr 1fr}.wrap{padding-top:20px}}@media(max-width:480px){.steps{grid-template-columns:1fr}.hero{padding:20px}.card{padding:18px}.button{width:100%}.actions{display:grid}}
</style>
</head>
<body><main class="wrap">
<div class="brand"><div class="orb"></div><div><h1>AURUM</h1><small>Help Aurum · contributor onboarding</small></div></div>

<?php foreach ($flashes as $f): ?>
<div class="flash <?= h($f['type']) ?>"><?= h($f['message']) ?></div>
<?php endforeach; ?>

<section class="hero">
<h2>Say “I want to help.” Aurum handles the boring part.</h2>
<p>Use your own GitHub account. Aurum never asks for your GitHub password. After GitHub confirms who you are, this portal can connect you to the project, accept the repository invitation, find a starter task, and send you straight to the work.</p>
<div class="steps">
<div class="step <?= $user ? 'done' : '' ?>"><b>1 · GitHub</b>Sign in or create your account at GitHub.</div>
<div class="step <?= $permission ? 'done' : '' ?>"><b>2 · Connect</b>Aurum links your GitHub identity to BoxBrain.</div>
<div class="step <?= $task ? 'done' : '' ?>"><b>3 · First task</b>Aurum chooses an open task that needs help.</div>
<div class="step"><b>4 · Contribute</b>Test, document, code, review, or share an idea.</div>
</div>
</section>

<div class="grid">
<section class="card">
<?php if (!$user): ?>
<h3>Join the Aurum project</h3>
<p>One GitHub button is the main doorway. If you do not have a GitHub account yet, GitHub handles the required account setup and verification; Aurum takes over again after authorization.</p>
<div class="statusline"><span class="dot <?= $oauthReady ? 'ok' : 'warn' ?>"></span><span><?= $oauthReady ? 'GitHub sign-in is ready.' : 'The page is deployed, but GitHub OAuth still needs its one-time server configuration.' ?></span></div>
<?php if ($cfg['invite_code'] !== '' && !$invitedThisBrowser): ?>
<div class="statusline"><span class="dot warn"></span><span>Use the private Aurum invite link you were sent. It authorizes this browser without making you type another code.</span></div>
<?php endif; ?>
<div class="actions">
<a class="button" href="?action=login">Continue with GitHub</a>
<a class="button ghost" href="https://github.com/FormatX66/BoxBrain" rel="noreferrer">View the project</a>
</div>
<p class="mini">Shared computer? That is fine. Each person uses their own GitHub login, then presses “Finish & clear this device” when done.</p>
<?php else: ?>
<h3>You’re signed in</h3>
<div class="profile">
<?php if (!empty($user['avatar_url'])): ?><img src="<?= h($user['avatar_url']) ?>" alt="GitHub avatar"><?php endif; ?>
<div><b><?= h($user['name'] ?: $user['login']) ?></b><span>@<?= h($user['login']) ?> on GitHub</span></div>
</div>
<div class="statusline"><span class="dot <?= $permission ? 'ok' : 'warn' ?>"></span><span><?= $permission ? 'Connected to FormatX66/BoxBrain with ' . h($permission) . ' access.' : ($automationReady ? 'GitHub is signed in; Aurum can finish the repository connection.' : 'GitHub is signed in. Automatic repository invitation needs the server admin token configured.') ?></span></div>
<div class="actions">
<?php if (!$permission): ?><a class="button" href="?action=connect">Connect me to Aurum</a><?php endif; ?>
<a class="button <?= $permission ? '' : 'secondary' ?>" href="?action=task">Give me a starter task</a>
<a class="button danger" href="?action=logout">Finish &amp; clear this device</a>
</div>

<?php if ($task): ?>
<div class="task">
<small>Starter task #<?= (int)$task['number'] ?></small>
<h4><?= h($task['title']) ?></h4>
<p>Aurum selected this from the live BoxBrain issue queue. Open it, read the goal, and contribute in whatever way matches your skills.</p>
<div class="actions"><a class="button" href="<?= h($task['html_url']) ?>" rel="noreferrer">Open my task on GitHub</a></div>
</div>
<?php endif; ?>
<?php endif; ?>
</section>

<aside class="card">
<h3>What counts as helping?</h3>
<ul class="checklist">
<li><span class="check">✓</span><span><b>Test it.</b><br>Try Aurum on a PC, Pi, browser, or workflow and report what happened.</span></li>
<li><span class="check">✓</span><span><b>Explain it.</b><br>Improve instructions so the next person can understand the project faster.</span></li>
<li><span class="check">✓</span><span><b>Build it.</b><br>Take an issue, make a branch or fork, and submit a pull request.</span></li>
<li><span class="check">✓</span><span><b>Challenge it.</b><br>Find assumptions, contradictions, edge cases, and better approaches.</span></li>
</ul>
<div class="setup">
<h3>Automation status</h3>
<div class="statusline"><span class="dot <?= $oauthReady ? 'ok' : 'warn' ?>"></span><span>GitHub login <?= $oauthReady ? 'ready' : 'needs setup' ?></span></div>
<div class="statusline"><span class="dot <?= $cfg['admin_token'] !== '' ? 'ok' : 'warn' ?>"></span><span>Repo connection <?= $cfg['admin_token'] !== '' ? 'ready' : 'needs setup' ?></span></div>
<div class="statusline"><span class="dot <?= $inviteReady ? 'ok' : 'warn' ?>"></span><span>Invite gate <?= $inviteReady ? 'ready' : 'needs setup' ?></span></div>
<?php if (!$oauthReady || !$automationReady || !$inviteReady): ?>
<p class="mini">Owner setup is intentionally server-side. No secret should be placed in this PHP file or in the browser.</p>
<div class="code">AURUM_GITHUB_CLIENT_ID
AURUM_GITHUB_CLIENT_SECRET
AURUM_GITHUB_ADMIN_TOKEN
AURUM_HELP_INVITE_CODE</div>
<?php endif; ?>
</div>
</aside>
</div>
</main></body></html>
