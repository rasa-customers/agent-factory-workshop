#!/usr/bin/env bash
# Bakes the cloud-machine image (Ubuntu 24.04). Run once as root on a fresh instance; provision.py does this.
#   REPO_URL=https://github.com/<org>/agent-factory-workshop bash bootstrap.sh
set -euxo pipefail
export DEBIAN_FRONTEND=noninteractive
export HOME="${HOME:-/root}"   # cloud-init runs user data without HOME; installers need it
apt-get update
apt-get install -y git curl build-essential lsof

id workshop >/dev/null 2>&1 || useradd -m -s /bin/bash workshop
sudo -u workshop bash -lc 'curl -LsSf https://astral.sh/uv/install.sh | sh'
sudo -u workshop bash -lc "git clone ${REPO_URL} /home/workshop/agent-factory-workshop || (cd /home/workshop/agent-factory-workshop && git pull)"
sudo -u workshop bash -lc 'cd ~/agent-factory-workshop && export PATH=$HOME/.local/bin:$PATH && ./setup.sh || true'
# Playwright's system deps need root
sudo -u workshop bash -lc 'cd ~/agent-factory-workshop && export PATH=$HOME/.local/bin:$PATH && uv run playwright install-deps chromium' || \
  (cd /home/workshop/agent-factory-workshop && /home/workshop/.local/bin/uv run playwright install-deps chromium)

# code-server (VS Code in the browser)
curl -fsSL https://code-server.dev/install.sh | sh
mkdir -p /home/workshop/.config/code-server
cat > /home/workshop/.config/code-server/config.yaml <<EOT
bind-addr: 0.0.0.0:8080
auth: password
password: $(openssl rand -hex 16)
cert: false
EOT
mkdir -p /home/workshop/.local/share/code-server/User
cat > /home/workshop/.local/share/code-server/User/settings.json <<'EOT'
{"workbench.startupEditor": "readme", "security.workspace.trust.enabled": false, "terminal.integrated.cwd": "/home/workshop/agent-factory-workshop"}
EOT
chown -R workshop:workshop /home/workshop/.config /home/workshop/.local
systemctl enable code-server@workshop

# `workshop up` as a service, started by the config agent once the machine is assigned
cat > /etc/systemd/system/workshop-up.service <<'EOT'
[Unit]
Description=Agent Factory workshop services
After=network-online.target
[Service]
User=workshop
WorkingDirectory=/home/workshop/agent-factory-workshop
Environment=PATH=/home/workshop/.local/bin:/usr/local/bin:/usr/bin:/bin
ExecStartPre=-/usr/bin/git pull --ff-only
ExecStartPre=-/home/workshop/.local/bin/uv sync
ExecStart=/home/workshop/.local/bin/uv run workshop up
Restart=on-failure
[Install]
WantedBy=multi-user.target
EOT

# The config agent: waits for an assignment from the portal, then writes .env and starts things
cat > /etc/systemd/system/factory-config-agent.service <<'EOT'
[Unit]
Description=Agent Factory config agent
After=network-online.target
ConditionPathExists=/etc/factory-workshop.env
[Service]
WorkingDirectory=/home/workshop/agent-factory-workshop
ExecStart=/usr/bin/python3 -m infra.vm.config_agent
Restart=always
[Install]
WantedBy=multi-user.target
EOT
systemctl daemon-reload
systemctl enable factory-config-agent
echo "bootstrap complete"
