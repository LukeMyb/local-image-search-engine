"use client";

import { useState, useEffect } from "react";
import { Search, X } from "lucide-react";

// 検索結果のデータ構造を定義（今回は最低限必要な id だけ）
interface SearchResult {
  id: number;
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

  // モーダルの開閉に合わせて背景のスクロールを制御する
  useEffect(() => {
    if (selectedImage) {
      // モーダルが開いている時: ブラウザ全体のスクロールを隠す（無効化）
      document.body.style.overflow = "hidden";
    } else {
      // モーダルが閉じた時: スクロール設定を元に戻す
      document.body.style.overflow = "";
    }

    // 安全装置: この画面から別のページへ移動した時などに、スクロール不可のままになるのを防ぐ
    return () => {
      document.body.style.overflow = "";
    };
  }, [selectedImage]); // <- selectedImage が変化するたびにこの処理を走らせる

  const handleSearch = async (e?: React.FormEvent) => {
    // フォーム送信によるページリロードを確実に阻止する
    if (e) e.preventDefault();

    // 空欄の場合は何もしない
    if (!query) return;

    setStatusMessage(`「${query}」を検索中...`);
    setResults([]); // 検索開始時に前の画像をクリア

    try {
      // Python側のAPIを叩く
      const response = await fetch(`http://192.168.11.3:8000/search?q=${query}`);

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

  return (
    // レイアウト
    <div className="p-2 min-h-screen bg-zinc-900 text-green-400 flex flex-col gap-4">
      <p className="text-lg font-medium">{statusMessage}</p>

      {/* 検索窓とボタンを横に並べるための箱 (flex flex-row を指定) */}
      <form 
        onSubmit={handleSearch} 
        className="flex flex-row gap-2"
      >

        {/* 検索窓（テキストボックス） */}
        <input
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="タグやキーワードを入力..."
          className="p-3 bg-[#27272a] rounded-md text-white placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-600 max-w-md"
        />

        {/* 検索ボタン */}
        <button
          type="submit"
          className="p-3 bg-[#27272a] hover:bg-zinc-700 text-zinc-400 hover:text-white rounded-md transition-colors flex items-center justify-center"
        >
          {/* 虫眼鏡アイコンの本体 */}
          <Search size={16} />
        </button>
      </form>

      {/* 取得したIDを使って画像を並べる処理 */}
      <div className="grid grid-cols-3 gap-2 md:grid-cols-6 md:gap-4 mt-4">
        {results.map((item) => (
          <img
            key={item.id}
            // Python側の画像のエンドポイントを呼び出し
            src={`http://192.168.11.3:8000/thumbnail/${item.id}`}
            alt={`Image ${item.id}`}
            // クリックされたら、この画像の情報を selectedImage にセットする
            onClick={() => setSelectedImage(item)}
            // カーソルを指マーク(cursor-pointer)にし、クリックできることを強調
            className="w-full aspect-square object-cover rounded-md cursor-pointer hover:opacity-80 transition-opacity"
          />
        ))}
      </div>

      {/* モーダルの描画処理 (selectedImage に中身がある時だけ表示される) */}
      {selectedImage && (
        <div 
          // 画面全体を覆う半透明の黒い背景
          className="fixed inset-0 bg-black flex items-center justify-center z-50"
        >
          {/* 画像を中央に配置するコンテナ */}
          <div className="relative w-full h-full flex flex-col items-center">
            <img 
              // 本画像(/image/)を呼び出す
              src={`http://192.168.11.3:8000/image/${selectedImage.id}`} 
              alt={`Selected ${selectedImage.id}`}
              className="w-full h-full object-contain"
            />
            
            <button 
              onClick={() => setSelectedImage(null)}
              className="absolute top-4 right-4 p-2 bg-black/50 text-white hover:bg-black/80 rounded-full transition-colors"
            >
              <X size={24} />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}