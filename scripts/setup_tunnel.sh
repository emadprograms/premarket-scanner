#!/bin/bash

# Configuration for Cloudflare Tunnel
# Expects TUNNEL_TOKEN environment variable

if [ -z "$TUNNEL_TOKEN" ]; then
    echo "❌ Error: TUNNEL_TOKEN not set."
    exit 1
fi

echo "🌐 Setting up Cloudflare Tunnel..."

# Download cloudflared
if [[ "$OSTYPE" == "linux-gnu"* ]]; then
    curl -L --output cloudflared.deb https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb
    sudo dpkg -i cloudflared.deb
    rm cloudflared.deb
elif [[ "$OSTYPE" == "darwin"* ]]; then
    brew install cloudflare/cloudflare/cloudflared
fi

# Run tunnel in background
cloudflared tunnel --no-autoupdate run --token "$TUNNEL_TOKEN" &

echo "✅ Cloudflare Tunnel started in background."
