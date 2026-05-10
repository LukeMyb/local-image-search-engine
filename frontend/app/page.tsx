"use client";

import { useState } from "react";

export default function Home() {
  // ステータスを管理する変数
  const [statusMessage, setStatusMessage] = useState("システム待機中...");
  // 検索キーワードを管理する変数
  const [query, setQuery] = useState("");

  return (
    // レイアウト
    <div className="p-4 min-h-screen bg-zinc-900 text-green-400 flex flex-col gap-4">
      <p className="text-lg font-medium">{statusMessage}</p>

      {/* 検索窓（テキストボックス） */}
      <input
        type="text"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="タグやキーワードを入力..."
        className="p-3 bg-[#27272a] rounded-md text-white placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-600 max-w-md"
      />
    </div>
  );
}