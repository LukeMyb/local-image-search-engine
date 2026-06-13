from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
from pydantic import BaseModel
from typing import List

from core.search import SearchManager

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

@app.get("/thumbnail/{image_id}")
def get_thumbnail(image_id: int):
    """
    画像IDを受け取り、ローカルのサムネイルファイルパスを特定してブラウザに画像データを配達する
    """
    image_data = search_manager.db.get_image_by_id(image_id)
    
    # データベースにIDが登録されていない、またはサムネイルパスがない場合のエラー
    if not image_data or not image_data.get('thumbnail_path'):
        raise HTTPException(status_code=404, detail="Thumbnail not found in database")
        
    # PC(ディスク)上にサムネイルファイルが実在するか確認
    if not os.path.exists(image_data['thumbnail_path']):
        raise HTTPException(status_code=404, detail="Thumbnail file not found on disk")
        
    # 安全にサムネイル画像データをブラウザへ配達する
    return FileResponse(image_data['thumbnail_path'])

@app.get("/search")
def search(q: str):
    """
    検索クエリ(q)を受け取り、検索結果をJSONで返す
    """
    results = search_manager.search(q) 

    # 検索結果からIDだけをすべて抽出し、表示用は最初の100件で切り出す
    all_ids = [img["id"] for img in results]
    initial_results = results[:100]

    return {
        "query": q,
        "total": len(all_ids),
        "all_ids": all_ids,
        "results": initial_results
    }

# IDリストから画像情報のみを取得するエンドポイント
@app.post("/images/batch")
def get_images_batch(request: BatchImageRequest):
    """
    IDのリストを受け取り、その画像データだけをDBから直接取得して返す
    """
    # SearchManagerが持っているdbインスタンスの新しいメソッドを呼び出す
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
    
    # フロントエンドが検索結果と同じように扱えるように、
    # {"query": "", "results": [...]} の形式で返す
    return {"query": "", "results": results}

@app.post("/favorite/{image_id}")
def toggle_favorite(image_id: int):
    """
    指定された画像のお気に入り状態を反転（0⇔1）させる
    """
    new_status = search_manager.db.toggle_favorite(image_id)
    
    # 変更後の状態をフロントエンドに返す
    return {"image_id": image_id, "is_favorite": new_status}



# フロントエンドから送られてくるJSONデータ（名前とクエリ）の型定義
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

# 絵柄タグ作成用エンドポイント
@app.post("/style")
def create_style_tag(data: StyleTagCreate):
    """
    選択された画像IDのリストとタグ名を受け取り、重心ベクトルを計算して絵柄タグを保存する
    """
    # 1. 画像IDからファイルパスを取得する
    image_paths = []
    for img_id in data.image_ids:
        img_data = search_manager.db.get_image_by_id(img_id)
        if img_data and img_data.get('file_path'):
            image_paths.append(img_data['file_path'])
            
    if not image_paths:
        raise HTTPException(status_code=400, detail="有効な画像が選択されていません")
        
    # 絵柄検索エンジン(style_searcher)を取得
    style_searcher = search_manager.style_engine
    if style_searcher is None:
        raise HTTPException(status_code=500, detail="絵柄検索エンジンがロードされていません")
        
    # 重心ベクトルを計算
    print(f"DEBUG: [{data.name}] を {len(image_paths)}枚の画像から計算します...")
    centroid = style_searcher.calculate_centroid(image_paths)
    
    if centroid is None:
        raise HTTPException(status_code=500, detail="絵柄の解析に失敗しました。画像がベクトル化されていない可能性があります。")
        
    # データベースに保存
    try:
        search_manager.db.save_style_tag(data.name, centroid)
        print(f"[{data.name}] の保存が完了しました！")
        return {
            "status": "success", 
            "message": f"絵柄タグ '{data.name}' を作成しました"
        }
    except Exception as e:
        # すでに同じ名前のタグが存在する場合などのエラーハンドリング
        raise HTTPException(status_code=400, detail=f"保存に失敗しました: {str(e)}")

# 絵柄タグの削除用エンドポイント
@app.delete("/style/{style_id}")
def delete_style(style_id: int):
    """
    指定されたIDの絵柄タグを削除する
    """
    search_manager.db.delete_style_tag(style_id)
    return {"status": "success", "message": "絵柄タグを削除しました"}