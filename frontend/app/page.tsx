"use client";

import { useState } from "react";

export default function Home() {
  // ステータスを管理する変数
  const [statusMessage, setStatusMessage] = useState("システム待機中...");

  return (
    // 画面全体を暗い背景にし、中央にテキストだけを配置する最小限のデザイン
    <div className="p-4 min-h-screen bg-zinc-900 text-green-400">
      <p className="text-lg font-medium">{statusMessage}</p>
    </div>
  );
}