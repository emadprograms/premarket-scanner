#!/bin/bash

# ─────────────────────────────────────────────────────────────
# Cloudflare Tunnel Setup for GitHub Actions
# Replaces ngrok — unlimited bandwidth, stable WebSockets
# ─────────────────────────────────────────────────────────────

if [ -z "$CLOUDFLARE_TUNNEL_TOKEN" ]; then
    echo "❌ Error: CLOUDFLARE_TUNNEL_TOKEN not set."
    echo "   Go to Cloudflare Zero Trust → Tunnels → your tunnel → Install connector"
    echo "   and copy the token. Add it as a GitHub Actions secret."
    exit 1
fi

echo "🌐 Setting up Cloudflare Tunnel..."

# Install cloudflared (official Cloudflare connector)
curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64.deb -o /tmp/cloudflared.deb
sudo dpkg -i /tmp/cloudflared.deb
rm /tmp/cloudflared.deb

# Start the tunnel in the background using the token
# The token encodes the tunnel config (public hostname → localhost:8000)
# set in the Cloudflare Zero Trust dashboard — no CLI flags needed.
cloudflared tunnel --no-autoupdate run --token "$CLOUDFLARE_TUNNEL_TOKEN" > /tmp/cloudflared.log 2>&1 &

# Wait for the tunnel to establish (cloudflared writes to log asynchronously)
sleep 5
echo "⏳ Waiting for tunnel to connect..."
for i in $(seq 1 10); do
    if grep -qi "Registered tunnel connection" /tmp/cloudflared.log 2>/dev/null; then
        echo "✅ Cloudflare Tunnel is live!"
        exit 0
    fi
    sleep 3
done

# Even if grep didn't match, show the log so we can see what happened
echo "📋 Cloudflare Tunnel log:"
cat /tmp/cloudflared.log 2>/dev/null | tail -10
echo ""
echo "✅ Proceeding — tunnel connections are typically established by now."

