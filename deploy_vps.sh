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
git clone https://github.com/rockyxd3/Auro-ruma.git
cd auro-zara

cat << 'EOF' > .env
API_ID=24790031
API_HASH=0c7a496a6e33e862be48af651b935cce
BOT_TOKEN=8119446814:AAErjw8AZ9WuK4AkE9oohOkFEqdv2h1fwnI
MONGO_URL=mongodb+srv://Mecobot:Mecobots@cluster0.o64pd7z.mongodb.net/?retryWrites=true&w=majority
LOGGER_ID=-1003738847504
OWNER_ID=7632048577
SESSION=AQF6RA8AsKFLeFKCTSRucYW3XjMQXyCvUELod7b93aWavdcxDWz67i2o9NF1d0g73EWkOhcuBIucxbHwiactBtSc69Vdbhh5CBshsvUS6ZvDXkWOJdZT-oS94GkIaeolVbtGVwxK1b-wzUceekFkS4g-7195IJLyaiCCVucKJhDiL7ts9g0GpZJmcC1y1cNjnzkSUmDJ2g42Br4vj5Q4srb_ceHqCyx0n5ueLaI6KO2JIxzm4Qrxqo_2ep9kj0zc2kQRcGmRhr5ZX8OsWziOrOLaptzWrJuvTyyik1_n9AxlL9UDhfCxHnRWFkLDjxEHvBsZ0BezOUBd6mLO8VwN_FQdpmo8gQAAAAIQqiWCAA
API_URL=https://apisparrow.site
API_KEY=sparrownhhJUQYo5QvMnred9S2YPcEi
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
