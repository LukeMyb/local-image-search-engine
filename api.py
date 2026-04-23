from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os

from core.search import SearchManager

app = FastAPI()

# フロントエンド（React/Next.js等）からのアクセスを許可する必須設定 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 開発中はどこからでも通信を許可
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 検索マネージャーの初期化
search_manager = SearchManager()

@app.get("/image/{image_id}")
def get_image(image_id: int):
    """
    画像IDを受け取り、ローカルのファイルパスを特定してブラウザに画像データを配達する
    """
    # SearchManagerのデータベース接続を借りて、IDから画像情報を取得
    image_data = search_manager.db.get_image_by_id(image_id)
    
    # データベースにIDが登録されていない場合のエラー
    if not image_data or not image_data['file_path']:
        raise HTTPException(status_code=404, detail="Image not found in database")
        
    # PC(ディスク)上にファイルが実在するか確認（移動・削除対策）
    if not os.path.exists(image_data['file_path']):
        raise HTTPException(status_code=404, detail="File not found on disk")
        
    # 安全に画像データそのものをブラウザへ配達する
    return FileResponse(image_data['file_path'])

@app.get("/search")
def search(q: str):
    """
    検索クエリ(q)を受け取り、検索結果をJSONで返す
    """
    results = search_manager.search(q) 
    return {"query": q, "results": results}

@app.get("/suggest")
def suggest(q: str):
    """
    サジェスト（入力補完）の候補をJSONで返す
    """
    suggestions = search_manager.get_suggestions(q)
    return {"query": q, "suggestions": suggestions}