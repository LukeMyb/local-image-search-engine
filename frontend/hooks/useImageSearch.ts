import { useState, useCallback } from "react";
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

  // 全IDリストとローディング状態の管理
  const [allIds, setAllIds] = useState<number[]>([]);
  const [isLoadingMore, setIsLoadingMore] = useState(false);

  // サジェスト関連の状態管理
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [isSuggestOpen, setIsSuggestOpen] = useState(false);

  // 検索実行ロジック
  const handleSearch = async (query: string, e?: React.FormEvent, overrideQuery?: string) => {
    // フォーム送信によるページリロードを阻止する
    if (e) e.preventDefault();

    // 検索実行時にスマホのキーボードを閉じる
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }

    // 直接渡されたキーワードがあればそれを使い、なければ検索窓(query)の値を使う
    const currentQuery = overrideQuery !== undefined ? overrideQuery : query;
    const isQueryEmpty = !currentQuery.trim();
    const endpoint = isQueryEmpty ? `/favorites` : `/search?q=${encodeURIComponent(currentQuery)}`;

    setStatusMessage(currentQuery ? `「${currentQuery}」を検索中...` : `お気に入り一覧を取得中...`);
    setResults([]); // 検索開始時に前の画像をクリア
    setAllIds([]); // 前の検索結果のIDリストも同時にクリア

    setIsSuggestOpen(false); // 検索実行時はサジェストを閉じる

    try {
      const response = await fetch(`${API_BASE_URL}${endpoint}`);
      if (!response.ok) throw new Error(`HTTPエラー: ${response.status}`);

      const data = await response.json();

      // お気に入り(/favorites)など従来形式が返ってきた時もエラーにならないようフォールバックを設定
      const ids = data.all_ids || data.results.map((r: any) => r.id);
      const initialResults = data.results.slice(0, 100);

      // IDリストと初期画像をセット
      setAllIds(ids);
      setResults(initialResults);
      setStatusMessage(`${data.total || ids.length}件のヒット`);
    } catch (error) {
      console.error(error);
      setStatusMessage("通信エラーが発生しました。");
    }
  };

  // スクロール時に次の100件を取得するロジック
  const loadMore = async () => {
    // 読み込み中、またはすべて読み込み済みの場合は何もしない
    if (isLoadingMore || results.length >= allIds.length) return;

    setIsLoadingMore(true);
    // 次に取得すべき100件のIDを切り出す
    const nextIds = allIds.slice(results.length, results.length + 100);

    try {
      const response = await fetch(`${API_BASE_URL}/images/batch`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ids: nextIds }),
      });

      if (!response.ok) throw new Error("追加画像の取得に失敗しました");

      const data = await response.json();
      // 既存の配列の後ろに、新しく取得した画像を結合する
      setResults((prev) => [...prev, ...data.results]);
    } catch (error) {
      console.error(error);
    } finally {
      setIsLoadingMore(false);
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
    hasMore: results.length < allIds.length,
    suggestions,
    isSuggestOpen,
    setIsSuggestOpen,
    fetchSuggestions,
    deleteStyleTag,
  };
}