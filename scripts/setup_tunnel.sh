#!/bin/bash

# Configuration for Ngrok Tunnel
# Expects NGROK_AUTH_TOKEN and NGROK_DOMAIN environment variables

if [ -z "$NGROK_AUTH_TOKEN" ]; then
    echo "❌ Error: NGROK_AUTH_TOKEN not set."
    exit 1
fi

if [ -z "$NGROK_DOMAIN" ]; then
    echo "❌ Error: NGROK_DOMAIN not set."
    exit 1
fi

echo "🌐 Setting up Ngrok Tunnel..."

# Download and install ngrok (official method)
wget -q https://bin.equinox.io/c/bNyj1mQVY4c/ngrok-v3-stable-linux-amd64.tgz
tar -xzf ngrok-v3-stable-linux-amd64.tgz
chmod +x ngrok
sudo mv ngrok /usr/local/bin/

# Authenticate ngrok
ngrok config add-authtoken "$NGROK_AUTH_TOKEN"

# Start ngrok tunnel in background with the static domain
ngrok http 8000 --domain="$NGROK_DOMAIN" --log=stdout > /tmp/ngrok.log 2>&1 &

sleep 2
echo "✅ Ngrok Tunnel started → https://$NGROK_DOMAIN"
