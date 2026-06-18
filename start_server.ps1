# Hugging Face関連の通信と利用統計送信をOSレベルで遮断する
$env:HF_HUB_OFFLINE = "1"
$env:TRANSFORMERS_OFFLINE = "1"
$env:HF_HUB_DISABLE_TELEMETRY = "1"

# サーバーを起動
uvicorn api:app --host 0.0.0.0 --port 8020