import os
import re
import subprocess
import json

# issues.txtを読み込む
with open('issues.txt', 'r', encoding='utf-8') as f:
    content = f.read()

# GitHubから既存のIssue（クローズ済み含む）のタイトル一覧を取得する
try:
    # ghコマンドで全IssueのタイトルをJSON形式で取得
    result = subprocess.run(
        ['gh', 'issue', 'list', '--state', 'all', '--json', 'title', '--limit', '1000'],
        capture_output=True, text=True, check=True
    )
    existing_issues = json.loads(result.stdout)
    existing_titles = {issue['title'] for issue in existing_issues}
except Exception as e:
    print(f"Error fetching issues: {e}")
    existing_titles = set()

# 空行（改行2つ以上）でブロックごとに分割
blocks = re.split(r'\n\s*\n', content.strip())

for block in blocks:
    lines = block.strip().splitlines()
    if not lines: continue
    
    title_line = lines[0]
    body = '\n'.join(lines[1:])
    
    # タイトルがすでにGitHub上に存在するかチェック
    # 正規表現での番号チェックから、取得したタイトル一覧との完全一致照合に変更
    if title_line in existing_titles:
        print(f"Skip (Already exists): {title_line}")
    else:
        # 存在しない場合は新規Issueを作成
        print(f"Creating issue: {title_line}")
        cmd = ['gh', 'issue', 'create', '--title', title_line, '--body', body]
        subprocess.run(cmd, check=True) # 出力を受け取って番号を抽出する処理を削除