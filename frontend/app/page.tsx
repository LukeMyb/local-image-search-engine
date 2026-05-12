"use client";

import { useState } from "react";
import { Search } from "lucide-react";

export default function Home() {
  // ステータスを管理する変数
  const [statusMessage, setStatusMessage] = useState("システム待機中...");
  // 検索キーワードを管理する変数
  const [query, setQuery] = useState("");
  // 検索結果（APIから返ってきた生データ）を保存する変数
  const [results, setResults] = useState<string>("");

  const handleSearch = async () => {
    // 空欄の場合は何もしない
    if (!query) return;

    setStatusMessage(`「${query}」を検索中...`);
    setResults(""); // 検索開始時に前の結果をクリア

    try {
      // Python側のAPIを叩く
      const response = await fetch(`http://localhost:8000/search?q=${query}`);

      if (!response.ok) {
        throw new Error(`HTTPエラー: ${response.status}`);
      }

      const data = await response.json();

      // ブラウザのフリーズを防ぐため、最初の2件だけを抽出する安全装置
      const safeData = {
        query: data.query,
        total_hits: data.results.length,
        results: data.results.slice(0, 2)
      };

      // 安全なデータの方を文字にして変数に格納
      setResults(JSON.stringify(safeData, null, 2));
      setStatusMessage(`${data.results.length}件の検索が完了しました！`);

    } catch (error) {
      console.error(error);
      setStatusMessage("通信エラーが発生しました。");
    }
  };

  return (
    // レイアウト
    <div className="p-4 min-h-screen bg-zinc-900 text-green-400 flex flex-col gap-4">
      <p className="text-lg font-medium">{statusMessage}</p>

      {/* 検索窓とボタンを横に並べるための箱 (flex flex-row を指定) */}
      <div className="flex flex-row gap-2">

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
          onClick={handleSearch}
          className="p-3 bg-[#27272a] hover:bg-zinc-700 text-zinc-400 hover:text-white rounded-md transition-colors flex items-center justify-center"
        >
          {/* 虫眼鏡アイコンの本体 */}
          <Search size={16} />
        </button>
      </div>

      {/* 検索結果（生データ）を表示するエリア */}
      {results && (
        <pre className="p-4 bg-black text-white rounded-md overflow-x-auto text-sm mt-4 max-w-2xl">
          {results}
        </pre>
      )}
    </div>
  );
}