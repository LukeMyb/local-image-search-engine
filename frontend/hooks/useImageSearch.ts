import { useState } from "react";

interface SearchResult {
  id: number;
  is_favorite?: number;
}

/**
 * 検索ロジックと検索結果の状態を管理するカスタムフック
 */
export function useImageSearch() {
  const [statusMessage, setStatusMessage] = useState("システム待機中...");
  const [results, setResults] = useState<SearchResult[]>([]);

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

    try {
      const response = await fetch(`http://192.168.11.3:8000${endpoint}`);
      if (!response.ok) throw new Error(`HTTPエラー: ${response.status}`);

      const data = await response.json();
      // 先頭50件のみ表示
      setResults(data.results.slice(0, 50));
      setStatusMessage(`${data.results.length}件の検索が完了しました（先頭50件を表示中）`);
    } catch (error) {
      console.error(error);
      setStatusMessage("通信エラーが発生しました。");
    }
  };

  // お気に入り切り替えロジック
  const toggleFavorite = async (image_id: number, e: React.MouseEvent, selectedImage: any, setSelectedImage: any) => {
    // 画像自体のクリック判定（モーダルを開く）が発動するのを防ぐ
    e.stopPropagation();

    try {
      const response = await fetch(`http://192.168.11.3:8000/favorite/${image_id}`, {
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

  return {
    results,
    setResults,
    statusMessage,
    setStatusMessage,
    handleSearch,
    toggleFavorite,
  };
}