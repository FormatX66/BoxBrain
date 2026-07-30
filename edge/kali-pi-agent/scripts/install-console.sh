#!/bin/sh
set -eu
umask 022

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this installer with sudo." >&2
    exit 1
fi

console_user=kali
novnc_version=1.7.0
novnc_archive_sha256=b1003a11b6e6e8d8f7f5e5586daae7f8ca651d8aee0aa155ff9ac841c48f52c6
novnc_url="https://github.com/novnc/noVNC/archive/refs/tags/v${novnc_version}.tar.gz"
console_root=/opt/boxbrain/pi-console
version_directory="$console_root/noVNC-$novnc_version"
project_dir=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)

if ! id "$console_user" >/dev/null 2>&1; then
    echo "The required local account '$console_user' does not exist." >&2
    exit 1
fi

missing=
for command in \
    curl dbus-run-session install ip python3 sha256sum ss \
    startxfce4 systemctl systemd-run tar websockify Xtightvnc
do
    if ! command -v "$command" >/dev/null 2>&1; then
        missing="$missing $command"
    fi
done
if [ -n "$missing" ]; then
    echo "Pi console prerequisites are missing:$missing" >&2
    echo "No packages were installed. Install or approve them separately, then retry." >&2
    exit 1
fi

install -d -o root -g root -m 0755 "$console_root"

if [ -e "$version_directory" ]; then
    if (
        [ -f "$version_directory/vnc.html" ] &&
        [ -f "$version_directory/LICENSE.txt" ] &&
        grep -q "^archive_sha256=$novnc_archive_sha256$" \
            "$version_directory/BOXBRAIN_PROVENANCE"
    ); then
        printf 'Verified existing noVNC %s installation.\n' "$novnc_version"
    else
        echo "Refusing to replace the unverified path $version_directory." >&2
        exit 1
    fi
else
    temporary_directory=$(mktemp -d /tmp/boxbrain-console.XXXXXX)
    trap 'rm -rf -- "$temporary_directory"' EXIT HUP INT TERM
    archive="$temporary_directory/noVNC.tar.gz"
    extraction_root="$temporary_directory/extracted"
    mkdir "$extraction_root"

    curl \
        --fail \
        --location \
        --proto '=https' \
        --tlsv1.2 \
        --output "$archive" \
        "$novnc_url"
    printf '%s  %s\n' "$novnc_archive_sha256" "$archive" | sha256sum -c -

    tar -tzf "$archive" |
        while IFS= read -r entry; do
            case "$entry" in
                /*|../*|*/../*)
                    echo "Unsafe archive entry: $entry" >&2
                    exit 1
                    ;;
            esac
        done
    tar -xzf "$archive" -C "$extraction_root"
    extracted="$extraction_root/noVNC-$novnc_version"
    test -f "$extracted/vnc.html"
    test -f "$extracted/LICENSE.txt"

    cat >"$extracted/BOXBRAIN_PROVENANCE" <<EOF
name=noVNC
version=$novnc_version
source=$novnc_url
archive_sha256=$novnc_archive_sha256
license=MPL-2.0
EOF
    chown -R root:root "$extracted"
    find "$extracted" -type d -exec chmod 0755 {} \;
    find "$extracted" -type f -exec chmod 0644 {} \;
    mv "$extracted" "$version_directory"
    printf 'Installed verified noVNC %s.\n' "$novnc_version"
fi

ln -sfn "noVNC-$novnc_version" "$console_root/current"
install -o root -g root -m 0755 \
    "$project_dir/scripts/start-console.sh" \
    /usr/local/bin/boxbrain-console-start
install -o root -g root -m 0755 \
    "$project_dir/scripts/stop-console.sh" \
    /usr/local/bin/boxbrain-console-stop

if [ ! -e /etc/boxbrain/console.env ]; then
    install -d -o root -g root -m 0755 /etc/boxbrain
    cat >/etc/boxbrain/console.env <<'EOF'
BOXBRAIN_CONSOLE_BIND=10.12.194.1
BOXBRAIN_CONSOLE_VIEWER_PORT=8790
EOF
    chown root:root /etc/boxbrain/console.env
    chmod 0644 /etc/boxbrain/console.env
fi

printf '%s\n' \
    "BoxBrain Pi console installed but not started or enabled at boot." \
    "Start explicitly with: sudo /usr/local/bin/boxbrain-console-start"
