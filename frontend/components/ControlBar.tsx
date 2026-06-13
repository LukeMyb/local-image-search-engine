import { useState } from "react";
import { CheckSquare, SortDesc, Zap, Target, X, MoreHorizontal, Tag } from "lucide-react";
import { API_BASE_URL } from "../lib/config";

// 親（page.tsx）から受け取るプロパティの型定義
interface ControlBarProps {
  isControlBarVisible: boolean;
  isSelectionMode: boolean;
  setIsSelectionMode: (mode: boolean) => void;
  sortText: string;
  toggleSortOrder: () => void;
  isHighAccuracy: boolean;
  setIsHighAccuracy: (accuracy: boolean) => void;
  selectedIds: number[];
  setSelectedIds: (ids: number[]) => void;
}

export default function ControlBar({
  isControlBarVisible,
  isSelectionMode,
  setIsSelectionMode,
  sortText,
  toggleSortOrder,
  isHighAccuracy,
  setIsHighAccuracy,
  selectedIds,
  setSelectedIds,
}: ControlBarProps) {
  // アクションメニューの開閉状態を管理するState
  const [isActionMenuOpen, setIsActionMenuOpen] = useState(false);

  // ダイアログの開閉と入力内容を管理するState
  const [isStyleDialogOpen, setIsStyleDialogOpen] = useState(false);
  const [styleNameInput, setStyleNameInput] = useState("");

  // 配列の長さから選択数を計算
  const selectedCount = selectedIds.length;

  // APIへ送信して絵柄タグを作成する関数
  const executeCreateStyleTag = async () => {
    if (selectedIds.length === 0 || !styleNameInput.trim()) return;

    const finalTagName = `style:${styleNameInput.trim()}`;
    setIsStyleDialogOpen(false); // ダイアログを閉じる

    try {
      const response = await fetch(`${API_BASE_URL}/style`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ 
          name: finalTagName, 
          image_ids: selectedIds 
        }),
      });

      const data = await response.json();

      if (!response.ok) {
        throw new Error(data.detail || "作成に失敗しました");
      }
      
      // 成功したら選択状態をリセットする
      setSelectedIds([]);
      setIsSelectionMode(false);
      
      alert(data.message); 
      
    } catch (error: any) {
      console.error("タグ作成エラー:", error);
      alert(error.message || "タグの作成に失敗しました");
    }
  };

  return (
    <>
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
                    setIsActionMenuOpen(false);
                    setStyleNameInput(""); 
                    setIsStyleDialogOpen(true);
                  }}
                  className="w-full flex flex-row items-center gap-3 px-4 py-3 hover:bg-zinc-700 transition-colors text-zinc-200 text-left"
                >
                  <Tag size={18} className="text-blue-400" />
                  <span className="text-sm font-medium">絵柄タグを作成</span>
                </button>
                {/* 将来的に他の機能を追加する場合はここにボタンを並べる */}
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

      {/* 幽閉された絵柄タグ作成ダイアログ */}
      {isStyleDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/60 backdrop-blur-sm animate-in fade-in duration-200">
          <div className="bg-zinc-800 border border-zinc-700 rounded-2xl p-6 w-full max-w-sm shadow-2xl flex flex-col gap-4">
            <h3 className="text-lg font-bold text-white">絵柄タグを作成</h3>
            <p className="text-sm text-zinc-400">
              選択した {selectedCount} 枚の画像から絵柄を解析し、タグとして保存します。
            </p>
            
            <div className="flex flex-col gap-1">
              <label className="text-xs text-zinc-500 font-medium">絵柄の名前（例: my_art）</label>
              <div className="flex items-center bg-zinc-900 border border-zinc-700 rounded-lg overflow-hidden focus-within:border-blue-500 transition-colors">
                <span className="pl-3 pr-1 text-zinc-500 text-sm select-none">style:</span>
                <input
                  type="text"
                  value={styleNameInput}
                  onChange={(e) => setStyleNameInput(e.target.value)}
                  placeholder="タグ名を入力"
                  className="flex-1 bg-transparent text-white p-2 text-base outline-none placeholder:text-zinc-600"
                  onKeyDown={(e) => {
                    if (e.key === "Enter" && styleNameInput.trim()) {
                      executeCreateStyleTag();
                    }
                  }}
                />
              </div>
            </div>

            <div className="flex justify-end gap-3 mt-2">
              <button
                onClick={() => setIsStyleDialogOpen(false)}
                className="px-4 py-2 rounded-lg text-sm font-medium text-zinc-300 hover:bg-zinc-700 transition-colors"
              >
                キャンセル
              </button>
              <button
                onClick={executeCreateStyleTag}
                disabled={!styleNameInput.trim()}
                className="px-4 py-2 rounded-lg text-sm font-medium bg-blue-600 text-white hover:bg-blue-500 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
              >
                作成する
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}