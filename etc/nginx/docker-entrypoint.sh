#!/bin/sh
set -eu

DOMAIN="supolare.ru"
CERT_DIR="/etc/letsencrypt/live/$DOMAIN"
LE_DIR="/etc/letsencrypt"
DHPARAM_FILE="$LE_DIR/ssl-dhparams.pem"

if ! command -v openssl >/dev/null 2>&1; then
    echo "[nginx] Installing openssl"
    apk add --no-cache openssl >/dev/null
fi

if [ ! -d "$CERT_DIR" ]; then
    mkdir -p "$CERT_DIR"
fi

FULLCHAIN="$CERT_DIR/fullchain.pem"
PRIVKEY="$CERT_DIR/privkey.pem"
CHAIN="$CERT_DIR/chain.pem"

if [ ! -f "$FULLCHAIN" ] || [ ! -f "$PRIVKEY" ]; then
    echo "[nginx] Generating temporary self-signed certificate for $DOMAIN"
    openssl req -x509 -nodes -newkey rsa:2048 \
        -days 1 \
        -keyout "$PRIVKEY" \
        -out "$FULLCHAIN" \
        -subj "/CN=$DOMAIN" 2>/dev/null
    cp "$FULLCHAIN" "$CHAIN"
fi

if [ ! -f "$DHPARAM_FILE" ]; then
    echo "[nginx] Generating fallback DH parameters"
    openssl dhparam -out "$DHPARAM_FILE" 2048 2>/dev/null
fi
