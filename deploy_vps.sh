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
git clone https://github.com/rockyxd3/New_Reapo.git
cd New_Reapo

cat << 'EOF' > .env
API_ID=31327567
API_HASH=c523f8135469acf0582ab2044e56b34e
BOT_TOKEN=8832601838:AAFnVjLE5y4GcHZIsf-XJDlaiFMwULcQziU
MONGO_URL=mongodb+srv://anjali:anjali@cluster0.oj6qq.mongodb.net/?retryWrites=true&w=majority
LOGGER_ID=-1004305621207
OWNER_ID=7632048577
SESSION=AQHeBU8AXortU_4PYgEscwxWRU7FpsjeK93zZ_IKDTm4BuHetF5AzEaJBGAAR_duRe8w8-6RazB-xQ87FJM38qSP3Z9Rn4mQJkg_avI6DkLLpZgf5w-qXyshT9uRfYete7lF8WH6sfaou3J8R32yeIKJR6MqHd-3JI5FPk8qwEZAdQhu906ZYeYHnu2ngRhoCJqO5L-anNs4HZhYmkkwARHcrcdwLyNrNSuWVOoKg2amav0QsqBKc62d7wBZhGQ5kvny17fb09KPo8RYVEewg2tDa-zmnNjITmwpqwFQ3Yitbq7Db2C8RNLimsDFpgjNDlxSr_E5ktJBFMwLFPNbwv4EvVnYZQAAAAIUoiRyAA
API_URL=https://apisparrow.site
API_KEY=sparrowzbA9h4lRscohX1HH1raPTKkX
EOF

python3 -m venv venv
./venv/bin/pip install --upgrade pip setuptools wheel
./venv/bin/pip install -r requirements.txt

tmux kill-session -t musicbot 2>/dev/null || true
tmux new-session -d -s musicbot './venv/bin/python3 -m anony'

sleep 4

echo "=========================================="
echo " Status Check & Logs:"
echo "=========================================="
tmux capture-pane -pt musicbot -S -30 || true

echo "=========================================="
echo " Setup Finished! Bot is running in tmux."
echo " To view live logs: tmux attach -t musicbot"
echo "=========================================="
