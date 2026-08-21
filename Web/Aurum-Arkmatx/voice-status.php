<?php
declare(strict_types=1);

const AURUM_REPO = 'FormatX66/BoxBrain';
const AURUM_CACHE_SECONDS = 120;

function aurum_json_file(string $path): array
{
    $raw = @file_get_contents($path);
    if ($raw === false) {
        throw new RuntimeException('status snapshot unavailable');
    }
    $data = json_decode($raw, true, 64, JSON_THROW_ON_ERROR);
    if (!is_array($data)) {
        throw new RuntimeException('status snapshot is not an object');
    }
    return $data;
}

function aurum_fetch_json(string $url): ?array
{
    $headers = [
        'Accept: application/vnd.github+json',
        'User-Agent: Aurum-Voice-Status/2',
        'X-GitHub-Api-Version: 2022-11-28',
    ];

    if (function_exists('curl_init')) {
        $handle = curl_init($url);
        if ($handle === false) {
            return null;
        }
        curl_setopt_array($handle, [
            CURLOPT_RETURNTRANSFER => true,
            CURLOPT_CONNECTTIMEOUT => 4,
            CURLOPT_TIMEOUT => 8,
            CURLOPT_FOLLOWLOCATION => false,
            CURLOPT_HTTPHEADER => $headers,
            CURLOPT_PROTOCOLS => CURLPROTO_HTTPS,
            CURLOPT_SSL_VERIFYPEER => true,
            CURLOPT_SSL_VERIFYHOST => 2,
        ]);
        $raw = curl_exec($handle);
        $status = (int) curl_getinfo($handle, CURLINFO_RESPONSE_CODE);
        curl_close($handle);
        if (!is_string($raw) || $status < 200 || $status >= 300) {
            return null;
        }
    } else {
        $context = stream_context_create([
            'http' => [
                'method' => 'GET',
                'timeout' => 8,
                'ignore_errors' => false,
                'header' => implode("\r\n", $headers) . "\r\n",
            ],
            'ssl' => [
                'verify_peer' => true,
                'verify_peer_name' => true,
            ],
        ]);
        $raw = @file_get_contents($url, false, $context);
        if (!is_string($raw)) {
            return null;
        }
    }

    try {
        $data = json_decode($raw, true, 64, JSON_THROW_ON_ERROR);
    } catch (Throwable $error) {
        return null;
    }
    return is_array($data) ? $data : null;
}

function aurum_time(?string $value): int
{
    if (!$value) {
        return 0;
    }
    $parsed = strtotime($value);
    return $parsed === false ? 0 : $parsed;
}

function aurum_active_run(array $run): bool
{
    return in_array((string) ($run['status'] ?? ''), [
        'queued', 'in_progress', 'waiting', 'requested', 'pending'
    ], true);
}

function aurum_set_all_stage(array &$payload, string $stage, bool $value): void
{
    foreach ($payload['human_capabilities'] as &$capability) {
        if (isset($capability['stages']) && is_array($capability['stages'])) {
            $capability['stages'][$stage] = $value;
        }
    }
    unset($capability);
}

function aurum_stage_count(array $capability): int
{
    $count = 0;
    foreach (($capability['stages'] ?? []) as $value) {
        if ($value === true) {
            $count++;
        }
    }
    return $count;
}

function aurum_commit_message(array $commit): string
{
    return (string) ($commit['commit']['message'] ?? '');
}

function aurum_run_head_time(array $run): int
{
    $headCommit = $run['head_commit'] ?? null;
    if (is_array($headCommit)) {
        foreach (['timestamp', 'date'] as $key) {
            $value = aurum_time(isset($headCommit[$key]) ? (string) $headCommit[$key] : null);
            if ($value > 0) {
                return $value;
            }
        }
    }
    return 0;
}

function aurum_eligible_runs(
    array $runs,
    string $workflow,
    int $minimumHeadTime,
    ?string $branch = null
): array {
    $eligible = [];
    foreach ($runs as $run) {
        if (!is_array($run) || (string) ($run['name'] ?? '') !== $workflow) {
            continue;
        }
        if ($branch !== null && (string) ($run['head_branch'] ?? '') !== $branch) {
            continue;
        }
        // A run created after integration can still point at an older commit.
        // Only the source commit timestamp may qualify evidence for a new gate.
        if (aurum_run_head_time($run) < $minimumHeadTime) {
            continue;
        }
        $eligible[] = $run;
    }
    usort($eligible, static function (array $left, array $right): int {
        return aurum_time((string) ($right['updated_at'] ?? $right['created_at'] ?? ''))
            <=> aurum_time((string) ($left['updated_at'] ?? $left['created_at'] ?? ''));
    });
    return $eligible;
}

