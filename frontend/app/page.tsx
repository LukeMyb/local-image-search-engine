"use client";

import { useState, useEffect, useRef, useCallback } from "react";
import { RotateCw, Zap, Loader2, Feather, Settings } from "lucide-react";
import { useSystemUI } from "../hooks/useSystemUI";
import { useImageSearch } from "../hooks/useImageSearch";
import { useDrawerSwipe } from "../hooks/useDrawerSwipe";

import BookmarkManager from "../components/BookmarkManager";
import ImageGrid from "../components/ImageGrid";
import ImageViewer from "../components/ImageViewer";
import SearchBar from "../components/SearchBar";
import ControlBar from "../components/ControlBar";
import SettingsModal from "../components/SettingsModal";

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
  // 最後にビューアーで開いていた画像のIDを保持するRef（ソート順変更時の中心保持用）
  const lastViewedIdRef = useRef<number | null>(null);

  // ビューアーで画像を開いている間（スワイプ移動を含む）は常に最新のIDを記録する
  useEffect(() => {
    if (selectedImage) {
      lastViewedIdRef.current = selectedImage.id;
    }
  }, [selectedImage]);

  // ドロワーの開閉状態を管理する変数
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  // ブックマーク保存ダイアログの開閉と入力内容を管理
  const [isSaveDialogOpen, setIsSaveDialogOpen] = useState(false);

  // 設定モーダルの開閉状態を管理
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);

  // 全ブックマークの完全な情報を保持する
  const [allBookmarks, setAllBookmarks] = useState<Bookmark[]>([]);
  // 現在保存されているすべての「クエリ（文字列）」のリストを保持する変数
  const [savedQueries, setSavedQueries] = useState<string[]>([]);

  // 選択モードとソート順のステート
  const [isSelectionMode, setIsSelectionMode] = useState(false);
  const [sortOrder, setSortOrder] = useState<"score" | "newest">("score");
  // 直前のソートがランダム表示だったかどうかと、その乱数シード値を管理するステート
  const [isRandomSorted, setIsRandomSorted] = useState(false);
  const [randomSeed, setRandomSeed] = useState<number | null>(null);

  // ランダムソート状態とシード値をState・localStorageの双方に同期するヘルパー
  const updateRandomSortState = useCallback((isRandom: boolean, seed: number | null = null) => {
    setIsRandomSorted(isRandom);
    setRandomSeed(seed);
    localStorage.setItem("isRandomSorted", String(isRandom));
    if (seed !== null) {
      localStorage.setItem("randomSeed", String(seed));
    } else {
      localStorage.removeItem("randomSeed");
    }
  }, []);

  // グリッドの列数を管理するState（PC用とスマホ用を分離）
  const [gridColsPC, setGridColsPC] = useState(6);
  const [gridColsMobile, setGridColsMobile] = useState(3);

  // ビューアーのUI表示状態を管理するState（初期値はtrue）
  const [isViewerUIVisible, setIsViewerUIVisible] = useState(true);

  // ビューアーでのゴミ箱移動時に確認ダイアログを表示するかどうかのState（初期値はtrue）
  const [confirmTrashInViewer, setConfirmTrashInViewer] = useState(true);

  // 検索バー横の検索ボタンを表示するかどうかのState（初期値はtrue）
  const [showSearchButton, setShowSearchButton] = useState(true);

  // 検索バー右側のゴミ箱フィルターボタンを表示するかどうかのState（初期値はtrue）
  const [showTrashButton, setShowTrashButton] = useState(true);

  // 類似画像検索時に周囲（保存日時が近い）の画像のタグも参照するかどうかのState（実験的機能・初期値はfalse）
  // TODO: 現時点では設定値の保持のみで、executeSearchSimilar 側のロジックは未実装
  const [useNeighborsForSimilar, setUseNeighborsForSimilar] = useState(false);

  // お気に入りフィルターのON/OFF状態を管理するState
  const [isFavoriteFilter, setIsFavoriteFilter] = useState(false);

  // ゴミ箱フィルターのON/OFF状態を管理するState
  const [isTrashFilter, setIsTrashFilter] = useState(false);

  // サーバーモード状態（"light" | "starting" | "heavy"）を管理するState
  const [serverMode, setServerMode] = useState<"light" | "starting" | "heavy">("light");

  // 重量モードのアイドル自動停止時間（秒）を管理するState（初期値は300秒＝5分）
  const [heavyIdleTimeout, setHeavyIdleTimeout] = useState<number>(300);

  // 絵柄検索の類似度しきい値を管理するState（初期値は0.98）
  const [styleThreshold, setStyleThreshold] = useState<number>(0.98);

  // 選択状態を切り替える関数（すでにあれば外し、なければ追加する）
  const toggleSelection = (id: number) => {
    setSelectedIds((prev) => 
      prev.includes(id) ? prev.filter((i) => i !== id) : [...prev, id]
    );
  };

  // ソート順をローテーションで切り替える関数
  const toggleSortOrder = () => {
    // 直前のソートがランダムだった場合は、ボタンの表示は変えずに現在表示されているソート順をそのまま適用する
    if (isRandomSorted) {
      updateRandomSortState(false, null);
      handleSearch(query, sortOrder, undefined, undefined, isFavoriteFilter, lastViewedIdRef.current, isTrashFilter);
      return;
    }

    const nextSort: "score" | "newest" = sortOrder === "score" ? "newest" : "score";
    
    setSortOrder(nextSort);
    localStorage.setItem("sortOrder", nextSort); // 切り替えた瞬間にlocalStorageに保存する
    // 最後にビューアーで開いた画像を中心に保持したまま再検索を実行
    handleSearch(query, nextSort, undefined, undefined, isFavoriteFilter, lastViewedIdRef.current, isTrashFilter);
  };

  // お気に入りフィルターのトグル処理
  const toggleFavoriteFilter = () => {
    const nextState = !isFavoriteFilter;
    setIsFavoriteFilter(nextState);
    localStorage.setItem("isFavoriteFilter", String(nextState)); // 切り替えた瞬間にlocalStorageに保存する
    const activeSort = isRandomSorted ? "random" : sortOrder;
    handleSearch(
      query,
      activeSort,
      undefined,
      undefined,
      nextState,
      null,
      isTrashFilter,
      isRandomSorted ? randomSeed : null
    );
  };

  // ゴミ箱フィルターのトグル処理
  const toggleTrashFilter = () => {
    const nextState = !isTrashFilter;
    setIsTrashFilter(nextState);
    setIsSelectionMode(false);
    const activeSort = isRandomSorted ? "random" : sortOrder;
    handleSearch(
      query,
      activeSort,
      undefined,
      undefined,
      isFavoriteFilter,
      null,
      nextState,
      isRandomSorted ? randomSeed : null
    );
  };



  // 表示するソート文字列の決定
  const sortText = sortOrder === "score" ? "スコア順" : "新着順";

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
    results, statusMessage, setStatusMessage, handleSearch, toggleFavorite, trashImages, restoreImages,
    loadMore, loadPrev, resetToTop, hasMore, hasPrev, focusRequest, anchorScrollRequest,
    // サジェスト用の状態と関数を取得
    suggestions, isSuggestOpen, setIsSuggestOpen, fetchSuggestions, deleteStyleTag 
  } = useImageSearch();

  // サーバーから現在の設定値（自動停止時間・絵柄検索しきい値）を取得して同期する関数
  const fetchAppSettings = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/settings`);
      if (!res.ok) return;
      const data = await res.json();
      if (typeof data.heavy_idle_timeout === "number") {
        setHeavyIdleTimeout(data.heavy_idle_timeout);
        localStorage.setItem("heavyIdleTimeout", String(data.heavy_idle_timeout));
      }
      if (typeof data.style_threshold === "number") {
        setStyleThreshold(data.style_threshold);
        localStorage.setItem("styleThreshold", String(data.style_threshold));
      }
    } catch (error) {
      console.error("設定の取得エラー:", error);
    }
  }, []);

  // サーバーから現在のモード状態を取得する関数
  const fetchServerMode = useCallback(async () => {
    try {
      const res = await fetch(`${API_BASE_URL}/mode`);
      if (!res.ok) return;
      const data = await res.json();
      if (data.mode === "light" || data.mode === "starting" || data.mode === "heavy") {
        setServerMode(data.mode);
      }
      if (typeof data.idle_timeout === "number") {
        setHeavyIdleTimeout(data.idle_timeout);
        localStorage.setItem("heavyIdleTimeout", String(data.idle_timeout));
      }
    } catch (error) {
      console.error("モード状態の取得エラー:", error);
    }
  }, []);

  // 重量モード起動中("starting")の間、完了するまで定期的にステータスをポーリングする（最大35秒タイムアウト）
  useEffect(() => {
    if (serverMode !== "starting") return;

    const startTime = Date.now();
    const interval = setInterval(async () => {
      if (Date.now() - startTime > 35000) {
        setServerMode("light");
        setStatusMessage("重量モードの起動がタイムアウトしました");
        return;
      }
      try {
        const res = await fetch(`${API_BASE_URL}/mode`);
        if (!res.ok) return;
        const data = await res.json();
        if (data.mode === "heavy") {
          setServerMode("heavy");
        } else if (data.mode === "light") {
          setServerMode("light");
          if (data.error) {
            setStatusMessage(`重量モードの起動に失敗しました: ${data.error}`);
          }
        }
      } catch (error) {
        console.error("モードポーリングエラー:", error);
      }
    }, 800);

    return () => clearInterval(interval);
  }, [serverMode, setStatusMessage]);

  // 重量モード("heavy")稼働中は、ページを開いている間20秒ごとに生存確認（ハートビート）を送り、
  // タブ復帰時（visibilitychange / focus）にも最新のモード状態を同期する
  useEffect(() => {
    const handleVisibilityOrFocus = () => {
      if (document.visibilityState === "visible") {
        fetchServerMode();
      }
    };
    window.addEventListener("focus", handleVisibilityOrFocus);
    document.addEventListener("visibilitychange", handleVisibilityOrFocus);

    let heartbeat: ReturnType<typeof setInterval> | null = null;
    if (serverMode === "heavy") {
      heartbeat = setInterval(() => {
        if (document.visibilityState === "visible") {
          fetchServerMode();
        }
      }, 20000);
    }

    return () => {
      window.removeEventListener("focus", handleVisibilityOrFocus);
      document.removeEventListener("visibilitychange", handleVisibilityOrFocus);
      if (heartbeat) clearInterval(heartbeat);
    };
  }, [serverMode, fetchServerMode]);

  // フロントエンドから軽量モード⇔重量モードを切り替える関数
  const toggleServerMode = async () => {
    if (serverMode === "starting") return;
    const targetMode = serverMode === "heavy" ? "light" : "heavy";

    try {
      if (targetMode === "heavy") {
        setServerMode("starting");
      }
      const res = await fetch(`${API_BASE_URL}/mode`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: targetMode, wait: false }),
      });
      if (!res.ok) throw new Error("モードの切り替えに失敗しました");
      const data = await res.json();
      if (data.mode === "light" || data.mode === "starting" || data.mode === "heavy") {
        setServerMode(data.mode);
      }
    } catch (error) {
      console.error("モード切り替えエラー:", error);
      setServerMode("light");
    }
  };

  // 一括削除・復元でアンカー位置が更新された場合は、ソート変更時の中心保持IDにも反映する
  useEffect(() => {
    if (anchorScrollRequest) {
      lastViewedIdRef.current = anchorScrollRequest.id;
    }
  }, [anchorScrollRequest]);

  // 選択中の画像にお気に入り（いいね）画像が含まれているかどうかを判定
  const hasFavoriteInSelection = selectedIds.some((id) =>
    results.some((item) => item.id === id && item.is_favorite === 1)
  );

  // ビューアーから1枚の画像を論理削除し、前後の画像へ切り替える処理
  const handleTrashInViewer = useCallback(async (imageId: number) => {
    const target = results.find((item) => item.id === imageId);
    if (target?.is_favorite === 1 || selectedImage?.is_favorite === 1) return;

    const currentIndex = results.findIndex((item) => item.id === imageId);
    const nextCandidate =
      currentIndex !== -1 && currentIndex < results.length - 1
        ? results[currentIndex + 1]
        : currentIndex > 0
        ? results[currentIndex - 1]
        : null;

    const trashed = await trashImages([imageId]);
    if (trashed.length > 0) {
      setSelectedImage(nextCandidate);
    }
  }, [results, selectedImage, trashImages]);

  // 選択モードで選択された複数画像を一括で論理削除する処理
  const handleTrashSelected = useCallback(async () => {
    if (selectedIds.length === 0 || hasFavoriteInSelection) return;
    const trashed = await trashImages(selectedIds);
    if (trashed.length > 0) {
      setSelectedIds([]);
      setIsSelectionMode(false);
    }
  }, [selectedIds, hasFavoriteInSelection, trashImages]);

  // ゴミ箱表示中：ビューアーから1枚の画像を復元し、前後の画像へ切り替える処理
  const handleRestoreInViewer = useCallback(async (imageId: number) => {
    const currentIndex = results.findIndex((item) => item.id === imageId);
    const nextCandidate =
      currentIndex !== -1 && currentIndex < results.length - 1
        ? results[currentIndex + 1]
        : currentIndex > 0
        ? results[currentIndex - 1]
        : null;

    const restored = await restoreImages([imageId]);
    if (restored.length > 0) {
      setSelectedImage(nextCandidate);
    }
  }, [results, restoreImages]);

  // ゴミ箱表示中：選択モードで選択された複数画像を一括で復元する処理
  const handleRestoreSelected = useCallback(async () => {
    if (selectedIds.length === 0) return;
    const restored = await restoreImages(selectedIds);
    if (restored.length > 0) {
      setSelectedIds([]);
      setIsSelectionMode(false);
    }
  }, [selectedIds, restoreImages]);

  // 現在のクエリとフィルターを維持したまま、新しい乱数シードで並び順をランダムにして再検索する
  const executeRandomSearch = () => {
    const newSeed = Math.floor(Math.random() * 2147483647) + 1;
    updateRandomSortState(true, newSeed);
    handleSearch(query, "random", undefined, undefined, isFavoriteFilter, null, isTrashFilter, newSeed);
  };

  // 現在の検索条件・ソート順（ランダム時はシード値も）を維持したままグリッドを再読み込みする
  const reloadGrid = useCallback(() => {
    const activeSort = isRandomSorted ? "random" : sortOrder;
    handleSearch(
      query,
      activeSort,
      undefined,
      undefined,
      isFavoriteFilter,
      null,
      isTrashFilter,
      isRandomSorted ? randomSeed : null
    );
  }, [query, sortOrder, isRandomSorted, randomSeed, isFavoriteFilter, isTrashFilter, handleSearch]);

  // 画面最上部でのプルリフレッシュ（下引っ張り再読み込み）用のStateとRef
  const [pullDistance, setPullDistance] = useState(0);
  const pullDistanceRef = useRef(0);
  const pullStartRef = useRef<{ x: number; y: number } | null>(null);
  const PULL_REFRESH_THRESHOLD = 55;

  // 画面最上部でさらに上方向へスクロール（下へスワイプ）した時にグリッドを再読み込みする処理
  useEffect(() => {
    if (selectedImage || isDrawerOpen || isSaveDialogOpen || isSettingsOpen || isSuggestOpen || hasPrev) {
      pullStartRef.current = null;
      pullDistanceRef.current = 0;
      setPullDistance(0);
      return;
    }

    const handleTouchStart = (e: TouchEvent) => {
      if (e.touches.length !== 1) {
        pullStartRef.current = null;
        return;
      }
      // 検索窓や入力欄の操作中はプルリフレッシュを開始しない
      const target = e.target as HTMLElement | null;
      if (target instanceof HTMLInputElement || target instanceof HTMLTextAreaElement) {
        pullStartRef.current = null;
        return;
      }
      // 画面の一番上にいる時のみ開始（左端40px以内のドロワースワイプ領域は除外）
      if (window.scrollY <= 0 && e.touches[0].clientX > 40) {
        pullStartRef.current = {
          x: e.touches[0].clientX,
          y: e.touches[0].clientY,
        };
      } else {
        pullStartRef.current = null;
      }
    };

    const handleTouchMove = (e: TouchEvent) => {
      if (!pullStartRef.current || e.touches.length !== 1) return;

      if (window.scrollY > 0) {
        pullStartRef.current = null;
        if (pullDistanceRef.current > 0) {
          pullDistanceRef.current = 0;
          setPullDistance(0);
        }
        return;
      }

      const diffX = e.touches[0].clientX - pullStartRef.current.x;
      const diffY = e.touches[0].clientY - pullStartRef.current.y;

      // 縦方向（下向き）のスワイプである場合のみプル距離を更新
      if (diffY > 10 && Math.abs(diffY) > Math.abs(diffX)) {
        const damped = Math.min((diffY - 10) * 0.45, 96);
        pullDistanceRef.current = damped;
        setPullDistance(damped);
      } else if (diffY <= 0 && pullDistanceRef.current > 0) {
        pullDistanceRef.current = 0;
        setPullDistance(0);
      }
    };

    const handleTouchEnd = () => {
      if (!pullStartRef.current) return;
      const finalPull = pullDistanceRef.current;
      pullStartRef.current = null;
      pullDistanceRef.current = 0;
      setPullDistance(0);

      if (finalPull >= PULL_REFRESH_THRESHOLD && window.scrollY <= 0) {
        reloadGrid();
      }
    };

    window.addEventListener("touchstart", handleTouchStart, { passive: true });
    window.addEventListener("touchmove", handleTouchMove, { passive: true });
    window.addEventListener("touchend", handleTouchEnd, { passive: true });
    window.addEventListener("touchcancel", handleTouchEnd, { passive: true });

    return () => {
      window.removeEventListener("touchstart", handleTouchStart);
      window.removeEventListener("touchmove", handleTouchMove);
      window.removeEventListener("touchend", handleTouchEnd);
      window.removeEventListener("touchcancel", handleTouchEnd);
    };
  }, [selectedImage, isDrawerOpen, isSaveDialogOpen, isSettingsOpen, isSuggestOpen, hasPrev, reloadGrid]);

  // PCの「r」キーでグリッドを再読み込みする処理
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.ctrlKey || e.metaKey || e.altKey) return;
      if (e.key !== "r" && e.key !== "R") return;
      if (selectedImage || isDrawerOpen || isSaveDialogOpen || isSettingsOpen) return;

      const target = e.target as HTMLElement | null;
      if (
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        target?.isContentEditable
      ) {
        return;
      }

      e.preventDefault();
      reloadGrid();
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [selectedImage, isDrawerOpen, isSaveDialogOpen, isSettingsOpen, reloadGrid]);

  // 類似画像検索（同じ髪色・目の色の検索）を実行する関数
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
        // 目の色のタグも空白をアンダースコアに変換して、closed_eyes も含めて OR ( | ) で繋ぐ
        const formattedEyeTags = eyeTags.map((t: string) => t.replace(/\s+/g, '_'));
        queryParts.push(["closed_eyes", ...formattedEyeTags].join('|'));
      }
    }

    const newQuery = queryParts.join(' ').trim();

    if (newQuery) {
      setQuery(newQuery);
      setSelectedImage(null); // ビューアーを閉じる
      updateRandomSortState(false, null);
      handleSearch(newQuery, "score", undefined, undefined, isFavoriteFilter, null, isTrashFilter);
    }
  }, [handleSearch, isFavoriteFilter, isTrashFilter, updateRandomSortState]);

  // 検索窓をリセットし、ソート順を新着順にして現在の画像の位置へスクロール移動する関数
  const executeJumpToImage = useCallback((image: SearchResult) => {
    if (!image) return;

    // ビューアーを閉じた直後のスクロール移動がブロックされないよう、スクロールロックを先行解除
    document.documentElement.style.overflow = "";
    document.documentElement.style.overscrollBehavior = "";
    document.body.style.overflow = "";
    document.body.style.overscrollBehavior = "";

    setQuery("");
    setSortOrder("newest");
    localStorage.setItem("sortOrder", "newest");
    updateRandomSortState(false, null);
    lastViewedIdRef.current = image.id;
    setSelectedImage(null); // ビューアーを閉じる

    // お気に入りフィルターがONかつ対象画像がお気に入りではない場合は、画像が表示されるようフィルターを解除
    let nextFavoriteFilter = isFavoriteFilter;
    if (isFavoriteFilter && image.is_favorite !== 1) {
      nextFavoriteFilter = false;
      setIsFavoriteFilter(false);
      localStorage.setItem("isFavoriteFilter", "false");
    }

    handleSearch("", "newest", undefined, undefined, nextFavoriteFilter, image.id, isTrashFilter);
  }, [handleSearch, isFavoriteFilter, isTrashFilter, updateRandomSortState]);

  // システム制御（ズーム禁止・スクロールロック）を有効化
  useSystemUI({ selectedImage, isDrawerOpen, isSettingsOpen });

  // スワイプによるドロワー展開ロジックを有効化
  useDrawerSwipe({ isDrawerOpen, setIsDrawerOpen, selectedImage, isSettingsOpen });

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
    fetchServerMode();
    fetchAppSettings();

    // localStorageから前回のソート順を読み込む（無い場合や無効な値の場合は "score" にする）
    const rawSavedSort = localStorage.getItem("sortOrder");
    const savedSort: "score" | "newest" = rawSavedSort === "newest" ? "newest" : "score";
    setSortOrder(savedSort);

    // localStorageから前回のランダムソート状態とシード値を読み込む
    const savedRandomSorted = localStorage.getItem("isRandomSorted") === "true";
    const savedSeedStr = localStorage.getItem("randomSeed");
    const parsedSeed = savedSeedStr ? parseInt(savedSeedStr, 10) : NaN;
    const savedSeed = !isNaN(parsedSeed) ? parsedSeed : null;
    const effectiveRandom = savedRandomSorted && savedSeed !== null;
    setIsRandomSorted(effectiveRandom);
    setRandomSeed(effectiveRandom ? savedSeed : null);

    // localStorageから前回のビューアーUI表示状態を読み込む
    const savedUIVisible = localStorage.getItem("isViewerUIVisible");
    if (savedUIVisible !== null) {
      setIsViewerUIVisible(savedUIVisible === "true");
    }

    // localStorageからビューアー削除時の確認ダイアログ設定を読み込む
    const savedConfirmTrash = localStorage.getItem("confirmTrashInViewer");
    if (savedConfirmTrash !== null) {
      setConfirmTrashInViewer(savedConfirmTrash === "true");
    }

    // localStorageから検索ボタンの表示設定を読み込む
    const savedShowSearchBtn = localStorage.getItem("showSearchButton");
    if (savedShowSearchBtn !== null) {
      setShowSearchButton(savedShowSearchBtn === "true");
    }

    // localStorageからゴミ箱ボタンの表示設定を読み込む
    const savedShowTrashBtn = localStorage.getItem("showTrashButton");
    if (savedShowTrashBtn !== null) {
      setShowTrashButton(savedShowTrashBtn === "true");
    }

    // localStorageから類似画像検索で周囲の画像を参照する設定を読み込む
    const savedUseNeighbors = localStorage.getItem("useNeighborsForSimilar");
    if (savedUseNeighbors !== null) {
      setUseNeighborsForSimilar(savedUseNeighbors === "true");
    }

    // localStorageから重量モードの自動停止時間を読み込む
    const savedIdleTimeout = localStorage.getItem("heavyIdleTimeout");
    if (savedIdleTimeout !== null) {
      const parsedTimeout = parseInt(savedIdleTimeout, 10);
      if (!isNaN(parsedTimeout) && parsedTimeout >= 0) {
        setHeavyIdleTimeout(parsedTimeout);
      }
    }

    // localStorageから絵柄検索の類似度しきい値を読み込む
    const savedStyleThreshold = localStorage.getItem("styleThreshold");
    if (savedStyleThreshold !== null) {
      const parsedThreshold = parseFloat(savedStyleThreshold);
      if (!isNaN(parsedThreshold) && parsedThreshold >= 0.97 && parsedThreshold <= 0.99) {
        setStyleThreshold(parsedThreshold);
      }
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
      const initialSort = effectiveRandom ? "random" : savedSort;
      handleSearch(
        lastQuery,
        initialSort,
        undefined,
        undefined,
        savedFavoriteFilter,
        null,
        false,
        effectiveRandom ? savedSeed : null
      );
    };

    restoreLastQuery();
  }, []);

  return (
    // レイアウト
    <div className="min-h-screen bg-zinc-900 text-green-400 flex flex-col relative pb-20 touch-manipulation">
      {/* 最上部でのプルリフレッシュ（下スワイプ再読み込み）インジケーター */}
      {pullDistance > 0 && (
        <div
          className="fixed left-1/2 -translate-x-1/2 z-50 pointer-events-none transition-transform duration-75"
          style={{ top: `${Math.min(pullDistance, 72)}px` }}
        >
          <div
            className={`p-2.5 rounded-full shadow-xl border backdrop-blur-md flex items-center justify-center transition-colors ${
              pullDistance >= PULL_REFRESH_THRESHOLD
                ? "bg-green-500/20 border-green-400 text-green-400"
                : "bg-zinc-800/90 border-zinc-700 text-zinc-400"
            }`}
          >
            <RotateCw
              size={20}
              style={{ transform: `rotate(${pullDistance * 4}deg)` }}
            />
          </div>
        </div>
      )}

      <div className="p-2 flex flex-col gap-4 md:sticky md:top-0 md:z-40 md:bg-zinc-900/90 md:backdrop-blur-md md:border-b md:border-zinc-800">
        <div className="flex items-center justify-between gap-2">
          <p className="text-lg font-medium truncate">{statusMessage}</p>

          <div className="shrink-0 flex items-center gap-2">
            {/* サーバーモード（軽量 / 重量）切り替えボタン */}
            <button
              type="button"
              onClick={toggleServerMode}
              disabled={serverMode === "starting"}
              title={
                serverMode === "heavy"
                  ? "クリックで軽量モードに戻す（メモリ解放）"
                  : serverMode === "starting"
                  ? "重量モード（AI）を起動しています..."
                  : "クリックで重量モード（AI検索・絵柄作成）を起動"
              }
              className={`shrink-0 flex items-center gap-1.5 px-3 py-1.5 rounded-full text-xs font-medium border transition-all cursor-pointer ${
                serverMode === "heavy"
                  ? "bg-blue-500/20 border-blue-500/50 text-blue-300 hover:bg-blue-500/30"
                  : serverMode === "starting"
                  ? "bg-amber-500/20 border-amber-500/40 text-amber-300 cursor-wait"
                  : "bg-zinc-800 border-zinc-700 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200"
              }`}
            >
              {serverMode === "heavy" ? (
                <>
                  <Zap size={14} className="fill-current text-blue-400" />
                  <span>重量版 ON</span>
                </>
              ) : serverMode === "starting" ? (
                <>
                  <Loader2 size={14} className="animate-spin text-amber-400" />
                  <span>重量版 起動中...</span>
                </>
              ) : (
                <>
                  <Feather size={14} className="text-zinc-400" />
                  <span>軽量版</span>
                </>
              )}
            </button>

            {/* 設定モーダルを開くボタン */}
            <button
              type="button"
              onClick={() => setIsSettingsOpen(true)}
              title="設定を開く"
              className="p-1.5 rounded-full bg-zinc-800 border border-zinc-700 text-zinc-400 hover:bg-zinc-700 hover:text-zinc-200 transition-colors flex items-center justify-center cursor-pointer"
            >
              <Settings size={16} />
            </button>
          </div>
        </div>

        {/* 検索バー */}
        <SearchBar 
          query={query}
          setQuery={setQuery}
          onSearch={(e) => {
            updateRandomSortState(false, null);
            handleSearch(query, sortOrder, e, undefined, isFavoriteFilter, null, isTrashFilter);
          }}
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
          // ゴミ箱フィルター
          isTrashFilter={isTrashFilter}
          onToggleTrashFilter={toggleTrashFilter}
          // 検索ボタンの表示/非表示
          showSearchButton={showSearchButton}
          // ゴミ箱フィルターボタンの表示/非表示
          showTrashButton={showTrashButton}
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
          loadPrev={loadPrev}
          hasPrev={hasPrev}
          resetToTop={resetToTop}
          focusRequest={focusRequest}
          anchorScrollRequest={anchorScrollRequest}
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
            onJumpToImage={executeJumpToImage}
            isTrashMode={isTrashFilter}
            confirmTrash={confirmTrashInViewer}
            onTrash={handleTrashInViewer}
            onRestore={handleRestoreInViewer}
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
        handleSearch={(e, oq) => {
          updateRandomSortState(false, null);
          return handleSearch(query, sortOrder, e, oq, isFavoriteFilter, null, isTrashFilter);
        }}
        allBookmarks={allBookmarks}
        savedQueries={savedQueries}
        refreshSavedQueries={refreshSavedQueries}
      />

      {/* 設定モーダルの処理 */}
      <SettingsModal
        isOpen={isSettingsOpen}
        onClose={() => setIsSettingsOpen(false)}
        showSearchButton={showSearchButton}
        onChangeShowSearchButton={(enabled) => {
          setShowSearchButton(enabled);
          localStorage.setItem("showSearchButton", String(enabled));
        }}
        showTrashButton={showTrashButton}
        onChangeShowTrashButton={(enabled) => {
          setShowTrashButton(enabled);
          localStorage.setItem("showTrashButton", String(enabled));
        }}
        confirmTrashInViewer={confirmTrashInViewer}
        onChangeConfirmTrashInViewer={(enabled) => {
          setConfirmTrashInViewer(enabled);
          localStorage.setItem("confirmTrashInViewer", String(enabled));
        }}
        useNeighborsForSimilar={useNeighborsForSimilar}
        onChangeUseNeighborsForSimilar={(enabled) => {
          setUseNeighborsForSimilar(enabled);
          localStorage.setItem("useNeighborsForSimilar", String(enabled));
        }}
        heavyIdleTimeout={heavyIdleTimeout}
        onChangeHeavyIdleTimeout={async (seconds) => {
          setHeavyIdleTimeout(seconds);
          localStorage.setItem("heavyIdleTimeout", String(seconds));
          try {
            await fetch(`${API_BASE_URL}/settings`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ heavy_idle_timeout: seconds }),
            });
          } catch (error) {
            console.error("自動停止時間の設定保存エラー:", error);
          }
        }}
        styleThreshold={styleThreshold}
        onChangeStyleThreshold={(val) => {
          setStyleThreshold(val);
        }}
        onCommitStyleThreshold={async (val) => {
          const rounded = Math.round(val * 1000) / 1000;
          setStyleThreshold(rounded);
          localStorage.setItem("styleThreshold", String(rounded));
          try {
            const res = await fetch(`${API_BASE_URL}/settings`, {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ style_threshold: rounded }),
            });
            if (res.ok && /style:[^\s|]+/.test(query)) {
              reloadGrid();
            }
          } catch (error) {
            console.error("絵柄検索しきい値の設定保存エラー:", error);
          }
        }}
      />

      {/* コントロールバーの処理 */}
      {!selectedImage && (
        <ControlBar
          isSelectionMode={isSelectionMode}
          setIsSelectionMode={setIsSelectionMode}
          sortText={sortText}
          toggleSortOrder={toggleSortOrder}
          selectedIds={selectedIds}
          setSelectedIds={setSelectedIds}
          setStatusMessage={setStatusMessage}
          executeRandomSearch={executeRandomSearch}
          isTrashMode={isTrashFilter}
          hasFavoriteInSelection={hasFavoriteInSelection}
          onTrashSelected={handleTrashSelected}
          onRestoreSelected={handleRestoreSelected}
          serverMode={serverMode}
        />
      )}
    </div>
  );
}
