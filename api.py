from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
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

@app.get("/")
def read_root():
    return {"message": "LISE API is running!"}

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