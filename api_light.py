from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
import re
from pydantic import BaseModel
from typing import List

from core.search_light import SearchManagerLight

# POST リクエストで受け取るIDリストのデータ型を定義
class BatchImageRequest(BaseModel):
    ids: List[int]

# 絵柄タグ作成リクエストのデータ型定義
class StyleTagCreate(BaseModel):
    name: str
    image_ids: List[int]

app = FastAPI()

# フロントエンド（React/Next.js等）からのアクセスを許可する必須設定 (CORS)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # 開発中はどこからでも通信を許可
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 検索マネージャーの初期化（軽量版）
search_manager = SearchManagerLight()

@app.get("/image/{image_id}")
def get_image(image_id: int):
    """
    画像IDを受け取り、ローカルのファイルパスを特定してブラウザに画像データを配達する
    """
    image_data = search_manager.db.get_image_by_id(image_id)
    
    if not image_data or not image_data['file_path']:
        raise HTTPException(status_code=404, detail="Image not found in database")
        
    if not os.path.exists(image_data['file_path']):
        raise HTTPException(status_code=404, detail="File not found on disk")
        
    return FileResponse(image_data['file_path'])

@app.get("/thumbnail/{image_id}")
def get_thumbnail(image_id: int):
    """
    画像IDを受け取り、ローカルのサムネイルファイルパスを特定してブラウザに画像データを配達する
    """
    image_data = search_manager.db.get_image_by_id(image_id)
    
    if not image_data or not image_data.get('thumbnail_path'):
        raise HTTPException(status_code=404, detail="Thumbnail not found in database")
        
    if not os.path.exists(image_data['thumbnail_path']):
        raise HTTPException(status_code=404, detail="Thumbnail file not found on disk")
        
    return FileResponse(image_data['thumbnail_path'])

@app.get("/search")
def search(q: str, sort: str = "score"):
    """
    検索クエリ(q)を受け取り、検索結果をJSONで返す
    """
    try:
        style_match = re.search(r'style:([^\s|]+)', q)
        if style_match:
            style_name = style_match.group(0)
            search_manager.db.update_style_usage(style_name)
    except Exception as e:
        print(f"履歴の保存に失敗しました: {e}")

    results = search_manager.search(q, sort_order=sort)

    all_ids = [img["id"] for img in results]
    initial_results = results[:100]

    return {
        "query": q,
        "total": len(all_ids),
        "all_ids": all_ids,
        "results": initial_results
    }

@app.post("/images/batch")
def get_images_batch(request: BatchImageRequest):
    """
    IDのリストを受け取り、その画像データだけをDBから直接取得して返す
    """
    results = search_manager.db.get_images_by_ids(request.ids)
    return {"results": results}

@app.get("/suggest")
def suggest(q: str):
    """
    サジェスト（入力補完）の候補をJSONで返す
    """
    suggestions = search_manager.get_suggestions(q)
    return {"query": q, "suggestions": suggestions}

@app.get("/favorites")
def get_favorites():
    """
    お気に入り画像の一覧を取得し、検索結果と同じフォーマットで返す
    """
    results = search_manager.db.get_favorite_images()
    return {"query": "", "results": results}

@app.post("/favorite/{image_id}")
def toggle_favorite(image_id: int):
    """
    指定された画像のお気に入り状態を反転（0⇔1）させる
    """
    new_status = search_manager.db.toggle_favorite(image_id)
    return {"image_id": image_id, "is_favorite": new_status}

class BookmarkCreate(BaseModel):
    name: str
    query: str

@app.post("/bookmark")
def save_bookmark(data: BookmarkCreate):
    """
    新しいブックマークを保存、または既存のブックマークを上書きする
    """
    search_manager.db.save_bookmark(data.name, data.query)
    return {"status": "success", "message": f"ブックマーク '{data.name}' を保存しました"}

@app.get("/bookmarks")
def get_bookmarks(filter_text: str = ""):
    """
    保存されているブックマークの一覧を取得する
    """
    bookmarks = search_manager.db.get_bookmarks(filter_text)
    return {"bookmarks": bookmarks}

@app.delete("/bookmark/{bookmark_id}")
def delete_bookmark(bookmark_id: int):
    """
    指定されたIDのブックマークを削除する
    """
    search_manager.db.delete_bookmark(bookmark_id)
    return {"status": "success", "message": "ブックマークを削除しました"}

@app.patch("/bookmark/{bookmark_id}/use")
def update_bookmark_usage(bookmark_id: int):
    """
    ブックマークが使用された時刻を現在時刻に更新する
    """
    search_manager.db.update_bookmark_usage(bookmark_id)
    return {"status": "success", "message": "使用時刻を更新しました"}

# 絵柄タグ作成用エンドポイント（軽量版はダミー処理）
@app.post("/style")
def create_style_tag(data: StyleTagCreate):
    """
    軽量モードのため、絵柄タグの作成機能は使用不可としてエラーを返す
    """
    raise HTTPException(status_code=400, detail="軽量モードのため絵柄タグの作成は使用できません")

# 絵柄タグの削除用エンドポイント
@app.delete("/style/{style_id}")
def delete_style(style_id: int):
    """
    指定されたIDの絵柄タグを削除する
    """
    search_manager.db.delete_style_tag(style_id)
    return {"status": "success", "message": "絵柄タグを削除しました"}

if __name__ == "__main__":
    import os
    import uvicorn
    from dotenv import load_dotenv

    # .env ファイルを読み込む
    load_dotenv()
    
    # API_HOST と API_PORT を取得
    host = os.getenv("API_HOST", "127.0.0.1")
    port = int(os.getenv("API_PORT", 8715))
    
    # uvicorn を起動
    uvicorn.run(app, host=host, port=port)
