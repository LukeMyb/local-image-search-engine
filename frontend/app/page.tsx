"use client";

import { useState, useEffect } from "react";

import BookmarkManager from "../components/BookmarkManager";
import ImageGrid from "../components/ImageGrid";
import ImageViewer from "../components/ImageViewer";
import SearchBar from "../components/SearchBar";

import { useSystemUI } from "../hooks/useSystemUI";

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
  // ステータスを管理する変数
  const [statusMessage, setStatusMessage] = useState("システム待機中...");
  // 検索キーワードを管理する変数
  const [query, setQuery] = useState("");

  // 画像のデータ（配列）
  const [results, setResults] = useState<SearchResult[]>([]);
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

  // システム制御（ズーム禁止・スクロールロック）を有効化
  useSystemUI({ selectedImage, isDrawerOpen });

  // サーバーからすべてのブックマークを取得して、クエリのリストを最新にする関数
  const refreshSavedQueries = async () => {
    try {
      // フィルターなしで全件取得
      const response = await fetch("http://192.168.11.3:8000/bookmarks?filter_text=");
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

  const handleSearch = async (e?: React.FormEvent, overrideQuery?: string) => {
    // フォーム送信によるページリロードを確実に阻止する
    if (e) e.preventDefault();

    // 検索実行時にスマホのキーボードを強制的に閉じる（フォーカスを外す）
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }

    // 直接渡されたキーワードがあればそれを使い、なければ検索窓(query)の値を使う
    const currentQuery = overrideQuery !== undefined ? overrideQuery : query;

    // 空文字（スペースのみ含む）の判定
    const isQueryEmpty = !currentQuery.trim();
    
    // 変数 endpoint を作成
    const endpoint = isQueryEmpty ? `/favorites` : `/search?q=${encodeURIComponent(currentQuery)}`;

    setStatusMessage(currentQuery ? `「${currentQuery}」を検索中...` : `お気に入り一覧を取得中...`);
    setResults([]); // 検索開始時に前の画像をクリア

    try {
      // Python側のAPIを叩く
      const response = await fetch(`http://192.168.11.3:8000${endpoint}`);

      if (!response.ok) {
        throw new Error(`HTTPエラー: ${response.status}`);
      }

      const data = await response.json();

      // 数千件の画像を一度に描画するとブラウザがフリーズするため、
      // 表示用の安全装置として先頭の50件だけ
      setResults(data.results.slice(0, 50));
      setStatusMessage(`${data.results.length}件の検索が完了しました（先頭50件を表示中）`);

    } catch (error) {
      console.error(error);
      setStatusMessage("通信エラーが発生しました。");
    }
  };

  // お気に入りボタンを押した時の処理
  const toggleFavorite = async (image_id: number, e: React.MouseEvent) => {
    // 画像自体のクリック判定（モーダルを開く）が発動するのを防ぐ
    e.stopPropagation();

    try {
      // POSTでAPIを叩く
      const response = await fetch(`http://192.168.11.3:8000/favorite/${image_id}`, {
        method: "POST",
      });
      if (!response.ok) throw new Error("通信エラー");

      const data = await response.json();

      // 画面上のハートの色を即座に更新するため、resultsの配列を書き換える
      setResults(results.map(item => 
        item.id === image_id ? { ...item, is_favorite: data.is_favorite } : item
      ));
      
      // もしモーダルを開いている最中なら、モーダル側のデータも更新する
      if (selectedImage && selectedImage.id === image_id) {
        setSelectedImage({ ...selectedImage, is_favorite: data.is_favorite });
      }

    } catch (error) {
      console.error(error);
    }
  };

  return (
    // レイアウト
    <div className="p-2 min-h-screen bg-zinc-900 text-green-400 flex flex-col gap-4">
      <p className="text-lg font-medium">{statusMessage}</p>

      {/* (SearchBarコンポーネントを呼び出し) */}
      <SearchBar 
        query={query}
        setQuery={setQuery}
        onSearch={handleSearch}
        setIsDrawerOpen={setIsDrawerOpen}
        openBookmarkDialog={openBookmarkDialog}
        savedQueries={savedQueries}
      />

      {/* 取得したIDを使って画像を並べる処理 */}
      <ImageGrid 
        results={results} 
        setSelectedImage={setSelectedImage} 
      />

      {/* モーダルの描画処理 (selectedImage に中身がある時だけ表示される) */}
      {selectedImage && (
        <ImageViewer 
          selectedImage={selectedImage} 
          onClose={() => setSelectedImage(null)} 
          onToggleFavorite={toggleFavorite} 
        />
      )}

      {/* ブックマーク関連の処理 */}
      <BookmarkManager
        isDrawerOpen={isDrawerOpen}
        setIsDrawerOpen={setIsDrawerOpen}
        isSaveDialogOpen={isSaveDialogOpen}
        setIsSaveDialogOpen={setIsSaveDialogOpen}
        query={query}
        setQuery={setQuery}
        handleSearch={handleSearch}
        allBookmarks={allBookmarks}
        savedQueries={savedQueries}
        refreshSavedQueries={refreshSavedQueries}
      />
    </div>
  );
}