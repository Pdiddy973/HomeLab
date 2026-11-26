# HomeServer

The Docker Compose files, example settings and Ansible runbooks behind my homelab, kept here so any machine can be rebuilt from scratch. Secrets are **never** stored here: every `.env.example` lists the settings a stack needs, with the values blanked.

## The lab

Hosts are named for planets and their guests for that planet's moons.

| Host | What it is | Runs |
| --- | --- | --- |
| jupiter | Proxmox host in the main rack | TrueNAS (ganymede), Plex (io), the Arr stack (europa), apps (callisto), Home Assistant (phobos), TangleBot (leda), secrets (rhea), runbooks (iapetus), game servers |
| saturn | Proxmox host in the network rack (planned) | The 24/7 guests: Home Assistant, the VPN, network boot, secrets, runbooks |
| juno | DigitalOcean droplet | Relay for the game servers, Uptime Kuma |

## Layout

```
hosts/
  <host>/
    <stack>/
      docker-compose.yml
      .env.example
ansible/           inventory and playbooks that Semaphore on iapetus runs
legacy/            older stacks from before the rebuild
scripts/
  sync.py          pulls files from the hosts and strips secrets
  manifest.txt     which files to pull
```

## Rebuilding a host

1. Build the host and install Docker.
2. Copy the stack folder to `/opt/stacks/<stack>` on it.
3. Copy `.env.example` to `.env` and fill in the real values from the secrets server or the password manager.
4. `chmod 600 .env && docker compose up -d`

## Keeping it up to date

`python3 scripts/sync.py` pulls the files over SSH, replaces every secret with `CHANGE_ME`, refuses to continue if anything still looks like a secret, and shows what changed. Nothing is published until the diff is reviewed and pushed. A gitleaks check runs on every push.