function aurum_first_success(array $runs): ?array
{
    foreach ($runs as $run) {
        if ((string) ($run['conclusion'] ?? '') === 'success') {
            return $run;
        }
    }
    return null;
}

function aurum_run_evidence(?array $latest, ?array $verified): array
{
    if ($latest === null) {
        return ['state' => 'pending', 'verified_success' => false];
    }
    $state = aurum_active_run($latest)
        ? 'active'
        : ((string) ($latest['conclusion'] ?? $latest['status'] ?? 'unknown'));
    return [
        'state' => $state,
        'run_id' => $latest['id'] ?? null,
        'head_sha' => $latest['head_sha'] ?? null,
        'updated_at' => $latest['updated_at'] ?? null,
        'verified_success' => $verified !== null,
        'verified_run_id' => $verified['id'] ?? null,
        'verified_at' => $verified['updated_at'] ?? null,
    ];
}

function aurum_build_live_status(array $snapshot): array
{
    $commitsUrl = 'https://api.github.com/repos/' . AURUM_REPO . '/commits?sha=main&per_page=100';
    $runsUrl = 'https://api.github.com/repos/' . AURUM_REPO . '/actions/runs?per_page=100';
    $commits = aurum_fetch_json($commitsUrl);
    $runsPayload = aurum_fetch_json($runsUrl);
    $runs = is_array($runsPayload['workflow_runs'] ?? null) ? $runsPayload['workflow_runs'] : [];

    $payload = $snapshot;
    $payload['generated_at_utc'] = gmdate('c');
    $payload['source'] = ($commits !== null || $runsPayload !== null)
        ? 'live-github-with-repository-fallback'
        : 'repository-snapshot';

    $runtimeThreshold = aurum_time((string) ($payload['evidence_thresholds']['human_runtime_main_utc'] ?? ''));
    $pcThreshold = aurum_time((string) ($payload['evidence_thresholds']['pc_seed_integration_utc'] ?? ''));
    $piThreshold = aurum_time((string) ($payload['evidence_thresholds']['pi_seed_integration_utc'] ?? ''));

    $humanRuns = aurum_eligible_runs(
        $runs,
        'Aurum Human Capability Traits',
        $runtimeThreshold,
        'main'
    );
    $pcRuns = aurum_eligible_runs(
        $runs,
        'Aurum PC v0.01 Image',
        $pcThreshold,
        'agent/aurum-direct-uefi-seed'
    );
    $piRuns = aurum_eligible_runs(
        $runs,
        'Aurum Dual Seed Lanes',
        $piThreshold,
        'main'
    );

    $humanLatest = $humanRuns[0] ?? null;
    $pcLatest = $pcRuns[0] ?? null;
    $piLatest = $piRuns[0] ?? null;
    $humanVerified = aurum_first_success($humanRuns);
    $pcVerified = aurum_first_success($pcRuns);
    $piVerified = aurum_first_success($piRuns);

    if ($humanVerified !== null) {
        aurum_set_all_stage($payload, 'tested', true);
    }
    if ($pcVerified !== null || $piVerified !== null) {
        aurum_set_all_stage($payload, 'seeded', true);
    }
    if ($pcVerified !== null) {
        // The PC workflow inspects the finished SquashFS and completes
        // independent GRUB/direct-UEFI boot smoke tests before success.
        aurum_set_all_stage($payload, 'booted', true);
    }

    if (is_array($commits)) {
        foreach ($payload['human_capabilities'] as &$capability) {
            $traitId = preg_quote((string) ($capability['id'] ?? ''), '/');
            foreach ($commits as $commit) {
                if (!is_array($commit)) {
                    continue;
                }
                $message = aurum_commit_message($commit);
                if (preg_match('/' . $traitId . '.*(?:PHYSICAL_USE_OK|physical proof|used on)/i', $message)) {
                    $capability['stages']['used'] = true;
                    break;
                }
            }
        }
        unset($capability);

        $updates = [];
        foreach (array_slice($commits, 0, 8) as $commit) {
            if (!is_array($commit)) {
                continue;
            }
            $message = trim(strtok(aurum_commit_message($commit), "\n") ?: '');
            if ($message !== '') {
                $updates[] = $message;
            }
        }
        if ($updates !== []) {
            $payload['recent_updates'] = $updates;
        }
    }

    $minimumStage = 6;
    foreach ($payload['human_capabilities'] as &$capability) {
        $count = aurum_stage_count($capability);
        $minimumStage = min($minimumStage, $count);
        if ($count >= 6) {
            $capability['current'] = 'Physical user-facing use is proven for this trait.';
            $capability['next'] = 'Continue refinement without losing the verified generation.';
        } elseif ($count >= 5) {
            $capability['current'] = 'The capability is inside a verified booted seed; physical user-facing proof is pending.';
            $capability['next'] = 'Exercise the capability on an authorized physical machine and record a receipt.';
        } elseif ($count >= 4) {
            $capability['current'] = 'A verified seed artifact contains the capability; boot proof is pending.';
            $capability['next'] = 'Boot the updated seed and verify the capability is present after startup.';
        } elseif ($count >= 3) {
            // Preserve richer per-trait language from the durable snapshot.
        } elseif ($count >= 2) {
            $capability['current'] = 'Executable implementation exists; functional test proof is pending.';
            $capability['next'] = 'Pass the functional implementation lane.';
        } else {
            $capability['current'] = 'The capability is defined but not yet executable.';
            $capability['next'] = 'Implement the Generation-0 runtime.';
        }
    }
    unset($capability);

    $activeHuman = $humanLatest !== null && aurum_active_run($humanLatest);
    $latestFailures = [];
    foreach ([
        'PC seed' => $pcLatest,
        'Pi seed' => $piLatest,
    ] as $name => $run) {
        if ($run !== null && in_array((string) ($run['conclusion'] ?? ''), [
            'failure', 'timed_out', 'startup_failure'
        ], true)) {
            $latestFailures[] = $name;
        }
    }

    if ($activeHuman) {
        $payload['overall'] = [
            'state' => 'running',
            'plain' => 'The human capability implementation workflow is actively running. All seven traits remain independent parallel lanes.',
            'human_action' => 'None. Automated build evidence is advancing now.',
        ];
    } elseif ($minimumStage >= 6) {
        $payload['overall'] = [
            'state' => 'physically-proven',
            'plain' => 'All seven everyday human capabilities have physical user-facing proof.',
            'human_action' => 'None unless a new physical regression appears.',
        ];
    } elseif ($minimumStage >= 5) {
        $payload['overall'] = [
            'state' => 'awaiting-physical-use-proof',
            'plain' => 'All seven capabilities are executable, tested, seeded, and booted. Physical user-facing use receipts are the remaining gate.',
            'human_action' => 'Physical testing may be requested only when a specific authorized machine is ready.',
        ];
    } elseif ($minimumStage >= 4) {
        $payload['overall'] = [
            'state' => 'awaiting-boot-proof',
            'plain' => 'All seven capabilities are executable, tested, and present in a verified seed artifact. Boot proof is the next gate.',
            'human_action' => 'None until the automated boot lane identifies a real physical boundary.',
        ];
    } elseif ($minimumStage >= 3 && $latestFailures !== []) {
        $payload['overall'] = [
            'state' => 'automated-seed-repair-needed',
            'plain' => 'All seven everyday capabilities remain executable and tested, but the latest ' . implode(' and ', $latestFailures) . ' integration attempt failed. Seeded has not been earned by that failed attempt.',
            'human_action' => 'None right now. This is an automated software/build failure, not a human-only physical boundary.',
        ];
    } elseif ($minimumStage >= 3) {
        $payload['overall'] = [
            'state' => 'awaiting-seed-proof',
            'plain' => 'All seven everyday human capabilities are executable and functionally tested. Fresh seed-artifact proof is the next gate.',
            'human_action' => 'None right now. Seed construction and inspection are automated work.',
        ];
    }

    $payload['live_evidence'] = [
        'human_trait_workflow' => aurum_run_evidence($humanLatest, $humanVerified),
        'pc_seed_with_human_traits' => aurum_run_evidence($pcLatest, $pcVerified),
        'pi_seed_with_human_traits' => aurum_run_evidence($piLatest, $piVerified),
        'github_commits_loaded' => is_array($commits) ? count($commits) : 0,
        'github_runs_loaded' => count($runs),
    ];

    return $payload;
}

