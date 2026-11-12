# Demo server runbook

The always-on demo runs on one DigitalOcean droplet (a rented VM). Postgres is Neon (outside the VM).
After set-up, every merge to main deploys by itself (CI job `deploy`).

What runs where:

| Where | What |
|---|---|
| Droplet `/opt/sevadesk/` | `docker-compose.yml`, `Caddyfile`, `otel-collector.yaml`, `deploy.sh` (CI copies these), `.env` (you write it once, never in git) |
| Neon | the Postgres database |
| Grafana Cloud | traces and logs |
| GitHub environment `demo` | SSH key, server identity, IP, domain |

Size: 2 GB memory is enough. Measured on 2026-11-12: all 6 containers use about 300 MB; the whole server about 740 MB.

## One-time set-up

Do the parts in order. Never paste a password, token, or private key into a chat, an issue, or a screenshot.
"WSL" = your laptop. "On the server" = after `ssh` into the droplet.

### 1. SSH key for you (WSL)

```bash
ssh-keygen -t ed25519 -f ~/.ssh/id_do -N "" -C "my-laptop"
cat ~/.ssh/id_do.pub          # the public half: safe to share
```

Optional shortcut, so `ssh sevadesk` is enough later (replace `<ip>` after part 2):

```bash
cat >> ~/.ssh/config <<'EOF'
Host sevadesk
  HostName <ip>
  User ubuntu
  IdentityFile ~/.ssh/id_do
EOF
```

### 2. The droplet

DigitalOcean → Create → Droplets:

- Region: **Bangalore (BLR1)**. Image: **Ubuntu 24.04 (LTS) x64**.
- Size: **Basic → Regular → 2 GB / 1 vCPU / 50 GB** ($12/month, billed per hour, no contract).
- Authentication: **SSH key** → paste `~/.ssh/id_do.pub`.
- Backups and extra volumes: off. Name: `sevadesk-demo`.

Note the **public IPv4**. Your domain is that IP with dashes plus `.sslip.io`.
Example: IP `168.144.155.227` → `168-144-155-227.sslip.io`.

No firewall step: a new droplet has no firewall, so ports 22, 80 and 443 are open.

Locked out (lost key)? Droplet page → **Web Console** logs you in as root in the browser. Add a new public key to `~/.ssh/authorized_keys` there.

### 3. User `ubuntu`, swap, Docker

A droplet starts with only `root`. CI logs in as `ubuntu`, so make that user. Log in once as root (`ssh -i ~/.ssh/id_do root@<ip>`), then:

```bash
adduser --disabled-password --gecos "" ubuntu
usermod -aG sudo ubuntu
echo "ubuntu ALL=(ALL) NOPASSWD:ALL" > /etc/sudoers.d/90-ubuntu
chmod 440 /etc/sudoers.d/90-ubuntu
mkdir -p /home/ubuntu/.ssh
cp /root/.ssh/authorized_keys /home/ubuntu/.ssh/
chown -R ubuntu:ubuntu /home/ubuntu/.ssh
chmod 700 /home/ubuntu/.ssh
chmod 600 /home/ubuntu/.ssh/authorized_keys
exit
```

Log in as `ubuntu` (`ssh -i ~/.ssh/id_do ubuntu@<ip>`). Add 2 GB swap (disk used as spare memory, for the deploy peak):

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
echo 'vm.swappiness=10' | sudo tee /etc/sysctl.d/99-swappiness.conf
sudo sysctl -p /etc/sysctl.d/99-swappiness.conf
free -h                         # "Swap: 2.0Gi"
```

Docker and the app folder:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
sudo mkdir -p /opt/sevadesk
sudo chown ubuntu: /opt/sevadesk
sudo reboot                     # applies updates; log in again after 1 minute
```

Check: `docker compose version` prints a version, and `free -h` still shows the swap.

### 4. Neon, Grafana, and the `.env` file

1. Neon (neon.tech): project `sevadesk`, Postgres **18**, region **Singapore** (closest to India). Connect → connection string with **connection pooling OFF** (no `-pooler` in the host). Change `postgresql://` to `postgresql+psycopg://`. Keep `?sslmode=require`.
2. Grafana Cloud: make an access token for the demo (scopes: write traces/logs). Note the stack's **instance ID** (a number) and the OTLP **endpoint**.
3. On the server, write the file with empty places:

```bash
cat > /opt/sevadesk/.env <<'EOF'
DEMO_DOMAIN=<ip-with-dashes>.sslip.io
DATABASE_URL=
OTLP_EXPORT_ENDPOINT=
OTLP_EXPORT_AUTH=
EOF
chmod 600 /opt/sevadesk/.env
```

