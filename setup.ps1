# エラーが発生した場合はその時点でスクリプトを停止する設定
$ErrorActionPreference = "Stop"

Write-Host "=== Local Image Search Engine セットアップを開始します ===" -ForegroundColor Cyan

# 実行するスクリプトの順番を定義
$scripts = @(
    "scripts/download_assets.py",
    "scripts/vectorize_tags.py",
    "tasks/index.py",
    "tasks/tagger.py"
)

foreach ($script in $scripts) {
    Write-Host "`n>>> [$script] を実行しています..." -ForegroundColor Yellow
    
    # Pythonスクリプトを実行
    python $script
    
    # 実行結果（終了コード）を確認し、0（成功）以外なら中断する
    if ($LASTEXITCODE -ne 0) {
        Write-Host "`n[エラー] $script の実行中にエラーが発生しました。" -ForegroundColor Red
        Write-Host "セットアップを中断します。エラー内容を確認してください。" -ForegroundColor Red
        exit $LASTEXITCODE
    }
}

Write-Host "`n=== すべてのセットアップが正常に完了しました！ ===" -ForegroundColor Green
Write-Host "python app.py でアプリを起動できます。" -ForegroundColor Cyan