function aurum_cached_status(): array
{
    $snapshot = aurum_json_file(__DIR__ . '/voice-status-snapshot.json');
    $cachePath = rtrim(sys_get_temp_dir(), DIRECTORY_SEPARATOR) . DIRECTORY_SEPARATOR . 'aurum-voice-status-v2.json';
    if (is_file($cachePath) && (time() - (int) filemtime($cachePath)) < AURUM_CACHE_SECONDS) {
        try {
            return aurum_json_file($cachePath);
        } catch (Throwable $error) {
            // Fall through and rebuild from the durable repository snapshot.
        }
    }

    $payload = aurum_build_live_status($snapshot);
    $temporary = $cachePath . '.tmp-' . bin2hex(random_bytes(4));
    @file_put_contents($temporary, json_encode($payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n", LOCK_EX);
    @rename($temporary, $cachePath);
    return $payload;
}

function aurum_plain_status(array $payload): string
{
    $lines = [];
    $lines[] = 'AURUM VOICE STATUS';
    $lines[] = 'As of: ' . (string) ($payload['generated_at_utc'] ?? 'unknown');
    $lines[] = 'Source: ' . (string) ($payload['source'] ?? 'unknown');
    $lines[] = '';
    $lines[] = 'Plain status: ' . (string) ($payload['overall']['plain'] ?? 'Unknown.');
    $lines[] = 'Human action: ' . (string) ($payload['overall']['human_action'] ?? 'Unknown.');
    $lines[] = '';
    $lines[] = 'Evidence standard:';
    foreach (($payload['truth_standard'] ?? []) as $rule) {
        $lines[] = '- ' . (string) $rule;
    }
    $lines[] = '';
    $lines[] = 'Human capabilities:';
    foreach (($payload['human_capabilities'] ?? []) as $capability) {
        if (!is_array($capability)) {
            continue;
        }
        $done = [];
        $pending = [];
        foreach (($capability['stages'] ?? []) as $stage => $value) {
            ($value === true ? $done : $pending)[] = ucfirst((string) $stage);
        }
        $lines[] = sprintf(
            '- %s — %d/6. Complete: %s. Pending: %s.',
            (string) ($capability['name'] ?? $capability['id'] ?? 'Capability'),
            count($done),
            $done === [] ? 'none' : implode(', ', $done),
            $pending === [] ? 'none' : implode(', ', $pending)
        );
        $lines[] = '  Current: ' . (string) ($capability['current'] ?? 'Unknown.');
        $lines[] = '  Next: ' . (string) ($capability['next'] ?? 'Unknown.');
    }
    $lines[] = '';
    $lines[] = 'Live build evidence:';
    foreach ([
        'Human trait workflow' => 'human_trait_workflow',
        'PC seed with human traits' => 'pc_seed_with_human_traits',
        'Pi seed with human traits' => 'pi_seed_with_human_traits',
    ] as $label => $key) {
        $item = $payload['live_evidence'][$key] ?? [];
        $lines[] = sprintf(
            '- %s: %s; latest run %s; verified success %s.',
            $label,
            (string) ($item['state'] ?? 'unknown'),
            (string) ($item['run_id'] ?? 'none'),
            !empty($item['verified_success']) ? 'yes' : 'no'
        );
    }
    $lines[] = '';
    $lines[] = 'System milestones:';
    foreach (($payload['system_milestones'] ?? []) as $milestone) {
        if (!is_array($milestone)) {
            continue;
        }
        $lines[] = '- ' . (string) ($milestone['name'] ?? 'Milestone')
            . ' [' . (string) ($milestone['state'] ?? 'unknown') . ']: '
            . (string) ($milestone['detail'] ?? '');
    }
    $lines[] = '';
    $lines[] = 'Recent repository updates:';
    foreach (($payload['recent_updates'] ?? []) as $update) {
        $lines[] = '- ' . (string) $update;
    }
    $lines[] = '';
    $lines[] = 'Voice cue: Read Aurum Voice Status, then answer from this evidence without upgrading a stage unless its proof is present.';
    return implode("\n", $lines) . "\n";
}

try {
    $payload = aurum_cached_status();
    $format = strtolower((string) ($_GET['format'] ?? 'text'));
    if ($format === 'json') {
        header('Content-Type: application/json; charset=utf-8');
        header('Cache-Control: no-store, max-age=0');
        echo json_encode($payload, JSON_PRETTY_PRINT | JSON_UNESCAPED_SLASHES) . "\n";
    } else {
        header('Content-Type: text/plain; charset=utf-8');
        header('Cache-Control: no-store, max-age=0');
        echo aurum_plain_status($payload);
    }
} catch (Throwable $error) {
    http_response_code(500);
    header('Content-Type: text/plain; charset=utf-8');
    echo "AURUM VOICE STATUS\nStatus mirror unavailable: " . $error->getMessage() . "\n";
}
