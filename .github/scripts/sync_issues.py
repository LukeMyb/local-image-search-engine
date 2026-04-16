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
        ['gh', 'issue', 'list', '--state', 'all', '--json', 'title,number,state', '--limit', '1000'],
        capture_output=True, text=True, check=True
    )
    existing_issues_list = json.loads(result.stdout)
    existing_issues = {issue['title']: issue for issue in existing_issues_list}
except Exception as e:
    print(f"Error fetching issues: {e}")
    existing_titles = set()

# 空行（改行2つ以上）でブロックごとに分割
blocks = re.split(r'\n\s*\n', content.strip())

for block in blocks:
    lines = block.strip().splitlines()
    if not lines: continue
    
    raw_title_line = lines[0].strip()
    body = '\n'.join(lines[1:])
    
    # タイトルの末尾に「 closed」がついているか判定
    is_closed_marked = raw_title_line.endswith(' closed')
    
    # GitHub上の検索に使う実際のタイトル（「 closed」がついている場合は取り除く）
    actual_title = raw_title_line[:-7] if is_closed_marked else raw_title_line

    # タイトルがすでにGitHub上に存在するかチェック
    if actual_title in existing_issues:
        issue_info = existing_issues[actual_title]
        
        if is_closed_marked:
            # 「 closed」がついていて、かつGitHub上でまだ「OPEN」ならクローズする
            if issue_info['state'] == 'OPEN':
                print(f"Closing issue: {actual_title} (#{issue_info['number']})")
                subprocess.run(['gh', 'issue', 'close', str(issue_info['number'])], check=True)
            else:
                print(f"Skip (Already closed): {actual_title}")
        else:
            print(f"Skip (Already exists): {actual_title}")
    else:
        if is_closed_marked:
            # 「 closed」が書き込まれているのにGitHubに存在しない場合はスキップ（誤爆防止）
            print(f"Skip (Marked as closed but not found on GitHub): {actual_title}")
        else:
            # 存在しない場合は新規Issueを作成
            print(f"Creating issue: {actual_title}")
            cmd = ['gh', 'issue', 'create', '--title', actual_title, '--body', body]
            subprocess.run(cmd, check=True)