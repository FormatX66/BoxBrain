from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "aurum-pi3-adaptive-kernel-overnight.yml"
HARNESS = ROOT / "Projects" / "AdaptiveKernel" / "pi3_overnight_lab.py"


def test_workflow_is_six_hour_bounded_and_leaves_artifact_time():
    text = WORKFLOW.read_text(encoding="utf-8")
    assert "timeout-minutes: 360" in text
    assert "default: 330" in text
    assert "-gt 330" in text


def test_workflow_requires_exact_backup_and_physical_identity():
    text = WORKFLOW.read_text(encoding="utf-8")
    for value in (
        "169.254.129.122",
        "00000000a6a7df7f",
        "Raspberry Pi 3 Model B Rev 1.2",
        "61a4c6bfc03e7ea3444ce67de20c506dbc57a7fc7e34da250b3bfab8d2845c62",
        "c45bb76d88867b1c3552791f9b992068bccd2c9f2f9b83c2fcab3d0cc79ee984",
        "smsc95xx",
        "/dev/mmcblk0p2",
    ):
        assert value in text


def test_workflow_is_strict_key_only_and_never_scans():
    text = WORKFLOW.read_text(encoding="utf-8")
    for value in (
        "BatchMode=yes",
        "PasswordAuthentication=no",
        "KbdInteractiveAuthentication=no",
        "PreferredAuthentications=publickey",
        "IdentitiesOnly=yes",
        "StrictHostKeyChecking=yes",
        "UserKnownHostsFile=",
    ):
        assert value in text
    assert "StrictHostKeyChecking=no" not in text
    assert "accept-new" not in text
    assert "nmap" not in text.lower()


def test_mutation_stages_are_ordered_and_locally_rolled_back():
    text = HARNESS.read_text(encoding="utf-8")
    indexes = [text.index(f'"{name}"') for name in (
        "observe",
        "userspace-adaptation",
        "virtual-driver",
        "exact-header-module",
        "smsc95xx-feature-canary",
    )]
    assert indexes == sorted(indexes)
    assert "systemd-run" in text
    assert "--on-active=" in text
    assert '"persistent_kernel_or_driver_change": False' in text
    assert '"replacement_kernel_installed": False' in text


def test_official_schematic_and_upstream_driver_are_recorded():
    text = HARNESS.read_text(encoding="utf-8")
    assert "https://pip.raspberrypi.com/documents/RP-008340-DS" in text
    assert "raspberrypi/linux/blob/rpi-6.18.y/drivers/net/usb/smsc95xx.c" in text
