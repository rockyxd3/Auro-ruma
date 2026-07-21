#!/bin/bash
set -e

echo "=========================================="
echo " Starting Full Automatic VPS Setup..."
echo "=========================================="

sudo apt update -y
sudo apt install -y curl git tmux unzip ffmpeg python3 python3-pip python3-venv python3-dev build-essential

# Install Node.js 20 (required by PyTgCalls engine)
if ! command -v node &> /dev/null; then
    echo "Installing Node.js..."
    curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
    sudo apt install -y nodejs
fi

# Install Deno if missing
if ! command -v deno &> /dev/null; then
    echo "Installing Deno..."
    curl -fsSL https://deno.land/install.sh | sh || true
    export DENO_INSTALL="$HOME/.deno"
    export PATH="$DENO_INSTALL/bin:$PATH"
fi

rm -rf New_Reapo
git clone https://github.com/rockyxd3/auro-zara.git
cd auro-zara

cat << 'EOF' > .env
API_ID=30760740
API_HASH=4d595bd36b2bd105ea79b10b3e3674e1
BOT_TOKEN=8310754623:AAFi6EFt9iGkomsSSYDDGH4msx1-QQO3N74
MONGO_URL=mongodb+srv://Govo:Govo@govo.fxh5zyz.mongodb.net/?retryWrites=true&w=majority
LOGGER_ID=-1003724317042
OWNER_ID=7632048577
SESSION=BQHVXyQAi81K-rYtZXi2gOf4DnJcLPn7Qsy3Zk_1g4XFBXPx05JxYAwoQPIy6sxbErAsFnEeYkz8ag9liP-FELKzRD58uAjDAYjC-W9oid0NwH_dNsOM5WUTvqUT_QSI_DjxCTRXqSwuJvgqy9Zw6EUg-yb2m_79NEu7q__zNqNxrNQB7T8n-fUFy45XNnIMajTEufgyHCFped6lkkO-tUWjD5sqD9V4eRYBPWOWxFsTjhN2S6bF2pCRQ6IVv010Ub6pnoKeGctohkjCPvNpmkFFn8UCzKkU6L5E-e-4cUn6AkdD_2L4ts2qgkdcYrUoWp43Fk35JCa0DjldWsAaKlVClpDC2gAAAAH87swMAA
API_URL=https://apisparrow.site
API_KEY=sparrowGQfbBI5nIbv44KHfTJGcKqju
EOF

python3 -m venv venv
./venv/bin/pip install --upgrade pip setuptools wheel
./venv/bin/pip install -r requirements.txt

tmux kill-session -t musicbot 2>/dev/null || true
tmux new-session -d -s musicbot './venv/bin/python3 -m auro'

sleep 4

echo "=========================================="
echo " Status Check & Logs:"
echo "=========================================="
tmux capture-pane -pt musicbot -S -30 || true

echo "=========================================="
echo " Setup Finished! Bot is running in tmux."
echo " To view live logs: tmux attach -t musicbot"
echo "=========================================="
