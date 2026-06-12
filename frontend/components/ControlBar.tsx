import { useState } from "react";
import { CheckSquare, SortDesc, Zap, Target, X, MoreHorizontal, Tag } from "lucide-react";

// 親（page.tsx）から受け取るプロパティの型定義
interface ControlBarProps {
  isControlBarVisible: boolean;
  isSelectionMode: boolean;
  setIsSelectionMode: (mode: boolean) => void;
  sortText: string;
  toggleSortOrder: () => void;
  isHighAccuracy: boolean;
  setIsHighAccuracy: (accuracy: boolean) => void;
  selectedCount?: number;
}

export default function ControlBar({
  isControlBarVisible,
  isSelectionMode,
  setIsSelectionMode,
  sortText,
  toggleSortOrder,
  isHighAccuracy,
  setIsHighAccuracy,
  selectedCount = 0,
}: ControlBarProps) {
  // アクションメニューの開閉状態を管理するState
  const [isActionMenuOpen, setIsActionMenuOpen] = useState(false);

  return (
    <div
      className={`fixed bottom-6 left-1/2 -translate-x-1/2 z-30 transition-all duration-300 ease-in-out ${
        isControlBarVisible || isSelectionMode ? "translate-y-0 opacity-100" : "translate-y-20 opacity-0 pointer-events-none"
      }`}
    >
      {/* 選択モードのON/OFFで中身を切り替える */}
      {!isSelectionMode ? (
        <div className="bg-zinc-800/90 backdrop-blur-md border border-zinc-700 shadow-2xl rounded-full px-1.5 py-1.5 flex flex-row items-center gap-1 overflow-x-auto max-w-[95vw] scrollbar-hide">
          
          {/* 選択モードボタン */}
          <button
            onClick={() => setIsSelectionMode(true)}
            className="flex flex-row items-center gap-1.5 px-3 py-1.5 rounded-full hover:bg-zinc-700 transition-colors text-zinc-300"
          >
            <CheckSquare size={16} />
            <span className="text-sm font-medium whitespace-nowrap">選択</span>
          </button>
          
          <div className="w-px h-5 bg-zinc-700 mx-0.5 shrink-0"></div>

          {/* ソート順変更ボタン */}
          <button
            onClick={toggleSortOrder}
            className="flex flex-row items-center gap-1.5 px-3 py-1.5 rounded-full hover:bg-zinc-700 transition-colors text-zinc-300"
          >
            <SortDesc size={16} />
            <span className="text-sm font-medium whitespace-nowrap">{sortText}</span>
          </button>

          <div className="w-px h-5 bg-zinc-700 mx-0.5 shrink-0"></div>

          {/* 検索精度切り替えボタン */}
          <button
            onClick={() => setIsHighAccuracy(!isHighAccuracy)}
            className="flex flex-row items-center gap-1.5 px-3 py-1.5 rounded-full hover:bg-zinc-700 transition-colors text-zinc-300"
          >
            {isHighAccuracy ? <Target size={16} /> : <Zap size={16} className="text-yellow-400" />}
            <span className="text-sm font-medium whitespace-nowrap">
              {isHighAccuracy ? "高精度" : "高速"}
            </span>
          </button>
          
        </div>

        ) : (
        // アクションバー
        <div className="relative flex justify-center">
          
          {/* アクションメニューの吹き出し (絶対配置で上に展開) */}
          {isActionMenuOpen && selectedCount > 0 && (
            <div className="absolute bottom-full mb-3 right-0 bg-zinc-800/95 backdrop-blur-md border border-zinc-700 shadow-2xl rounded-2xl py-2 min-w-45 overflow-hidden origin-bottom-right animate-in fade-in zoom-in-95 duration-200">
              <button
                onClick={() => {
                  alert("絵柄タグ作成機能は準備中です"); // モック用のアラート
                  setIsActionMenuOpen(false);
                  setIsSelectionMode(false);
                }}
                className="w-full flex flex-row items-center gap-3 px-4 py-3 hover:bg-zinc-700 transition-colors text-zinc-200 text-left"
              >
                <Tag size={18} className="text-blue-400" />
                <span className="text-sm font-medium">絵柄タグを作成</span>
              </button>
              {/* 将来的に他の機能を追加する場合はここにボタンを並べます */}
            </div>
          )}

          {/* アクションバー本体 */}
          {/* 青枠を付けて「選択中」であることを視覚的にアピール */}
          <div className="bg-zinc-800/90 backdrop-blur-md border border-blue-500/50 shadow-blue-900/20 shadow-2xl rounded-full px-1.5 py-1.5 flex flex-row items-center justify-between gap-4 overflow-x-auto min-w-70 max-w-[95vw]">
            
            {/* キャンセルボタン (左) */}
            <button
              onClick={() => {
                setIsSelectionMode(false);
                setIsActionMenuOpen(false);
              }}
              className="p-2 rounded-full hover:bg-zinc-700 transition-colors text-zinc-300 shrink-0"
              title="キャンセル"
            >
              <X size={18} />
            </button>
            
            {/* 選択枚数 (中央) */}
            <div className="flex-1 text-center truncate">
              <span className="text-sm font-bold text-white">
                {selectedCount > 0 ? `${selectedCount}枚選択中` : "画像を選択してください"}
              </span>
            </div>

            {/* アクションメニュー展開ボタン (右) */}
            <button
              onClick={() => setIsActionMenuOpen(!isActionMenuOpen)}
              disabled={selectedCount === 0} // 1枚も選ばれていない時は押せない
              className={`p-2 rounded-full transition-colors shrink-0 ${
                selectedCount > 0 
                  ? "bg-blue-600/20 text-blue-400 hover:bg-blue-600/40" 
                  : "text-zinc-600 cursor-not-allowed"
              }`}
              title="アクション"
            >
              <MoreHorizontal size={18} />
            </button>
            
          </div>
        </div>
      )}
    </div>
  );
}