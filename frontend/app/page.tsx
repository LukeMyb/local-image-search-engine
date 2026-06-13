"use client";

import { useState, useEffect, useRef } from "react";
import { useSystemUI } from "../hooks/useSystemUI";
import { useImageSearch } from "../hooks/useImageSearch";
import { useDrawerSwipe } from "../hooks/useDrawerSwipe";

import BookmarkManager from "../components/BookmarkManager";
import ImageGrid from "../components/ImageGrid";
import ImageViewer from "../components/ImageViewer";
import SearchBar from "../components/SearchBar";
import ControlBar from "../components/ControlBar";

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

  // コントロールバーの表示状態と、スクロール量監視用のRef
  const [isControlBarVisible, setIsControlBarVisible] = useState(true);
  const lastScrollY = useRef(0);

  // 選択モードとソート順のステート
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [sortOrder, setSortOrder] = useState<"score" | "favorite" | "newest">("score");

  // ソート順をローテーションで切り替える関数
  const toggleSortOrder = () => {
    if (sortOrder === "score") setSortOrder("favorite");
    else if (sortOrder === "favorite") setSortOrder("newest");
    else setSortOrder("score");
  };

  // 表示するソート文字列の決定
  const sortText = sortOrder === "score" ? "スコア順" : sortOrder === "favorite" ? "お気に入り" : "新着順";

  // 検索精度モードの見た目切り替え用ステート
  const [isHighAccuracy, setIsHighAccuracy] = useState(true);

  // 選択された画像のIDリストを管理するState
  const [selectedIds, setSelectedIds] = useState<number[]>([]);

  // 選択状態を切り替える関数（すでにあれば外し、なければ追加する）
  const toggleSelection = (id: number) => {
    setSelectedIds((prev) => 
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    );
  };

  // 選択モードがOFFになったら、選択されている画像を自動リセットする
  useEffect(() => {
    if (!isSelectionMode) {
      setSelectedIds([]);
    }
  }, [isSelectionMode]);

  // 検索・画像操作ロジックをフックから取得
  const { 
    results, statusMessage, handleSearch, toggleFavorite, loadMore, hasMore,
    // サジェスト用の状態と関数を取得
    suggestions, isSuggestOpen, setIsSuggestOpen, fetchSuggestions, deleteStyleTag 
  } = useImageSearch();

  // システム制御（ズーム禁止・スクロールロック）を有効化
  useSystemUI({ selectedImage, isDrawerOpen });

  // スワイプによるドロワー展開ロジックを有効化
  useDrawerSwipe({ isDrawerOpen, setIsDrawerOpen, selectedImage });

  // スクロール検知ロジック（下にスクロールで隠し、上にスクロールで表示）
  useEffect(() => {
    const handleScroll = () => {
      const currentScrollY = window.scrollY;
      
      // 50px以上スクロールしている場合のみ判定（一番上にいる時のチラつき防止）
      if (currentScrollY > 50) {
        // 現在位置が前回より下なら非表示、上なら表示
        if (currentScrollY > lastScrollY.current) {
          setIsControlBarVisible(false);
        } else {
          setIsControlBarVisible(true);
        }
      } else {
        setIsControlBarVisible(true);
      }
      lastScrollY.current = currentScrollY;
    };

    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

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

    // 前回の検索クエリを復元し、初期検索を走らせる
    const restoreLastQuery = async () => {
      try {
        const response = await fetch(`${API_BASE_URL}/search/last_query`);
        if (response.ok) {
          const data = await response.json();
          const lastQuery = data.query || "";
          
          setQuery(lastQuery); // 検索窓に前回の文字をセットする
          
          // その文字で初回検索を実行する（空文字の場合はお気に入りが表示される）
          handleSearch(lastQuery); 
        } else {
          handleSearch(""); // 失敗した場合は空（お気に入り）で検索
        }
      } catch (error) {
        console.error("前回クエリの復元エラー:", error);
        handleSearch(""); // ネットワークエラー時も初期検索は走らせる
      }
    };

    restoreLastQuery();
  }, []);

  return (
    // レイアウト
    <div className="min-h-screen bg-zinc-900 text-green-400 flex flex-col relative pb-20 touch-manipulation">
      <div className="p-2 flex flex-col gap-4 md:sticky md:top-0 md:z-40 md:bg-zinc-900/90 md:backdrop-blur-md md:border-b md:border-zinc-800">
        <p className="text-lg font-medium">{statusMessage}</p>

        {/* (SearchBarコンポーネントを呼び出し) */}
        <SearchBar 
          query={query}
          setQuery={setQuery}
          onSearch={(e) => handleSearch(query, e)}
          setIsDrawerOpen={setIsDrawerOpen}
          openBookmarkDialog={openBookmarkDialog}
          savedQueries={savedQueries}
          // 以下、サジェスト用に渡すProps
          suggestions={suggestions}
          isSuggestOpen={isSuggestOpen}
          setIsSuggestOpen={setIsSuggestOpen}
          fetchSuggestions={fetchSuggestions}
          deleteStyleTag={deleteStyleTag}
        />
      </div>

      {/* 画像グリッドなどを配置するメインコンテンツ領域 */}
      <div className="p-2 pt-0 flex-1 flex flex-col gap-4">
        {/* 取得したIDを使って画像を並べる処理 */}
        <ImageGrid 
          results={results} 
          selectedImage={selectedImage}
          setSelectedImage={setSelectedImage} 
          loadMore={loadMore}
          hasMore={hasMore}
          isSelectionMode={isSelectionMode}
          selectedIds={selectedIds}
          toggleSelection={toggleSelection}
        />
      </div>

      {/* モーダルの描画処理 */}
      {selectedImage && (() => {
        // 現在の画像が配列の何番目にあるかを計算
        const currentIndex = results.findIndex((item) => item.id === selectedImage.id);
        const hasPreceding = currentIndex > 0;
        const hasSubsequent = currentIndex < results.length - 1;

        // 前後の画像データも取得する
        const prevImage = hasPreceding ? results[currentIndex - 1] : null;
        const nextImage = hasSubsequent ? results[currentIndex + 1] : null;

        return (
          <ImageViewer 
            selectedImage={selectedImage}
            prevImage={prevImage}
            nextImage={nextImage}
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

      {/* コントロールバーの処理 */}
      {!selectedImage && (
        <ControlBar
          isControlBarVisible={isControlBarVisible}
          isSelectionMode={isSelectionMode}
          setIsSelectionMode={setIsSelectionMode}
          sortText={sortText}
          toggleSortOrder={toggleSortOrder}
          isHighAccuracy={isHighAccuracy}
          setIsHighAccuracy={setIsHighAccuracy}
          selectedIds={selectedIds}
          setSelectedIds={setSelectedIds}
        />
      )}
    </div>
  );
}