#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

# Conservative defaults for a single-user Xray host.
# This script does not disable IPv6, open random ports, or install remote code.

[[ $EUID -eq 0 ]] || { echo "Run as root: sudo bash scripts/harden-host.sh" >&2; exit 1; }
command -v apt-get >/dev/null || { echo "Debian/Ubuntu is required" >&2; exit 1; }

export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ca-certificates curl jq openssl iproute2 dnsutils unattended-upgrades

install -d -m 0755 /etc/sysctl.d
cat >/etc/sysctl.d/99-autovless-resilience.conf <<'EOF'
# Keep TCP behavior conventional and stable under loss; avoid fingerprintable hacks.
net.ipv4.tcp_congestion_control = bbr
net.core.default_qdisc = fq
net.ipv4.tcp_mtu_probing = 1
net.ipv4.tcp_keepalive_time = 300
net.ipv4.tcp_keepalive_intvl = 30
net.ipv4.tcp_keepalive_probes = 5
# Do not route or accept IPv6 unless the operator has explicitly configured it.
net.ipv6.conf.all.accept_ra = 0
net.ipv6.conf.default.accept_ra = 0
EOF
sysctl --system >/dev/null

# Keep SSH available, and expose only standard web ports plus the existing panel ports.
if command -v ufw >/dev/null; then
  ufw default deny incoming
  ufw default allow outgoing
  ufw allow 22/tcp
  ufw allow 80/tcp
  ufw allow 443/tcp
  ufw --force enable
fi

systemctl enable --now unattended-upgrades >/dev/null 2>&1 || true
printf '%s\n' 'Host hardening applied. Configure Xray through 3x-ui; do not paste secrets into Git.'
