#!/bin/bash
set -e

if [ -f .env.production ]; then
  export $(grep -v '^#' .env.production | xargs)
elif [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

DOMAIN=${DOMAIN:-allkey.kz}
EMAIL=${EMAIL:-admin@allkey.kz}

echo "=== SSL Init for $DOMAIN and api.$DOMAIN ==="

# 1. Install nginx and certbot if not present
if ! command -v nginx &> /dev/null; then
    echo "Installing nginx..."
    apt-get update && apt-get install -y nginx
fi

if ! command -v certbot &> /dev/null; then
    echo "Installing certbot..."
    apt-get update && apt-get install -y certbot python3-certbot-nginx
fi

# 2. Copy nginx config
echo "Setting up nginx config..."
cp nginx/allkey.kz.conf /etc/nginx/sites-available/allkey.kz.conf
ln -sf /etc/nginx/sites-available/allkey.kz.conf /etc/nginx/sites-enabled/allkey.kz.conf
rm -f /etc/nginx/sites-enabled/default

# 3. Create a temporary HTTP-only config for certbot challenge
cat > /etc/nginx/sites-available/allkey-temp.conf <<EOF
server {
    listen 80;
    server_name $DOMAIN api.$DOMAIN;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        return 200 'Setting up SSL...';
        add_header Content-Type text/plain;
    }
}
EOF

ln -sf /etc/nginx/sites-available/allkey-temp.conf /etc/nginx/sites-enabled/allkey.kz.conf
mkdir -p /var/www/certbot

nginx -t && systemctl restart nginx

# 4. Get certificate
echo "Requesting certificate from Let's Encrypt..."
certbot certonly --webroot -w /var/www/certbot \
    --email "$EMAIL" \
    -d "$DOMAIN" -d "api.$DOMAIN" \
    --agree-tos --no-eff-email

# 5. Switch to full config with SSL
echo "Switching to full SSL config..."
cp nginx/allkey.kz.conf /etc/nginx/sites-available/allkey.kz.conf
ln -sf /etc/nginx/sites-available/allkey.kz.conf /etc/nginx/sites-enabled/allkey.kz.conf
rm -f /etc/nginx/sites-available/allkey-temp.conf
nginx -t && systemctl reload nginx

# 6. Set up auto-renewal with nginx reload
echo "Setting up auto-renewal..."
cat > /etc/cron.d/certbot-renew <<EOF
0 3 * * * root certbot renew --quiet --deploy-hook "systemctl reload nginx"
EOF

# 7. Start docker services
echo "Starting Docker services..."
docker compose -f docker-compose.prod.yml up -d --build

echo ""
echo "=== Done! ==="
echo "https://$DOMAIN"
echo "https://api.$DOMAIN"
echo ""
echo "Certificate auto-renewal is configured via cron."
echo "Nginx will reload automatically after each renewal."
