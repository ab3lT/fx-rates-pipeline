# Deploying to a VPS

Target: an Ubuntu/Debian VPS with a domain (or subdomain) pointing at it. The stack runs in
Docker Compose; nginx on the host terminates HTTPS and proxies to the dashboard.

```
 internet ──► nginx :443 ──► web (gunicorn) 127.0.0.1:8000 ──► db (PostgreSQL, private network)
                                   scheduler ──────────────────┘
```

## 1. Install Docker, nginx and certbot (once)

```bash
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker $USER        # log out and back in after this
sudo apt-get install -y nginx certbot python3-certbot-nginx
```

## 2. Get the code onto the server

```bash
git clone https://github.com/ab3lT/fx-rates-etl.git ~/fx-rates-etl
cd ~/fx-rates-etl
```

(Or `rsync -av --exclude .git ./ user@server:~/fx-rates-etl/` from your machine.)

## 3. Configure secrets

```bash
cp .env.prod.example .env.prod
sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$(openssl rand -hex 24)/" .env.prod
sed -i "s/^FX_ADMIN_TOKEN=.*/FX_ADMIN_TOKEN=$(openssl rand -hex 32)/" .env.prod
chmod 600 .env.prod
```

## 4. Start the stack

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
docker compose -f docker-compose.prod.yml --env-file .env.prod logs -f scheduler   # watch the backfill
curl -s http://127.0.0.1:8000/api/health                                          # {"status":"ok"}
```

On first start the scheduler backfills `FX_BACKFILL_DAYS` of history, then runs every
`FX_SCHEDULE_HOURS`. All three services restart automatically after a reboot.

## 5. nginx and HTTPS

```bash
sed -i 's/fx.example.com/fx.yourdomain.com/' deploy/nginx.conf
sudo cp deploy/nginx.conf /etc/nginx/sites-available/fx-rates
sudo ln -s /etc/nginx/sites-available/fx-rates /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d fx.yourdomain.com
```

If a firewall is on: `sudo ufw allow 'Nginx Full'`.

## Updating

```bash
cd ~/fx-rates-etl && git pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d --build
```

## Triggering a run manually

```bash
curl -X POST https://fx.yourdomain.com/api/runs \
  -H "Authorization: Bearer $FX_ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"start": "2025-01-01", "end": "2025-03-31"}'
```

## Backups

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec -T db \
  pg_dump -U fx fx | gzip > fx-$(date +%F).sql.gz
```
