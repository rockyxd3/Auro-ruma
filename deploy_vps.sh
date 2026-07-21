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
API_ID=36354238
API_HASH=o64pd7z.mongodb.net/?retryWrites=true&w=majority
BOT_TOKEN=8808199635:AAEDcCjThXkse7Qf5LloPEV5TwafHtiuAng
MONGO_URL=mongodb+srv://Mecobot:Mecobots@cluster0.o64pd7z.mongodb.net/?retryWrites=true&w=majority
LOGGER_ID=-1004468370263
OWNER_ID=8935584927
SESSION=AgHUtygAM2l9LEEABsjisccCnBTRcJ0MzlG6_BtqXqpegu7sfSCfZovZCP7RYdMdnyFiNtzwoQcvTWuRoOvv5AAg4QAgZ9OxQBtWxMrce33jtNNoTzc9B5TdYRI2TpddX9nyZds4iznnNRlBkmokVUT3TqHGIz0CuVPy7Mwz4f2-rSiwhFbE03oEOckbe0rMgWYeh200IfA7_a29qgNZk-8AqWxnhv_ys1ge7oxL5j6TUmQY6VpLb71MLwLrrLZs-MzGnwLuu624pSUpgqztqXYOCZTm0iiyZjJBbnV-L8SqUmWLePt46j8W8ohhtvbKaV0iseE7pdfxTrP123TjYt2m9c7EAwAAAAH1c_4KAA
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
