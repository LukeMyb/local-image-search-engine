"use client";

import { useState, useEffect } from "react";
import { useSystemUI } from "../hooks/useSystemUI";
import { useImageSearch } from "../hooks/useImageSearch";

import BookmarkManager from "../components/BookmarkManager";
import ImageGrid from "../components/ImageGrid";
import ImageViewer from "../components/ImageViewer";
import SearchBar from "../components/SearchBar";

import { API_BASE_URL } from "../lib/config";

// 検索結果のデータ構造を定義
interface SearchResult {
  id: number;
  is_favorite?: number;
}

// ブックマークのデータ構造を定義
interface Bookmark {
  id: number;
  name: string;
  query: string;
  last_used_at: string;
}

export default function Home() {
  // 検索キーワードを管理する変数
  const [query, setQuery] = useState("");

  // 選択された画像（モーダルで表示する画像）を管理する変数
  const [selectedImage, setSelectedImage] = useState<SearchResult | null>(null);

  // ドロワーの開閉状態を管理する変数
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  // ブックマーク保存ダイアログの開閉と入力内容を管理
  const [isSaveDialogOpen, setIsSaveDialogOpen] = useState(false);

  // 全ブックマークの完全な情報を保持する
  const [allBookmarks, setAllBookmarks] = useState<Bookmark[]>([]);
  // 現在保存されているすべての「クエリ（文字列）」のリストを保持する変数
  const [savedQueries, setSavedQueries] = useState<string[]>([]);

  // 検索・画像操作ロジックをフックから取得
  const { results, statusMessage, handleSearch, toggleFavorite, loadMore, hasMore } = useImageSearch();

  // システム制御（ズーム禁止・スクロールロック）を有効化
  useSystemUI({ selectedImage, isDrawerOpen });

  // サーバーからすべてのブックマークを取得して、クエリのリストを最新にする関数
  const refreshSavedQueries = async () => {
    try {
      // フィルターなしで全件取得
      const response = await fetch(`${API_BASE_URL}/bookmarks?filter_text=`);
      if (!response.ok) throw new Error();
      const data = await response.json();
      
      // 全データを保存
      setAllBookmarks(data.bookmarks);
      
      // クエリ文字列だけの配列を作成して保存
      const queries = data.bookmarks.map((bm: Bookmark) => bm.query.trim());
      setSavedQueries(queries);
    } catch (error) {
      console.error("ブックマーク同期エラー:", error);
    }
  };

  // ブックマークボタンを押した時の処理
  const openBookmarkDialog = () => {
    if (!query.trim()) return;

    // 現在のクエリが保存済みかどうかを判定
    const existingBm = allBookmarks.find(bm => bm.query.trim() === query.trim());
    
    setIsSaveDialogOpen(true);
  };

  // アプリ起動時に一回だけ、保存済みクエリのリストを読み込む
  useEffect(() => {
    refreshSavedQueries();
  }, []);

  return (
    // レイアウト
    <div className="p-2 min-h-screen bg-zinc-900 text-green-400 flex flex-col gap-4">
      <p className="text-lg font-medium">{statusMessage}</p>

      {/* (SearchBarコンポーネントを呼び出し) */}
      <SearchBar 
        query={query}
        setQuery={setQuery}
        onSearch={(e) => handleSearch(query, e)}
        setIsDrawerOpen={setIsDrawerOpen}
        openBookmarkDialog={openBookmarkDialog}
        savedQueries={savedQueries}
      />

      {/* 取得したIDを使って画像を並べる処理 */}
      <ImageGrid 
        results={results} 
        setSelectedImage={setSelectedImage} 
        loadMore={loadMore}
        hasMore={hasMore}
      />

      {/* モーダルの描画処理 */}
      {selectedImage && (() => {
        // 現在の画像が配列の何番目にあるかを計算
        const currentIndex = results.findIndex((item) => item.id === selectedImage.id);
        const hasPreceding = currentIndex > 0;
        const hasSubsequent = currentIndex < results.length - 1;

        return (
          <ImageViewer 
            selectedImage={selectedImage} 
            onClose={() => setSelectedImage(null)} 
            onToggleFavorite={(id, e) => toggleFavorite(id, e, selectedImage, setSelectedImage)}
            onNext={() => hasSubsequent && setSelectedImage(results[currentIndex + 1])}
            onPrev={() => hasPreceding && setSelectedImage(results[currentIndex - 1])}
            hasPreceding={hasPreceding}
            hasSubsequent={hasSubsequent}
          />
        );
      })()}

      {/* ブックマーク関連の処理 */}
      <BookmarkManager
        isDrawerOpen={isDrawerOpen}
        setIsDrawerOpen={setIsDrawerOpen}
        isSaveDialogOpen={isSaveDialogOpen}
        setIsSaveDialogOpen={setIsSaveDialogOpen}
        query={query}
        setQuery={setQuery}
        handleSearch={(e, oq) => handleSearch(query, e, oq)}
        allBookmarks={allBookmarks}
        savedQueries={savedQueries}
        refreshSavedQueries={refreshSavedQueries}
      />
    </div>
  );
}