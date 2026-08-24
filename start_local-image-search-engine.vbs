Set WshShell = CreateObject("WScript.Shell")

' バックエンドの起動 (コマンドプロンプトを非表示で実行)
WshShell.Run "cmd /c cd c:\src\personal\local-image-search-engine && uvicorn api:app --host 0.0.0.0 --port 8020", 0, False

' フロントエンドの起動 (コマンドプロンプトを非表示で実行)
WshShell.Run "cmd /c cd c:\src\personal\local-image-search-engine\frontend && npm run start", 0, False
