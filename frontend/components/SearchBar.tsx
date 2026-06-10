import { useState, useEffect, useRef } from "react";
import { Search, X, Menu, BookmarkPlus, BookmarkCheck, Trash2 } from "lucide-react";

// サジェストの型定義
interface Suggestion {
  id?: number;
  is_style?: boolean;
  display: string;
  query: string;
  count: number;
}

interface SearchBarProps {
  query: string;
  setQuery: (q: string) => void;
  onSearch: (e?: React.FormEvent) => void;
  setIsDrawerOpen: (open: boolean) => void;
  openBookmarkDialog: () => void;
  savedQueries: string[];
  // サジェスト用のProps
  suggestions: Suggestion[];
  isSuggestOpen: boolean;
  setIsSuggestOpen: (open: boolean) => void;
  fetchSuggestions: (q: string) => void;
  deleteStyleTag: (id: number) => Promise<void>;
}

export default function SearchBar({
  query,
  setQuery,
  onSearch,
  setIsDrawerOpen,
  openBookmarkDialog,
  savedQueries,
  // サジェスト用のPropsを受け取る
  suggestions,
  isSuggestOpen,
  setIsSuggestOpen,
  fetchSuggestions,
  deleteStyleTag,
}: SearchBarProps) {
  // 枠外クリック検知用のRefと、削除ダイアログ用のState
  const searchBarRef = useRef<HTMLDivElement>(null);
  const [styleToDelete, setStyleToDelete] = useState<Suggestion | null>(null);

  // クエリが変更されたら、少し遅れてAPIを叩く（デバウンス処理）
  useEffect(() => {
    const timer = setTimeout(() => {
      fetchSuggestions(query);
    }, 300); // 300ミリ秒入力が止まったら発火

    return () => clearTimeout(timer);
  }, [query, fetchSuggestions]);

  // サジェスト枠の外側をクリックしたら閉じる処理
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (searchBarRef.current && !searchBarRef.current.contains(e.target as Node)) {
        setIsSuggestOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [setIsSuggestOpen]);

  return (
    <>
      <div className="flex flex-row gap-2 w-full max-w-md">
        {/* ドロワーメニュー展開ボタン */}
        <button
          type="button"
          onClick={() => setIsDrawerOpen(true)}
          className="p-3 bg-[#27272a] hover:bg-zinc-700 text-zinc-400 hover:text-white rounded-md transition-colors flex items-center justify-center shrink-0"
        >
          <Menu size={16} />
        </button>

        {/* 検索フォーム */}
        <form onSubmit={onSearch} className="flex flex-row gap-2 grow">
          <div className="relative grow flex items-center">
            {/* 検索窓（テキストボックス） */}
            <input
              type="text"
              value={query}
              onFocus={() => setIsSuggestOpen(true)}
              // フォーカスが外れたらサジェストを閉じる（クリック判定のために少し遅延させる）
              onBlur={() => setTimeout(() => setIsSuggestOpen(false), 150)}
              onChange={(e) => {
                setQuery(e.target.value);
                setIsSuggestOpen(true);
              }}
              placeholder="タグやキーワードを入力..."
              className="p-3 pr-10 bg-[#27272a] rounded-md text-white placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-600 w-full min-w-0"
            />

            {/* 文字が入力されている時だけ表示されるクリアボタン */}
            {query && (
              <button
                type="button"
                // タップ時にフォーカスが外れる（キーボードが閉じる）のを防ぐ
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => setQuery("")}
                className="absolute right-2 p-2 text-zinc-400 hover:text-white rounded-full transition-colors flex items-center justify-center"
              >
                <X size={16} />
              </button>
            )}

            {/* サジェストのドロップダウンUI */}
            {isSuggestOpen && suggestions.length > 0 && (
              <div className="absolute top-full left-0 right-0 mt-1 bg-[#1E1E1E] border border-white/20 rounded-md shadow-2xl z-50 max-h-60 overflow-y-auto">
                {suggestions.map((s, idx) => (
                  <div
                    key={idx}
                    className="flex flex-row justify-between items-center border-b border-white/5 last:border-0 hover:bg-zinc-800 transition-colors"
                  >
                    <div
                      className="flex-1 p-3 cursor-pointer text-sm text-zinc-200"
                      onClick={() => {
                        setQuery(s.query); // 検索窓にクエリを反映
                        setIsSuggestOpen(false); // サジェストを閉じる
                      }}
                    >
                      {s.display}
                    </div>

                    {/* 絵柄タグ(is_style)の場合のみゴミ箱アイコンを表示 */}
                    {s.is_style && (
                      <button
                        type="button"
                        onClick={(e) => {
                          e.stopPropagation(); // クリックイベントの伝播を防ぐ
                          setStyleToDelete(s); // 削除ダイアログを開く
                        }}
                        className="p-3 text-zinc-500 hover:text-red-400 hover:bg-zinc-700 transition-colors shrink-0"
                        title="この絵柄タグを削除"
                      >
                        <Trash2 size={16} />
                      </button>
                    )}
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* 検索ボタン */}
          <button
            type="submit"
            className="p-3 bg-[#27272a] hover:bg-zinc-700 text-zinc-400 hover:text-white rounded-md transition-colors flex items-center justify-center shrink-0"
          >
            <Search size={16} />
          </button>
        </form>

        {/* ブックマーク保存ボタン */}
        <button
          type="button"
          // クエリが入力されている時だけダイアログを開けるようにする
          onClick={openBookmarkDialog}
          className={`p-3 rounded-md transition-colors flex items-center justify-center shrink-0 ${
            query.trim() 
              // 入力されたクエリが保存済みリストにある場合、緑色(text-green-400)にする
              ? savedQueries.includes(query.trim())
                ? "bg-[#27272a] hover:bg-zinc-700 text-green-400"
                : "bg-[#27272a] hover:bg-zinc-700 text-zinc-400 hover:text-white" 
              : "bg-[#27272a] text-zinc-600 cursor-not-allowed"
          }`}
        >
          {/* 保存済みかどうかに応じてアイコンを切り替える */}
          {query.trim() && savedQueries.includes(query.trim()) ? (
            <BookmarkCheck size={16} />
          ) : (
            <BookmarkPlus size={16} />
          )}
        </button>
      </div>

      {/* 絵柄タグの削除確認ダイアログ */}
      {styleToDelete && (
        <div className="fixed inset-0 z-60 flex items-center justify-center p-4">
          <div 
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setStyleToDelete(null)}
          ></div>
          
          <div className="relative bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl w-full max-w-sm p-6 flex flex-col gap-4">
            <h3 className="text-lg font-medium text-white">絵柄タグの削除</h3>
            
            <p className="text-zinc-300 text-sm">
              絵柄タグ「<span className="font-bold text-white">{styleToDelete.display}</span>」を削除しますか？<br/>
              （この操作は元に戻せません）
            </p>

            <div className="flex flex-row justify-end gap-2 mt-4">
              <button
                onClick={() => setStyleToDelete(null)}
                className="px-4 py-2 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded-md transition-colors"
              >
                キャンセル
              </button>
              <button
                onClick={async () => {
                  if (styleToDelete.id) {
                    await deleteStyleTag(styleToDelete.id);
                  }
                  setStyleToDelete(null);
                }}
                className="px-4 py-2 bg-red-600 hover:bg-red-500 text-white rounded-md transition-colors font-medium"
              >
                削除
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}