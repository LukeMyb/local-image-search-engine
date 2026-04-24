"use client";

import { useState } from "react";

export default function Home() {
  // ステータスを管理する変数
  const [statusMessage, setStatusMessage] = useState("システム待機中...");

  return (
    // 画面全体を暗い背景にし、中央にテキストだけを配置する最小限のデザイン
    <div className="flex items-center justify-center min-h-screen bg-gray-900 text-white">
      <p>{statusMessage}</p>
    </div>
  );
}