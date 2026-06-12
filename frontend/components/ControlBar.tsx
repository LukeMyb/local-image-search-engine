import { CheckSquare, SortDesc, Zap, Target } from "lucide-react";

// 親（page.tsx）から受け取るプロパティの型定義
interface ControlBarProps {
  isControlBarVisible: boolean;
  isSelectionMode: boolean;
  setIsSelectionMode: (mode: boolean) => void;
  sortText: string;
  toggleSortOrder: () => void;
  isHighAccuracy: boolean;
  setIsHighAccuracy: (accuracy: boolean) => void;
}

export default function ControlBar({
  isControlBarVisible,
  isSelectionMode,
  setIsSelectionMode,
  sortText,
  toggleSortOrder,
  isHighAccuracy,
  setIsHighAccuracy,
}: ControlBarProps) {
  return (
    <div
      className={`fixed bottom-6 left-1/2 -translate-x-1/2 z-30 transition-all duration-300 ease-in-out ${
        isControlBarVisible ? "translate-y-0 opacity-100" : "translate-y-20 opacity-0 pointer-events-none"
      }`}
    >
      <div className="bg-zinc-800/90 backdrop-blur-md border border-zinc-700 shadow-2xl rounded-full px-1.5 py-1.5 flex flex-row items-center gap-1 overflow-x-auto max-w-[95vw] scrollbar-hide">
        
        {/* 選択モードボタン */}
        <button
          onClick={() => setIsSelectionMode(!isSelectionMode)}
          className={`flex flex-row items-center gap-1.5 px-3 py-1.5 rounded-full transition-colors ${
            isSelectionMode 
              ? "bg-blue-600/20 text-blue-400 hover:bg-blue-600/30" 
              : "hover:bg-zinc-700 text-zinc-300"
          }`}
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
    </div>
  );
}