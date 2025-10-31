#!/bin/sh
set -eu

DOMAIN="supolare.ru"
ALT_DOMAIN="www.supolare.ru"
EMAIL="nachatoi@list.ru"
WEBROOT="/var/www/certbot"
LE_DIR="/etc/letsencrypt"
LIVE_DIR="$LE_DIR/live/$DOMAIN"

trap 'exit 0' TERM INT

issue_certificate() {
    certbot certonly \
        --webroot \
        --webroot-path "$WEBROOT" \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        --non-interactive \
        -d "$DOMAIN" \
        -d "$ALT_DOMAIN"
}

if [ ! -f "$LIVE_DIR/fullchain.pem" ]; then
    echo "[certbot] Requesting initial certificate for $DOMAIN"
    until issue_certificate; do
        echo "[certbot] Initial issuance failed; retrying in 60 seconds..."
        sleep 60
    done
    echo "[certbot] Initial certificate obtained"
fi

while :; do
    certbot renew \
        --webroot \
        --webroot-path "$WEBROOT" \
        --non-interactive \
        --quiet
    sleep 12h &
    wait $!
    echo "[certbot] Performed renewal check"
    if [ -x /var/run/certbot-post-renew ]; then
        /var/run/certbot-post-renew || true
    fi
done
