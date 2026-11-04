import { useState, useCallback, useRef } from "react";
import { API_BASE_URL } from "../lib/config";

interface SearchResult {
  id: number;
  is_favorite?: number;
  is_deleted?: number;
}

// サジェスト候補のデータ構造を定義
interface Suggestion {
  id?: number;
  is_style?: boolean;
  display: string;
  query: string;
  count: number;
}

// グリッドの列数（1, 2, 3, 4, 5, 6, 8, 10, 12列）で割り切れるバッチ単位
const BATCH_SIZE = 120;

/**
 * 検索ロジックと検索結果の状態を管理するカスタムフック
 */
export function useImageSearch() {
  const [statusMessage, setStatusMessage] = useState("システム待機中...");
  const [results, setResults] = useState<SearchResult[]>([]);

  // 全IDリストと現在表示中のスライス範囲 [startIndex, endIndex) の管理
  const [allIds, setAllIds] = useState<number[]>([]);
  const [startIndex, setStartIndex] = useState(0);
  const [endIndex, setEndIndex] = useState(0);

  // スクロールによる親の再レンダリング時にもコールバック参照を固定するためのRef
  const allIdsRef = useRef<number[]>([]);
  const resultsRef = useRef<SearchResult[]>([]);
  const initialResultsRef = useRef<SearchResult[]>([]);
  const startIndexRef = useRef(0);
  const endIndexRef = useRef(0);
  const isLoadingMoreRef = useRef(false);
  const isLoadingPrevRef = useRef(false);

  // ソート変更時などに中央へフォーカスさせる対象のリクエスト情報
  const [focusRequest, setFocusRequest] = useState<{ id: number; key: number } | null>(null);
  // 一括削除・復元時に最後に選択した画像の位置へスクロール補正するためのリクエスト情報
  const [anchorScrollRequest, setAnchorScrollRequest] = useState<{
    id: number;
    viewportTop: number;
    key: number;
  } | null>(null);

  // 非同期競合防止用のリクエストID
  const searchSeqRef = useRef(0);

  // サジェスト関連の状態管理
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [isSuggestOpen, setIsSuggestOpen] = useState(false);

  // results の state と Ref を同時に更新するヘルパー
  const updateResults = useCallback(
    (updater: SearchResult[] | ((prev: SearchResult[]) => SearchResult[])) => {
      setResults((prev) => {
        const next = typeof updater === "function" ? updater(prev) : updater;
        resultsRef.current = next;
        return next;
      });
    },
    []
  );

  // スライス範囲と全IDリストをState・Ref双方へ同期するヘルパー
  const applyWindowState = useCallback((ids: number[], start: number, end: number) => {
    allIdsRef.current = ids;
    startIndexRef.current = start;
    endIndexRef.current = end;
    setAllIds(ids);
    setStartIndex(start);
    setEndIndex(end);
  }, []);

  // 検索実行ロジック
  const handleSearch = async (
    query: string,
    sortOrder: string = "score",
    e?: React.FormEvent,
    overrideQuery?: string,
    isFavoriteFilter: boolean = false,
    focusImageId?: number | null,
    isTrashFilter: boolean = false
  ) => {
    // フォーム送信によるページリロードを阻止する
    if (e) e.preventDefault();

    // 検索実行時にスマホのキーボードを閉じる
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }

    const currentSeq = ++searchSeqRef.current;
    isLoadingMoreRef.current = false;
    isLoadingPrevRef.current = false;

    // 直接渡されたキーワードがあればそれを使い、なければ検索窓(query)の値を使う
    const currentQuery = overrideQuery !== undefined ? overrideQuery : query;

    // クエリをlocalStorageに保存する
    localStorage.setItem("lastQuery", currentQuery);

    let endpoint = `/search?q=${encodeURIComponent(currentQuery)}&sort=${sortOrder}${isFavoriteFilter ? '&favorite_only=true' : ''}${isTrashFilter ? '&trash_only=true' : ''}`;
    
    // ランダムソート時はキャッシュを回避して毎回新しいシャッフルを得る
    if (sortOrder === "random") {
      endpoint += `&_t=${Date.now()}`;
    }

    if (isTrashFilter) {
      setStatusMessage(currentQuery ? `ゴミ箱内「${currentQuery}」を検索中...` : `ゴミ箱を表示中...`);
    } else {
      setStatusMessage(currentQuery ? `「${currentQuery}」を検索中...` : `全件表示中...`);
    }
    if (!focusImageId) {
      setFocusRequest(null);
    }
    setAnchorScrollRequest(null);
    updateResults([]); // 検索開始時に前の画像をクリア
    initialResultsRef.current = [];
    applyWindowState([], 0, 0);

    setIsSuggestOpen(false); // 検索実行時はサジェストを閉じる

    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`);
      if (!response.ok) {
        let errorDetail = `HTTPエラー: ${response.status}`;
        try {
          const errData = await response.json();
          if (errData.detail) errorDetail = errData.detail;
        } catch (e) {
          // JSONパースエラー時は無視
        }
        throw new Error(errorDetail);
      }

      const data = await response.json();
      if (currentSeq !== searchSeqRef.current) return;

      const ids: number[] = data.all_ids;
      const initialResults: SearchResult[] = data.results.slice(0, 100);
      initialResultsRef.current = initialResults;

      // フォーカス対象の画像IDが指定されており、かつ検索結果内に存在する場合
      const targetIndex = focusImageId != null ? ids.indexOf(focusImageId) : -1;

      if (targetIndex !== -1 && focusImageId != null) {
        if (targetIndex < 60) {
          // 先頭付近にある場合は最初の100件をそのまま使って中央へスクロールさせる
          applyWindowState(ids, 0, initialResults.length);
          updateResults(initialResults);
          setFocusRequest({ id: focusImageId, key: Date.now() });
        } else {
          // 後半にある場合は、列ズレを防ぐため120の倍数に揃えた開始位置から十分な前後幅を切り出して取得する
          const winStart = targetIndex < 240
            ? 0
            : Math.max(0, Math.floor((targetIndex - 180) / BATCH_SIZE) * BATCH_SIZE);
          const winEnd = Math.min(
            ids.length,
            Math.max(winStart + BATCH_SIZE * 3, Math.ceil((targetIndex + 120) / BATCH_SIZE) * BATCH_SIZE)
          );
          const windowIds = ids.slice(winStart, winEnd);

          const batchRes = await fetch(`${API_BASE_URL}/images/batch`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids: windowIds }),
          });

          if (currentSeq !== searchSeqRef.current) return;

          if (batchRes.ok) {
            const batchData = await batchRes.json();
            applyWindowState(ids, winStart, winEnd);
            updateResults(batchData.results);
            setFocusRequest({ id: focusImageId, key: Date.now() });
          } else {
            // フォールバック：初期100件を表示
            applyWindowState(ids, 0, initialResults.length);
            updateResults(initialResults);
          }
        }
      } else {
        // 通常の検索またはランダムソート時は先頭100件を表示し、一番上へ戻す
        setFocusRequest(null);
        applyWindowState(ids, 0, initialResults.length);
        updateResults(initialResults);
        if (typeof window !== "undefined") {
          window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
        }
      }

      const hitCount = data.total ?? ids.length;
      setStatusMessage(isTrashFilter ? `ゴミ箱: ${hitCount}件` : `${hitCount}件のヒット`);
    } catch (error: any) {
      if (currentSeq !== searchSeqRef.current) return;
      console.error(error);
      setStatusMessage(error.message || "通信エラーが発生しました。");
    }
  };

  // 下スクロール時に次のバッチを取得するロジック（参照を安定化してObserver再生成を防ぐ）
  const loadMore = useCallback(async () => {
    const currentEnd = endIndexRef.current;
    const ids = allIdsRef.current;
    if (isLoadingMoreRef.current || currentEnd >= ids.length) return;

    isLoadingMoreRef.current = true;
    const currentSeq = searchSeqRef.current;
    const nextEnd = Math.min(ids.length, currentEnd + BATCH_SIZE);
    const nextIds = ids.slice(currentEnd, nextEnd);

    try {
      const response = await fetch(`${API_BASE_URL}/images/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: nextIds }),
      });

      if (!response.ok) throw new Error("追加画像の取得に失敗しました");

      const data = await response.json();
      if (currentSeq !== searchSeqRef.current) return;

      endIndexRef.current = nextEnd;
      setEndIndex(nextEnd);
      updateResults((prev) => [...prev, ...data.results]);
    } catch (error) {
      console.error(error);
    } finally {
      if (currentSeq === searchSeqRef.current) {
        isLoadingMoreRef.current = false;
      }
    }
  }, [updateResults]);

  // 途中から表示を開始した場合に、上スクロールで前のバッチ（120件単位）を取得するロジック
  const loadPrev = useCallback(async () => {
    const currentStart = startIndexRef.current;
    const ids = allIdsRef.current;
    if (isLoadingPrevRef.current || currentStart <= 0) return;

    isLoadingPrevRef.current = true;
    const currentSeq = searchSeqRef.current;
    const nextStart = Math.max(0, currentStart - BATCH_SIZE);
    const prevIds = ids.slice(nextStart, currentStart);

    try {
      const response = await fetch(`${API_BASE_URL}/images/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: prevIds }),
      });

      if (!response.ok) throw new Error("前の画像の取得に失敗しました");

      const data = await response.json();
      if (currentSeq !== searchSeqRef.current) return;

      startIndexRef.current = nextStart;
      setStartIndex(nextStart);
      updateResults((prev) => [...data.results, ...prev]);
    } catch (error) {
      console.error(error);
    } finally {
      if (currentSeq === searchSeqRef.current) {
        isLoadingPrevRef.current = false;
      }
    }
  }, [updateResults]);

  // 途中から表示している状態（startIndex > 0）で「一番上に戻る」が押された際、先頭スライスへ即座に復帰する関数
  const resetToTop = useCallback(() => {
    const ids = allIdsRef.current;
    const topItems = initialResultsRef.current;
    if (startIndexRef.current > 0 && topItems.length > 0) {
      isLoadingPrevRef.current = false;
      isLoadingMoreRef.current = false;
      setFocusRequest(null);
      setAnchorScrollRequest(null);
      applyWindowState(ids, 0, topItems.length);
      updateResults(topItems);
    }
  }, [applyWindowState, updateResults]);

  // お気に入り切り替えロジック
  const toggleFavorite = async (image_id: number, e: React.MouseEvent, selectedImage: any, setSelectedImage: any) => {
    // 画像自体のクリック判定（モーダルを開く）が発動するのを防ぐ
    e.stopPropagation();

    try {
      const response = await fetch(`${API_BASE_URL}/favorite/${image_id}`, {
        method: "POST",
      });
      if (!response.ok) throw new Error("通信エラー");

      const data = await response.json();

      // 一覧側の状態を更新
      updateResults((prev) => 
        prev.map(item => item.id === image_id ? { ...item, is_favorite: data.is_favorite } : item)
      );
      initialResultsRef.current = initialResultsRef.current.map((item) =>
        item.id === image_id ? { ...item, is_favorite: data.is_favorite } : item
      );
      
      // モーダル側の状態も同期
      if (selectedImage && selectedImage.id === image_id) {
        setSelectedImage({ ...selectedImage, is_favorite: data.is_favorite });
      }
    } catch (error) {
      console.error(error);
    }
  };

  // 現在の表示リスト・スライス範囲から指定ID群を即座に除外し、最後に選択した画像の位置へスクロールを補正する共通ヘルパー
  const removeIdsFromView = useCallback((targetIds: number[], lastSelectedId?: number) => {
    const targetSet = new Set<number>(targetIds);
    const currentResults = resultsRef.current;
    const referenceId = lastSelectedId ?? targetIds[targetIds.length - 1];

    // 最後に選択していた画像の位置を基準に、削除後にその場所へ詰まる残存画像（anchorId）と画面上のY座標を特定する
    if (referenceId !== undefined && typeof window !== "undefined") {
      const lastIdx = currentResults.findIndex((item) => item.id === referenceId);
      if (lastIdx !== -1) {
        let anchorId: number | null = null;
        // 最後に選択した画像の直後から、削除対象ではない最初の画像を探す（上に詰まってその位置に来る画像）
        for (let i = lastIdx + 1; i < currentResults.length; i++) {
          if (!targetSet.has(currentResults[i].id)) {
            anchorId = currentResults[i].id;
            break;
          }
        }
        // 後ろに残存画像がない場合（末尾まで全て選択した場合など）は、直前の残存画像を探す
        if (anchorId === null) {
          for (let i = lastIdx - 1; i >= 0; i--) {
            if (!targetSet.has(currentResults[i].id)) {
              anchorId = currentResults[i].id;
              break;
            }
          }
        }

        if (anchorId !== null) {
          const lastEl = document.getElementById(`grid-image-${referenceId}`);
          let viewportTop = window.innerHeight / 3;
          if (lastEl) {
            const rect = lastEl.getBoundingClientRect();
            const isVisible = rect.bottom > 0 && rect.top < window.innerHeight;
            // 画面内に見えていた場合はそのY座標を維持し、画面外だった場合は画面中央付近へ移動させる
            viewportTop = isVisible ? rect.top : Math.max(80, (window.innerHeight - rect.height) / 2);
          }
          setAnchorScrollRequest({
            id: anchorId,
            viewportTop,
            key: Date.now(),
          });
        }
      }
    }

    const oldIds = allIdsRef.current;
    const oldStart = startIndexRef.current;
    const oldEnd = endIndexRef.current;

    let removedBeforeStart = 0;
    let removedInWindow = 0;
    for (let i = 0; i < oldIds.length; i++) {
      if (targetSet.has(oldIds[i])) {
        if (i < oldStart) {
          removedBeforeStart++;
        } else if (i < oldEnd) {
          removedInWindow++;
        }
      }
    }

    const newAllIds = oldIds.filter((id) => !targetSet.has(id));
    const newStart = Math.max(0, oldStart - removedBeforeStart);
    const newEnd = Math.max(newStart, oldEnd - removedBeforeStart - removedInWindow);

    applyWindowState(newAllIds, newStart, newEnd);
    initialResultsRef.current = initialResultsRef.current.filter((item) => !targetSet.has(item.id));
    updateResults((prev) => prev.filter((item) => !targetSet.has(item.id)));
  }, [applyWindowState, updateResults]);

  // 指定した画像IDリストを論理削除（data/trash/ へ移動）し、現在の表示リストから即座に除外する関数
  const trashImages = useCallback(async (imageIds: number[]): Promise<number[]> => {
    if (!imageIds || imageIds.length === 0) return [];
    const lastSelectedId = imageIds[imageIds.length - 1];

    try {
      const response = await fetch(`${API_BASE_URL}/images/trash`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: imageIds }),
      });

      if (!response.ok) {
        throw new Error("画像の削除に失敗しました");
      }

      const data = await response.json();
      const trashedIds: number[] = data.trashed_ids || [];
      if (trashedIds.length === 0) return [];

      removeIdsFromView(trashedIds, lastSelectedId);
      setStatusMessage(`${trashedIds.length}枚をゴミ箱に移動しました`);

      return trashedIds;
    } catch (error: any) {
      console.error("論理削除エラー:", error);
      setStatusMessage(error.message || "画像の削除に失敗しました");
      return [];
    }
  }, [removeIdsFromView]);

  // 指定した画像IDリストをゴミ箱から復元（data/images/ へ移動）し、現在のゴミ箱表示リストから即座に除外する関数
  const restoreImages = useCallback(async (imageIds: number[]): Promise<number[]> => {
    if (!imageIds || imageIds.length === 0) return [];
    const lastSelectedId = imageIds[imageIds.length - 1];

    try {
      const response = await fetch(`${API_BASE_URL}/images/restore`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: imageIds }),
      });

      if (!response.ok) {
        throw new Error("画像の復元に失敗しました");
      }

      const data = await response.json();
      const restoredIds: number[] = data.restored_ids || [];
      if (restoredIds.length === 0) return [];

      removeIdsFromView(restoredIds, lastSelectedId);
      setStatusMessage(`${restoredIds.length}枚を復元しました`);

      return restoredIds;
    } catch (error: any) {
      console.error("復元エラー:", error);
      setStatusMessage(error.message || "画像の復元に失敗しました");
      return [];
    }
  }, [removeIdsFromView]);

  // バックエンドからサジェスト候補を取得する関数
  const fetchSuggestions = useCallback(async (inputQuery: string) => {
    if (!inputQuery.trim()) {
      setSuggestions([]);
      return;
    }

    try {
      const response = await fetch(`${API_BASE_URL}/suggest?q=${encodeURIComponent(inputQuery)}`);
      if (!response.ok) throw new Error("サジェストの取得に失敗しました");

      const data = await response.json();
      setSuggestions(data.suggestions);
    } catch (error) {
      console.error(error);
    }
  }, []);

  // 絵柄タグを削除する関数
  const deleteStyleTag = async (styleId: number) => {
    try {
      const response = await fetch(`${API_BASE_URL}/style/${styleId}`, {
        method: "DELETE",
      });
      if (!response.ok) throw new Error("絵柄タグの削除に失敗しました");

      // 削除が成功したら、現在メモリにあるサジェスト一覧からそのタグを即座に除外する
      setSuggestions((prev) => prev.filter((s) => !(s.is_style && s.id === styleId)));
      
      // もしリストが空になったら枠を閉じる
      setSuggestions((prev) => {
        if (prev.length === 0) setIsSuggestOpen(false);
        return prev;
      });
    } catch (error) {
      console.error(error);
      alert("絵柄タグの削除に失敗しました");
    }
  };

  return {
    results,
    setResults,
    statusMessage,
    setStatusMessage,
    handleSearch,
    toggleFavorite,
    trashImages,
    restoreImages,
    loadMore,
    loadPrev,
    resetToTop,
    hasMore: endIndex < allIds.length,
    hasPrev: startIndex > 0,
    focusRequest,
    setFocusRequest,
    anchorScrollRequest,
    setAnchorScrollRequest,
    suggestions,
    isSuggestOpen,
    setIsSuggestOpen,
    fetchSuggestions,
    deleteStyleTag,
  };
}
