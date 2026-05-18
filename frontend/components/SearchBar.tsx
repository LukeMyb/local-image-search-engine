import { Search, X, Menu, BookmarkPlus, BookmarkCheck } from "lucide-react";

interface SearchBarProps {
  query: string;
  setQuery: (q: string) => void;
  onSearch: (e?: React.FormEvent) => void;
  setIsDrawerOpen: (open: boolean) => void;
  openBookmarkDialog: () => void;
  savedQueries: string[];
}

export default function SearchBar({
  query,
  setQuery,
  onSearch,
  setIsDrawerOpen,
  openBookmarkDialog,
  savedQueries,
}: SearchBarProps) {
  return (
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
            onChange={(e) => setQuery(e.target.value)}
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
  );
}