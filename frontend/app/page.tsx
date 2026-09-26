"use client";

import { useState, useEffect, useRef, useCallback } from "react";
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

  // グリッドの列数を管理するState（PC用とスマホ用を分離）
  const [gridColsPC, setGridColsPC] = useState(6);
  const [gridColsMobile, setGridColsMobile] = useState(3);

  // ビューアーのUI表示状態を管理するState（初期値はtrue）
  const [isViewerUIVisible, setIsViewerUIVisible] = useState(true);

  // お気に入りフィルターのON/OFF状態を管理するState
  const [isFavoriteFilter, setIsFavoriteFilter] = useState(false);

  // 選択状態を切り替える関数（すでにあれば外し、なければ追加する）
  const toggleSelection = (id: number) => {
    setSelectedIds((prev) => 
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    );
  };

  // ソート順をローテーションで切り替える関数
  const toggleSortOrder = () => {
    let nextSort: "score" | "favorite" | "newest";
    if (sortOrder === "score") nextSort = "favorite";
    else if (sortOrder === "favorite") nextSort = "newest";
    else nextSort = "score";
    
    setSortOrder(nextSort);
    localStorage.setItem("sortOrder", nextSort); // 切り替えた瞬間にlocalStorageに保存する
    handleSearch(query, nextSort, undefined, undefined, isFavoriteFilter); // ソートを切り替えた瞬間に再検索を実行
  };

  // お気に入りフィルターのトグル処理
  const toggleFavoriteFilter = () => {
    const nextState = !isFavoriteFilter;
    setIsFavoriteFilter(nextState);
    localStorage.setItem("isFavoriteFilter", String(nextState)); // 切り替えた瞬間にlocalStorageに保存する
    handleSearch(query, sortOrder, undefined, undefined, nextState);
  };



  // 表示するソート文字列の決定
  const sortText = sortOrder === "score" ? "スコア順" : sortOrder === "favorite" ? "お気に入り" : "新着順";

  // 選択された画像のIDリストを管理するState
  const [selectedIds, setSelectedIds] = useState<number[]>([]);


  // 選択モードがOFFになったら、選択されている画像を自動リセットする
  useEffect(() => {
    if (!isSelectionMode) {
      setSelectedIds([]);
    }
  }, [isSelectionMode]);

  // 検索・画像操作ロジックをフックから取得
  const { 
    results, statusMessage, setStatusMessage, handleSearch, toggleFavorite, loadMore, hasMore,
    // サジェスト用の状態と関数を取得
    suggestions, isSuggestOpen, setIsSuggestOpen, fetchSuggestions, deleteStyleTag 
  } = useImageSearch();

  // 現在のクエリとフィルターを維持したまま、並び順をランダムにして再検索する
  const executeRandomSearch = () => {
    handleSearch(query, "random", undefined, undefined, isFavoriteFilter);
  };

  // 類似画像（同じ髪色）を検索する関数
  const executeSearchSimilar = useCallback((image: any) => {
    if (!image || !image.tags_combined) {
      alert("この画像にはタグ情報がありません。");
      return;
    }

    // 色に関する明確な髪色タグの辞書（配列）
    const validHairColors = [
      "blonde hair", "blonde_hair",
      "brown hair", "brown_hair",
      "black hair", "black_hair",
      "blue hair", "blue_hair",
      "purple hair", "purple_hair",
      "pink hair", "pink_hair",
      "white hair", "white_hair",
      "red hair", "red_hair",
      "grey hair", "grey_hair", "gray hair", "gray_hair",
      "green hair", "green_hair",
      "silver hair", "silver_hair",
      "orange hair", "orange_hair",
      "aqua hair", "aqua_hair",
      "light blue hair", "light_blue_hair",
      "light green hair", "light_green_hair",
      "dark blue hair", "dark_blue_hair",
      "dark brown hair", "dark_brown_hair",
    ];

    // 色に関する明確な目の色タグの辞書（配列）
    const validEyeColors = [
      "blue eyes", "blue_eyes",
      "red eyes", "red_eyes",
      "brown eyes", "brown_eyes",
      "green eyes", "green_eyes",
      "purple eyes", "purple_eyes",
      "yellow eyes", "yellow_eyes",
      "pink eyes", "pink_eyes",
      "black eyes", "black_eyes",
      "aqua eyes", "aqua_eyes",
      "orange eyes", "orange_eyes",
      "grey eyes", "grey_eyes", "gray eyes", "gray_eyes",
      "white eyes", "white_eyes",
      "multicolored eyes", "multicolored_eyes",
    ];

    // マルチカラー系のタグ（AND検索にするもの）
    const multicolorKeywords = ["multicolored", "two-tone", "streaked", "colored inner"];

    // カンマ区切りのタグ文字列を配列に分割
    const tags = image.tags_combined.split(',').map((t: string) => t.trim().toLowerCase());
    
    // 定義した髪色タグに含まれるものだけを抽出（wet_hair 等を除外）
    const hairTags = tags.filter((t: string) => 
      validHairColors.includes(t) || multicolorKeywords.some(k => t.includes(k) && (t.endsWith(' hair') || t.endsWith('_hair')))
    );
    
    if (hairTags.length === 0) {
      alert("この画像には髪色のタグがありません。");
      return;
    }

    // 検索窓の仕様（空白はAND、| はOR）に合わせるため、抽出したタグの内部の空白を _ に置換しておく
    const multiTags = hairTags
      .filter((t: string) => multicolorKeywords.some(k => t.includes(k)))
      .map((t: string) => t.replace(/\s+/g, '_'));

    const normalTags = hairTags
      .filter((t: string) => !multicolorKeywords.some(k => t.includes(k)))
      .map((t: string) => t.replace(/\s+/g, '_'));

    const queryParts = [];
    if (multiTags.length > 0) {
      // マルチカラー系同士はOR検索 ( | 区切り )
      queryParts.push(multiTags.join('|'));
    }
    if (normalTags.length > 0) {
      if (multiTags.length > 0) {
        // マルチカラーが含まれる場合は、混色を意図していると見なし AND (空白区切り) で繋ぐ
        queryParts.push(normalTags.join(' '));
      } else {
        // 通常の髪色タグのみの場合は、表記揺れや複数キャラ対応のため OR ( | 区切り ) で繋ぐ
        queryParts.push(normalTags.join('|'));
      }
    }

    // 目の色の処理
    const hasClosedEyes = tags.includes("closed eyes") || tags.includes("closed_eyes");
    if (hasClosedEyes) {
      // 目が閉じている場合は目の色による絞り込みはせず、closed_eyesをORグループとして追加
      queryParts.push("closed_eyes");
    } else {
      // 目の色のタグがあれば抽出
      const eyeTags = tags.filter((t: string) => validEyeColors.includes(t));
      if (eyeTags.length > 0) {
        // 目の色のタグも空白をアンダースコアに変換して、複数あれば OR ( | ) で繋ぐ
        const formattedEyeTags = eyeTags.map((t: string) => t.replace(/\s+/g, '_'));
        queryParts.push(formattedEyeTags.join('|'));
      }
    }

    const newQuery = queryParts.join(' ').trim();

    if (newQuery) {
      setQuery(newQuery);
      setSelectedImage(null); // ビューアーを閉じる
      handleSearch(newQuery, "score", undefined, undefined, isFavoriteFilter);
    }
  }, [handleSearch, isFavoriteFilter]);

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

    // localStorageから前回のソート順を読み込む（無い場合は "score" にする）
    const savedSort = (localStorage.getItem("sortOrder") as "score" | "favorite" | "newest") || "score";
    setSortOrder(savedSort);

    // localStorageから前回のビューアーUI表示状態を読み込む
    const savedUIVisible = localStorage.getItem("isViewerUIVisible");
    if (savedUIVisible !== null) {
      setIsViewerUIVisible(savedUIVisible === "true");
    }

    // localStorageから列数の設定を読み込む
    const savedColsPC = localStorage.getItem("gridColsPC");
    if (savedColsPC) setGridColsPC(parseInt(savedColsPC, 10));
    const savedColsMobile = localStorage.getItem("gridColsMobile");
    if (savedColsMobile) setGridColsMobile(parseInt(savedColsMobile, 10));

    // localStorageからお気に入りフィルター状態を読み込む
    const savedFavoriteFilterStr = localStorage.getItem("isFavoriteFilter");
    const savedFavoriteFilter = savedFavoriteFilterStr === "true";
    setIsFavoriteFilter(savedFavoriteFilter);

    // 前回の検索クエリを復元し、初期検索を走らせる
    const restoreLastQuery = () => {
      // localStorageから読み込んで検索を実行する
      const lastQuery = localStorage.getItem("lastQuery") || "";
      setQuery(lastQuery);
      handleSearch(lastQuery, savedSort, undefined, undefined, savedFavoriteFilter);
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
          onSearch={(e) => handleSearch(query, sortOrder, e, undefined, isFavoriteFilter)}
          setIsDrawerOpen={setIsDrawerOpen}
          openBookmarkDialog={openBookmarkDialog}
          savedQueries={savedQueries}
          // 以下、サジェスト用に渡すProps
          suggestions={suggestions}
          isSuggestOpen={isSuggestOpen}
          setIsSuggestOpen={setIsSuggestOpen}
          fetchSuggestions={fetchSuggestions}
          deleteStyleTag={deleteStyleTag}
          // お気に入りフィルター
          isFavoriteFilter={isFavoriteFilter}
          onToggleFavoriteFilter={toggleFavoriteFilter}
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

          // 列数の状態と、変更時にlocalStorageにも保存する更新関数を渡す
          gridColsPC={gridColsPC}
          setGridColsPC={(cols) => {
            setGridColsPC(cols);
            localStorage.setItem("gridColsPC", String(cols));
          }}
          gridColsMobile={gridColsMobile}
          setGridColsMobile={(cols) => {
            setGridColsMobile(cols);
            localStorage.setItem("gridColsMobile", String(cols));
          }}
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
            onSearchSimilar={executeSearchSimilar}
            onNext={() => hasSubsequent && setSelectedImage(results[currentIndex + 1])}
            onPrev={() => hasPreceding && setSelectedImage(results[currentIndex - 1])}
            hasPreceding={hasPreceding}
            hasSubsequent={hasSubsequent}

            // UIの表示状態と、トグル＆保存を行う関数を渡す
            isUIVisible={isViewerUIVisible}
            onToggleUI={() => {
              const nextState = !isViewerUIVisible;
              setIsViewerUIVisible(nextState);
              localStorage.setItem("isViewerUIVisible", String(nextState)); // 変更と同時に保存
            }}
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
        handleSearch={(e, oq) => handleSearch(query, sortOrder, e, oq, isFavoriteFilter)}
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
          selectedIds={selectedIds}
          setSelectedIds={setSelectedIds}
          setStatusMessage={setStatusMessage}
          executeRandomSearch={executeRandomSearch}
        />
      )}
    </div>
  );
}