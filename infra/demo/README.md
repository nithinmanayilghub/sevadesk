# Demo server runbook

The always-on demo runs on one Oracle Cloud ARM VM. Postgres is Neon (outside the VM).
After set-up, every merge to main deploys by itself (CI job `deploy`).

What runs where:

| Where | What |
|---|---|
| Oracle VM `/opt/sevadesk/` | `docker-compose.yml`, `Caddyfile`, `otel-collector.yaml`, `deploy.sh` (CI copies these), `.env` (you write it once, never in git) |
| Neon | the Postgres database |
| Grafana Cloud | traces and logs |
| GitHub environment `demo` | SSH key, server identity, IP, domain |

## One-time set-up

Do the parts in order. Never paste a password, token, or private key into a chat or an issue.

### 1. Oracle account

1. Sign up at cloud.oracle.com. Pick the **home region** with care: you cannot change it later, and free ARM VMs live only there. Pick **India South (Hyderabad)** or **India West (Mumbai)**.
2. Billing → **Upgrade to Pay As You Go**. You stay at $0 while you use only Always Free resources. Oracle does not take back idle VMs on this tier.
3. Billing → Budgets → **Create budget**: $1 per month, alert at 100% to your email. Any charge then sends you an email.

### 2. The VM

Compute → Instances → Create instance:

- Image: **Canonical Ubuntu 24.04** (aarch64).
- Shape: Ampere **VM.Standard.A1.Flex**, 4 OCPU, 24 GB memory (the whole free ARM allowance).
- Networking: a new VCN with a public subnet; **assign a public IPv4 address**.
- SSH keys: upload YOUR public key (for example `~/.ssh/id_ed25519.pub`).
- Boot volume: 50 GB.

"Out of capacity" error: try another availability domain, or try again later.

Note the **public IP**. Your domain is that IP with dashes plus `.sslip.io`.
Example: IP `140.238.1.2` → `140-238-1-2.sslip.io`.

### 3. Firewall (two layers)

1. Oracle side: Networking → your VCN → the public subnet's **security list** → add ingress rules from `0.0.0.0/0`: TCP 80, TCP 443, UDP 443. (Port 22 is already open.)
2. VM side: Oracle's Ubuntu image has its own iptables rules that block 80/443. Log in (`ssh ubuntu@<ip>`) and run:

```bash
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 80 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p tcp --dport 443 -j ACCEPT
sudo iptables -I INPUT 6 -m state --state NEW -p udp --dport 443 -j ACCEPT
sudo netfilter-persistent save
```

### 4. Docker

On the VM:

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker ubuntu
sudo mkdir -p /opt/sevadesk && sudo chown ubuntu: /opt/sevadesk
exit
```

Log in again, then check: `docker compose version` prints a version.

### 5. Neon and the `.env` file

1. Sign up at neon.tech. Create a project `sevadesk`, Postgres **18**, region = the one closest to your Oracle region (Neon has no India region today; Singapore is closest).
2. Connect → copy the connection string with **connection pooling OFF** (the host has no `-pooler`).
3. Change the start from `postgresql://` to `postgresql+psycopg://`. Keep `?sslmode=require`.
4. Grafana Cloud: **make a new access token** (revoke the old one). Build the auth value as in `infra/compose/.env.example`.
5. On the VM: copy `infra/demo/.env.example` to `/opt/sevadesk/.env`, fill all four values, then `chmod 600 /opt/sevadesk/.env`.

### 6. Deploy key (CI's own SSH key)

On your PC (WSL):

```bash
ssh-keygen -t ed25519 -f ~/sevadesk-deploy -N "" -C "github-deploy"
ssh-copy-id -i ~/sevadesk-deploy.pub ubuntu@<ip>
ssh-keyscan -t ed25519 <ip>          # the output is the "known_hosts" value (public, safe)
```

### 7. GitHub environment

Repo → Settings → Environments → **New environment** `demo`:

- Secrets: `DEMO_SSH_KEY` = the full content of `~/sevadesk-deploy` (the private key); `DEMO_SSH_KNOWN_HOSTS` = the `ssh-keyscan` output.
- Variables: `DEMO_HOST` = the IP; `DEMO_DOMAIN` = the sslip.io name.

Then delete the private key from your PC: `rm ~/sevadesk-deploy`.

### 8. Public images

The VM pulls images with no login, so the packages must be public (they hold no secrets).
GitHub → your profile → Packages → `sevadesk-backend` → Package settings → Change visibility → **Public**. Same for `sevadesk-frontend`. Delete the old `sevadesk-worker` package.

## Deploy by hand

From the repo root (WSL), with `<sha>` = a full commit SHA on main whose images exist in GHCR:

```bash
scp infra/demo/docker-compose.yml infra/demo/Caddyfile infra/demo/deploy.sh \
    infra/compose/otel-collector.yaml ubuntu@<ip>:/opt/sevadesk/
ssh ubuntu@<ip> /opt/sevadesk/deploy.sh <sha>
```

## Look at the running demo

```bash
ssh ubuntu@<ip>
cd /opt/sevadesk
# compose needs IMAGE_TAG: read it from the running backend container's image name.
export IMAGE_TAG=$(docker ps --filter label=com.docker.compose.service=backend --format '{{.Image}}' | cut -d: -f2)
docker compose ps                 # every container and its health
docker compose logs -f backend    # JSON logs (also in Grafana Cloud)
```

## Known limits

- If the new version fails its health wait, the old containers are already replaced. Fix forward with a new commit.
- A migration that drops or renames something the OLD code still uses breaks the old version during the deploy. Use expand/contract (Epic 2).
- SSH port 22 is open to the internet (GitHub's IPs change). Only key login works.
- The sslip.io name changes if the VM's public IP changes. Then update `.env` and the GitHub variable.