4. `DATABASE_URL`: `nano /opt/sevadesk/.env`, go to the end of that line, paste, then Ctrl+O, Enter, Ctrl+X.
5. Endpoint (not secret):

```bash
sed -i 's|^OTLP_EXPORT_ENDPOINT=.*|OTLP_EXPORT_ENDPOINT=<endpoint>|' /opt/sevadesk/.env
```

6. Auth (the token is never shown or saved in shell history):

```bash
read -rsp "Paste the Grafana token, then press Enter: " TOK; echo
AUTH="Basic $(printf '<instance-id>:%s' "$TOK" | base64 -w0)"
sed -i "s|^OTLP_EXPORT_AUTH=.*|OTLP_EXPORT_AUTH=$AUTH|" /opt/sevadesk/.env
unset TOK AUTH
```

7. Checks that show no secrets:

```bash
cut -d= -f1 /opt/sevadesk/.env                    # the 4 names
grep -c '^[A-Z_]*=$' /opt/sevadesk/.env           # 0 = no empty value
grep -c 'pooler' /opt/sevadesk/.env               # 0
ls -l /opt/sevadesk/.env                          # -rw------- ubuntu
```

(Do not check with `grep '=$'`: base64 values often end with `=`, so it counts a good line.)

### 5. Deploy key (CI's own SSH key)

In WSL:

```bash
ssh-keygen -t ed25519 -f ~/sevadesk-deploy -N "" -C "github-deploy"
cat ~/sevadesk-deploy.pub | ssh -i ~/.ssh/id_do ubuntu@<ip> 'cat >> ~/.ssh/authorized_keys'
ssh -i ~/sevadesk-deploy ubuntu@<ip> echo deploy-key-works
```

### 6. GitHub environment

Repo → Settings → Environments → **New environment** `demo`. The page has two sections. Use the right one:

| Name | Section | Value |
|---|---|---|
| `DEMO_SSH_KEY` | **Environment secrets** | the full content of `~/sevadesk-deploy` (the private key) |
| `DEMO_SSH_KNOWN_HOSTS` | **Environment secrets** | output of `ssh-keyscan -t ed25519 <ip>` (one line: IP, `ssh-ed25519`, key) |
| `DEMO_HOST` | **Environment variables** | the IP |
| `DEMO_DOMAIN` | **Environment variables** | the sslip.io name |

The CI file reads the first two from `secrets`, the last two from `vars`. In the wrong section, the deploy cannot find them.
From WSL, `ssh-keyscan -t ed25519 <ip> 2>/dev/null | clip.exe` puts the line in the Windows clipboard.

Then delete the private key from your PC: `rm ~/sevadesk-deploy`.

### 7. Public images

The server pulls images with no login, so the packages must be public (they hold no secrets).
GitHub → your profile → Packages → `sevadesk-backend` and `sevadesk-frontend` → each shows a **Public** badge. If not: Package settings → Change visibility → Public.

## Deploy by hand

From the repo root (WSL), with `<sha>` = a full commit SHA on main whose images exist in GHCR:

```bash
scp -i ~/.ssh/id_do infra/demo/docker-compose.yml infra/demo/Caddyfile infra/demo/deploy.sh \
    infra/compose/otel-collector.yaml ubuntu@<ip>:/opt/sevadesk/
ssh -i ~/.ssh/id_do ubuntu@<ip> /opt/sevadesk/deploy.sh <sha>
```

## Look at the running demo

```bash
ssh -i ~/.ssh/id_do ubuntu@<ip>
cd /opt/sevadesk
# compose needs IMAGE_TAG: read it from the running backend container's image name.
export IMAGE_TAG=$(docker ps --filter label=com.docker.compose.service=backend --format '{{.Image}}' | cut -d: -f2)
docker compose ps                 # every container and its health
docker compose logs -f backend    # JSON logs (also in Grafana Cloud)
docker stats --no-stream          # memory per container
free -h                           # memory of the whole server
```

## Known limits

- If the new version fails its health wait, the old containers are already replaced. Fix forward with a new commit.
- A migration that drops or renames something the OLD code still uses breaks the old version during the deploy. Use expand/contract (Epic 2).
- SSH port 22 is open to the internet (GitHub's IPs change). Only key login works.
- The sslip.io name changes if the droplet's IP changes (only when you destroy and re-create it). Then update `.env` and the GitHub variables.
- Out of memory later: Droplet → Resize → **CPU and RAM only** to 4 GB (keeps the option to go back down).
