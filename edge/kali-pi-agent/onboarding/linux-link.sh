#!/bin/sh
# BoxBrain target link for Linux.
# Review this file before running it. It creates a non-sudo system user and
# authorizes one BoxBrain public key.
set -eu

if [ "$(id -u)" -ne 0 ]; then
    echo "Run this script with sudo." >&2
    exit 1
fi

printf '\nBOXBRAIN AUTHORIZATION\n'
printf '%s\n' \
    'This will enable SSH and create a non-sudo account named boxbrain-link.' \
    'Only use this on a computer you own or are authorized to assess.'
printf 'Type AUTHORIZE to continue: '
IFS= read -r approval
if [ "$approval" != "AUTHORIZE" ]; then
    echo "Authorization was not confirmed. No changes were made." >&2
    exit 1
fi

public_key='__BOXBRAIN_PUBLIC_KEY__'

if ! command -v sshd >/dev/null 2>&1; then
    if command -v apt-get >/dev/null 2>&1; then
        apt-get update
        DEBIAN_FRONTEND=noninteractive apt-get install -y openssh-server
    elif command -v dnf >/dev/null 2>&1; then
        dnf install -y openssh-server
    else
        echo "Install OpenSSH Server, then run this script again." >&2
        exit 1
    fi
fi

if ! id boxbrain-link >/dev/null 2>&1; then
    useradd --create-home --user-group --shell /bin/sh boxbrain-link
fi
if passwd --status boxbrain-link 2>/dev/null | grep -q ' L '; then
    random_password=$(od -An -N32 -tx1 /dev/urandom | tr -d ' \n')
    printf 'boxbrain-link:%s\n' "$random_password" | chpasswd
    unset random_password
fi

home_dir=$(getent passwd boxbrain-link | cut -d: -f6)
install -d -o boxbrain-link -g boxbrain-link -m 0700 "$home_dir/.ssh"
printf '%s\n' "$public_key" >"$home_dir/.ssh/authorized_keys"
chown boxbrain-link:boxbrain-link "$home_dir/.ssh/authorized_keys"
chmod 0600 "$home_dir/.ssh/authorized_keys"

config_dir=/etc/ssh/sshd_config.d
config_file="$config_dir/90-boxbrain-link.conf"
install -d -o root -g root -m 0755 "$config_dir"
if [ ! -e "$config_file" ]; then
    {
        printf '%s\n' \
            '# BoxBrain managed SSH restrictions' \
            'Match User boxbrain-link' \
            '    AuthenticationMethods publickey' \
            '    PasswordAuthentication no' \
            '    KbdInteractiveAuthentication no' \
            '    PermitTTY no' \
            '    AllowTcpForwarding no' \
            '    X11Forwarding no' \
            '    PermitTunnel no'
    } >"$config_file"
    chmod 0644 "$config_file"
fi

sshd -t
if systemctl list-unit-files ssh.service >/dev/null 2>&1; then
    systemctl enable --now ssh.service
else
    systemctl enable --now sshd.service
fi
systemctl reload ssh.service 2>/dev/null || systemctl reload sshd.service

printf '\nBoxBrain link authorized.\n'
printf '%s\n' \
    'The boxbrain-link account has no sudo access.' \
    'Keep this USB connection attached; BoxBrain will confirm the SSH link.'
