import { useState, useCallback, useRef } from "react";
import { API_BASE_URL } from "../lib/config";

interface SearchResult {
  id: number;
  is_favorite?: number;
}

// サジェスト候補のデータ構造を定義
interface Suggestion {
  id?: number;
  is_style?: boolean;
  display: string;
  query: string;
  count: number;
}

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
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [isLoadingPrev, setIsLoadingPrev] = useState(false);

  // ソート変更時などに中央へフォーカスさせる対象のリクエスト情報
  const [focusRequest, setFocusRequest] = useState<{ id: number; key: number } | null>(null);

  // 非同期競合防止用のリクエストID
  const searchSeqRef = useRef(0);

  // サジェスト関連の状態管理
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [isSuggestOpen, setIsSuggestOpen] = useState(false);

  // 検索実行ロジック
  const handleSearch = async (
    query: string,
    sortOrder: string = "score",
    e?: React.FormEvent,
    overrideQuery?: string,
    isFavoriteFilter: boolean = false,
    focusImageId?: number | null
  ) => {
    // フォーム送信によるページリロードを阻止する
    if (e) e.preventDefault();

    // 検索実行時にスマホのキーボードを閉じる
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }

    const currentSeq = ++searchSeqRef.current;

    // 直接渡されたキーワードがあればそれを使い、なければ検索窓(query)の値を使う
    const currentQuery = overrideQuery !== undefined ? overrideQuery : query;

    // クエリをlocalStorageに保存する
    localStorage.setItem("lastQuery", currentQuery);

    let endpoint = `/search?q=${encodeURIComponent(currentQuery)}&sort=${sortOrder}${isFavoriteFilter ? '&favorite_only=true' : ''}`;
    
    // ランダムソート時はキャッシュを回避して毎回新しいシャッフルを得る
    if (sortOrder === "random") {
      endpoint += `&_t=${Date.now()}`;
    }

    setStatusMessage(currentQuery ? `「${currentQuery}」を検索中...` : `全件表示中...`);
    if (!focusImageId) {
      setFocusRequest(null);
    }
    setResults([]); // 検索開始時に前の画像をクリア
    setAllIds([]); // 前の検索結果のIDリストも同時にクリア
    setStartIndex(0);
    setEndIndex(0);

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

      // お気に入り(/favorites)など従来形式が返ってきた時もエラーにならないようフォールバックを設定
      const ids: number[] = data.all_ids || data.results.map((r: any) => r.id);
      const initialResults: SearchResult[] = data.results.slice(0, 100);

      // フォーカス対象の画像IDが指定されており、かつ検索結果内に存在する場合
      const targetIndex = focusImageId != null ? ids.indexOf(focusImageId) : -1;

      if (targetIndex !== -1 && focusImageId != null) {
        if (targetIndex < 60) {
          // 先頭付近にある場合は最初の100件をそのまま使って中央へスクロールさせる
          setAllIds(ids);
          setStartIndex(0);
          setEndIndex(initialResults.length);
          setResults(initialResults);
          setFocusRequest({ id: focusImageId, key: Date.now() });
        } else {
          // 後半にある場合は、対象画像の前後50件（計100件）のウィンドウを取得して即座に表示する
          const winStart = Math.max(0, Math.min(targetIndex - 50, ids.length - 100));
          const winEnd = Math.min(ids.length, winStart + 100);
          const windowIds = ids.slice(winStart, winEnd);

          const batchRes = await fetch(`${API_BASE_URL}/images/batch`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids: windowIds }),
          });

          if (currentSeq !== searchSeqRef.current) return;

          if (batchRes.ok) {
            const batchData = await batchRes.json();
            setAllIds(ids);
            setStartIndex(winStart);
            setEndIndex(winEnd);
            setResults(batchData.results);
            setFocusRequest({ id: focusImageId, key: Date.now() });
          } else {
            // フォールバック：初期100件を表示
            setAllIds(ids);
            setStartIndex(0);
            setEndIndex(initialResults.length);
            setResults(initialResults);
          }
        }
      } else {
        // 通常の検索またはランダムソート時は先頭100件を表示し、一番上へ戻す
        setFocusRequest(null);
        setAllIds(ids);
        setStartIndex(0);
        setEndIndex(initialResults.length);
        setResults(initialResults);
        if (typeof window !== "undefined") {
          window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
        }
      }

      setStatusMessage(`${data.total || ids.length}件のヒット`);
    } catch (error: any) {
      if (currentSeq !== searchSeqRef.current) return;
      console.error(error);
      setStatusMessage(error.message || "通信エラーが発生しました。");
    }
  };

  // 下スクロール時に次の100件を取得するロジック
  const loadMore = async () => {
    // 読み込み中、または末尾まで読み込み済みの場合は何もしない
    if (isLoadingMore || endIndex >= allIds.length) return;

    setIsLoadingMore(true);
    const nextEnd = Math.min(allIds.length, endIndex + 100);
    const nextIds = allIds.slice(endIndex, nextEnd);

    try {
      const response = await fetch(`${API_BASE_URL}/images/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: nextIds }),
      });

      if (!response.ok) throw new Error("追加画像の取得に失敗しました");

      const data = await response.json();
      setResults((prev) => [...prev, ...data.results]);
      setEndIndex(nextEnd);
    } catch (error) {
      console.error(error);
    } finally {
      setIsLoadingMore(false);
    }
  };

  // 途中から表示を開始した場合に、上スクロールで前の100件を取得するロジック
  const loadPrev = async () => {
    if (isLoadingPrev || startIndex <= 0) return;

    setIsLoadingPrev(true);
    const nextStart = Math.max(0, startIndex - 100);
    const prevIds = allIds.slice(nextStart, startIndex);

    try {
      const response = await fetch(`${API_BASE_URL}/images/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: prevIds }),
      });

      if (!response.ok) throw new Error("前の画像の取得に失敗しました");

      const data = await response.json();
      setResults((prev) => [...data.results, ...prev]);
      setStartIndex(nextStart);
    } catch (error) {
      console.error(error);
    } finally {
      setIsLoadingPrev(false);
    }
  };

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
      setResults((prev) => 
        prev.map(item => item.id === image_id ? { ...item, is_favorite: data.is_favorite } : item)
      );
      
      // モーダル側の状態も同期
      if (selectedImage && selectedImage.id === image_id) {
        setSelectedImage({ ...selectedImage, is_favorite: data.is_favorite });
      }
    } catch (error) {
      console.error(error);
    }
  };

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
    loadMore,
    loadPrev,
    hasMore: endIndex < allIds.length,
    hasPrev: startIndex > 0,
    focusRequest,
    setFocusRequest,
    suggestions,
    isSuggestOpen,
    setIsSuggestOpen,
    fetchSuggestions,
    deleteStyleTag,
  };
}
