#Requires -Version 5.1
Set-StrictMode -Version Latest

$gen11Extension = Join-Path $PSScriptRoot 'aurum-pi4-driver-gen11-extension.ps1'
if (-not (Test-Path -LiteralPath $gen11Extension -PathType Leaf)) {
    throw "Missing Aurum Pi4 generation-11 extension: $gen11Extension"
}
. $gen11Extension

if ($trialGeneration -ge 12) {
    $shutdownFunction = @'
static void aurum_shutdown(struct platform_device *pdev)
{
    struct aurum_leds *priv = platform_get_drvdata(pdev);
    int i;

    if (!priv)
        return;

    for (i = 0; i < priv->count; i++) {
        struct aurum_led *led = &priv->leds[i];

        if (!(led->cdev.flags & LED_RETAIN_AT_SHUTDOWN))
            aurum_led_set(&led->cdev, LED_OFF);
    }
}

'@

    $generation12Patches = @(
        [pscustomobject]@{
            Old = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10, 11}:'
            New = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10, 11, 12}:'
        },
        [pscustomobject]@{
            Old = '            11: "reference-aligned GPIO direction-flag handling, unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and learned Pi readback semantics",'
            New = '            11: "reference-aligned GPIO direction-flag handling, unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and learned Pi readback semantics",' + "`n" + '            12: "reference-aligned shutdown LED policy, GPIO direction-flag handling, unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and learned Pi readback semantics",'
        },
        [pscustomobject]@{
            Old = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11}:'
            New = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12}:'
        },
        [pscustomobject]@{
            Old = '        11: "reference-aligned GPIO direction-flag handling plus unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and reference-compatible readback",'
            New = '        11: "reference-aligned GPIO direction-flag handling plus unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and reference-compatible readback",' + "`n" + '        12: "reference-aligned shutdown LED policy plus GPIO direction-flag handling, unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and reference-compatible readback",'
        },
        [pscustomobject]@{
            Old = 'static const struct of_device_id aurum_of_match[] = {'
            New = $shutdownFunction + 'static const struct of_device_id aurum_of_match[] = {'
        },
        [pscustomobject]@{
            Old = '    .probe = aurum_probe,'
            New = '    .probe = aurum_probe,' + "`n" + '    .shutdown = aurum_shutdown,'
        },
        [pscustomobject]@{
            Old = '        "gpio_direction_flag_aware": generation >= 11,'
            New = '        "gpio_direction_flag_aware": generation >= 11,' + "`n" + '        "shutdown_led_policy_aware": generation >= 12,'
        }
    )

    foreach ($patch in $generation12Patches) {
        if (-not $controlledGenerator.Contains($patch.Old)) {
            throw "Could not apply bounded generation-12 synthesizer patch: $($patch.Old)"
        }
        $controlledGenerator = $controlledGenerator.Replace($patch.Old, $patch.New)
    }

    Write-Host "AURUM_PI4_DRIVER_GEN12 reference=shutdown-led-policy source=raspberrypi-linux-rpi-6.12.y bounded=true live_shutdown_exercised=false"
}
