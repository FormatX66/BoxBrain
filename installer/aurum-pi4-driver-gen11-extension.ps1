#Requires -Version 5.1
Set-StrictMode -Version Latest

if ($trialGeneration -ge 11) {
    $generation11Patches = @(
        [pscustomobject]@{
            Old = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10}:'
            New = 'elif generation in {3, 4, 5, 6, 7, 8, 9, 10, 11}:'
        },
        [pscustomobject]@{
            Old = @'
        set_functions = '''static void aurum_led_set(struct led_classdev *cdev, enum led_brightness value)
{
    struct aurum_led *led = container_of(cdev, struct aurum_led, cdev);
    int level = value == LED_OFF ? 0 : 1;

    if (led->can_sleep)
        gpiod_set_value_cansleep(led->gpiod, level);
    else
        gpiod_set_value(led->gpiod, level);
}

static int aurum_led_set_blocking(struct led_classdev *cdev, enum led_brightness value)
{
    aurum_led_set(cdev, value);
    return 0;
}
'''
'@
            New = @'
        set_functions = '''static void aurum_led_set(struct led_classdev *cdev, enum led_brightness value)
{
    struct aurum_led *led = container_of(cdev, struct aurum_led, cdev);
    int level = value == LED_OFF ? 0 : 1;

    if (led->cdev.flags & SET_GPIO_INPUT) {
        gpiod_direction_input(led->gpiod);
        led->cdev.flags &= ~SET_GPIO_INPUT;
    } else if (led->cdev.flags & SET_GPIO_OUTPUT) {
        gpiod_direction_output(led->gpiod, level);
        led->cdev.flags &= ~SET_GPIO_OUTPUT;
    } else if (led->can_sleep ||
               (led->cdev.flags & (SET_GPIO_INPUT | SET_GPIO_OUTPUT))) {
        gpiod_set_value_cansleep(led->gpiod, level);
    } else {
        gpiod_set_value(led->gpiod, level);
    }
}

static int aurum_led_set_blocking(struct led_classdev *cdev, enum led_brightness value)
{
    aurum_led_set(cdev, value);
    return 0;
}
'''
'@
        },
        [pscustomobject]@{
            Old = '            10: "reference-aligned unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and learned Pi readback semantics",'
            New = '            10: "reference-aligned unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and learned Pi readback semantics",' + "`n" + '            11: "reference-aligned GPIO direction-flag handling, unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and learned Pi readback semantics",'
        },
        [pscustomobject]@{
            Old = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10}:'
            New = 'if generation not in {1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11}:'
        },
        [pscustomobject]@{
            Old = '        10: "reference-aligned unified LED setter dispatch plus counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and reference-compatible readback",'
            New = '        10: "reference-aligned unified LED setter dispatch plus counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and reference-compatible readback",' + "`n" + '        11: "reference-aligned GPIO direction-flag handling plus unified LED setter dispatch, counted flexible-array metadata, topology-sized overflow-safe LED allocation, LED default pinctrl selection, GPIO consumer identity, firmware LED policy flags, default-state initialization, sleep-aware GPIO LED writes, and reference-compatible readback",'
        },
        [pscustomobject]@{
            Old = '        "unified_led_setter_dispatch": generation >= 10,'
            New = '        "unified_led_setter_dispatch": generation >= 10,' + "`n" + '        "gpio_direction_flag_aware": generation >= 11,'
        }
    )

    foreach ($patch in $generation11Patches) {
        if (-not $controlledGenerator.Contains($patch.Old)) {
            throw "Could not apply bounded generation-11 synthesizer patch: $($patch.Old)"
        }
        $controlledGenerator = $controlledGenerator.Replace($patch.Old, $patch.New)
    }

    Write-Host "AURUM_PI4_DRIVER_GEN11 reference=gpio-direction-flags source=raspberrypi-linux-rpi-6.12.y bounded=true"
}
