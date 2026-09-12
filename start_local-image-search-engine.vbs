Set WshShell = CreateObject("WScript.Shell")

' バックエンドの起動 (コマンドプロンプトを非表示で実行)
WshShell.Run "cmd /c cd c:\src\personal\local-image-search-engine && call .venv\Scripts\activate && python api.py", 0, False

' フロントエンドの起動 (コマンドプロンプトを非表示で実行)
WshShell.Run "cmd /c cd c:\src\personal\local-image-search-engine\frontend && npm run start", 0, False
