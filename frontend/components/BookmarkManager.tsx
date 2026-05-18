import { useState, useEffect } from "react";
import { Trash2 } from "lucide-react";

// ブックマークのデータ構造を定義
interface Bookmark {
  id: number;
  name: string;
  query: string;
  last_used_at: string;
}

interface BookmarkManagerProps {
  isDrawerOpen: boolean;
  setIsDrawerOpen: (open: boolean) => void;
  isSaveDialogOpen: boolean;
  setIsSaveDialogOpen: (open: boolean) => void;
  query: string;
  setQuery: (q: string) => void;
  handleSearch: (e?: React.FormEvent, overrideQuery?: string) => Promise<void>;
  allBookmarks: Bookmark[];
  savedQueries: string[];
  refreshSavedQueries: () => Promise<void>;
}

export default function BookmarkManager({
  isDrawerOpen,
  setIsDrawerOpen,
  isSaveDialogOpen,
  setIsSaveDialogOpen,
  query,
  setQuery,
  handleSearch,
  allBookmarks,
  savedQueries,
  refreshSavedQueries,
}: BookmarkManagerProps) {
  // 取得したブックマーク一覧を保持する変数
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  // ドロワー内の検索フィルター文字を管理する変数
  const [drawerFilter, setDrawerFilter] = useState("");
  // 削除ダイアログの開閉状態と、削除対象のブックマークを保持
  const [isDeleteDialogOpen, setIsDeleteDialogOpen] = useState(false);
  const [bookmarkToDelete, setBookmarkToDelete] = useState<Bookmark | null>(null);
  // ブックマーク保存ダイアログの入力内容を管理
  const [newBookmarkName, setNewBookmarkName] = useState("");

  // 保存ダイアログが開かれたとき、またはクエリが変わったときに初期値をセットする
  useEffect(() => {
    if (isSaveDialogOpen) {
      const existingBm = allBookmarks.find(bm => bm.query.trim() === query.trim());
      if (existingBm) {
        setNewBookmarkName(existingBm.name);
      } else {
        setNewBookmarkName("");
      }
    }
  }, [isSaveDialogOpen, allBookmarks, query]);

  // ドロワーが開いている時に、ブックマーク一覧をサーバーから取得する
  useEffect(() => {
    if (!isDrawerOpen) return;

    const fetchBookmarks = async () => {
      try {
        const response = await fetch(
          `http://192.168.11.3:8000/bookmarks?filter_text=${encodeURIComponent(drawerFilter)}`
        );
        if (!response.ok) throw new Error("ブックマークの取得に失敗しました");
        const data = await response.json();
        setBookmarks(data.bookmarks);
      } catch (error) {
        console.error(error);
      }
    };

    fetchBookmarks();
  }, [isDrawerOpen, drawerFilter]); // <- ドロワーの開閉や、フィルター文字が変わるたびに実行

  // ブックマークをサーバーに保存する処理
  const handleSaveBookmark = async () => {
    if (!newBookmarkName.trim() || !query.trim()) return;

    try {
      // 既存のブックマーク（同じクエリで保存されているもの）が存在するか、名前が変更されているかを確認
      const existingBm = allBookmarks.find(bm => bm.query.trim() === query.trim());
      const isNameChanged = existingBm && existingBm.name.trim() !== newBookmarkName.trim();

      const response = await fetch("http://192.168.11.3:8000/bookmark", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: newBookmarkName.trim(),
          query: query.trim(),
        }),
      });

      if (!response.ok) throw new Error("保存に失敗しました");

      // 新規保存が「成功した場合のみ」、古いブックマークを削除（DELETE）する
      if (isNameChanged) {
        const deleteResponse = await fetch(`http://192.168.11.3:8000/bookmark/${existingBm.id}`, {
          method: "DELETE",
        });
        
        if (!deleteResponse.ok) {
          // もし削除だけ失敗した場合は、データ自体は残っているのでコンソール警告のみに留める
          console.error("古いブックマークの削除に失敗しましたが、新しい名前での保存は完了しています。");
        }
      }

      // 成功したらダイアログを閉じて入力欄をリセット
      setIsSaveDialogOpen(false);
      setNewBookmarkName("");
      // 保存が成功した瞬間に、メモリ上の保存済みクエリ一覧を最新にする
      await refreshSavedQueries();
      
    } catch (error) {
      console.error(error);
      alert("保存に失敗しました");
    }
  };

  // ブックマークを削除する処理
  const handleDeleteBookmark = async () => {
    if (!bookmarkToDelete) return;

    try {
      const response = await fetch(`http://192.168.11.3:8000/bookmark/${bookmarkToDelete.id}`, {
        method: "DELETE",
      });

      if (!response.ok) throw new Error("削除に失敗しました");

      // ドロワー内のリストから即座に消す
      setBookmarks(prev => prev.filter(bm => bm.id !== bookmarkToDelete.id));
      // 保存済みクエリの全リストも最新化
      await refreshSavedQueries();
      // ダイアログを閉じて状態をリセット
      setIsDeleteDialogOpen(false);
      setBookmarkToDelete(null);

    } catch (error) {
      console.error(error);
      alert("削除に失敗しました");
    }
  };

  return (
    <>
      {/* ドロワー（ブックマーク一覧）の描画処理 */}
      {isDrawerOpen && (
        <div className="fixed inset-0 z-50 flex">
          {/* 背景の半透明オーバーレイ（ここをタップするとドロワーが閉じる） */}
          <div 
            className="absolute inset-0 bg-black/50 backdrop-blur-sm"
            onClick={() => setIsDrawerOpen(false)}
          ></div>
          
          {/* ドロワー本体（左側に固定） */}
          <div className="relative w-80 max-w-[80%] bg-zinc-900 h-full shadow-2xl flex flex-col border-r border-zinc-800">
            
            {/* フィルター用検索窓 */}
            <div className="p-4 border-b border-zinc-800">
              <input
                type="text"
                // 値の同期と変更イベントの検知
                value={drawerFilter}
                onChange={(e) => setDrawerFilter(e.target.value)}
                placeholder="ブックマークを検索..."
                className="w-full p-3 bg-[#27272a] rounded-md text-white placeholder-zinc-400 focus:outline-none focus:ring-2 focus:ring-blue-600"
              />
            </div>
            
            {/* ブックマークリスト表示エリア */}
            <div className="flex-1 overflow-y-auto p-2 flex flex-col gap-1">
              {/* ブックマークが空の場合の表示 */}
              {bookmarks.length === 0 ? (
                <p className="text-zinc-500 text-center mt-8 text-sm">
                  {drawerFilter ? "一致するブックマークがありません" : "ブックマークがありません"}
                </p>
              ) : (
                // 取得したブックマークをループ処理でリスト表示
                bookmarks.map((bm) => (
                  <div
                    key={bm.id}
                    className="w-full border-b border-zinc-800/50 last:border-0 flex flex-row items-stretch group"
                  >
                    {/* 名前とクエリ */}
                    <div
                      onClick={() => {
                        setQuery(bm.query);
                        setIsDrawerOpen(false);
                        handleSearch(undefined, bm.query);
                      }}
                      className="flex-1 p-3 flex flex-col min-w-0 cursor-pointer hover:bg-zinc-800/30 active:bg-zinc-700 active:scale-[0.98] transition-all duration-75 origin-left"
                    >
                      <span className="text-sm font-medium text-zinc-200 truncate">
                        {bm.name}
                      </span>
                      <span className="text-xs text-zinc-500 truncate mt-0.5">
                        {bm.query}
                      </span>
                    </div>

                    {/* 削除ボタン */}
                    <div className="shrink-0 flex items-center justify-center p-3 pl-0">
                      <button
                        type="button"
                        className="p-2 text-zinc-500 hover:text-red-400 hover:bg-zinc-700/50 active:bg-zinc-700/50 active:scale-125 rounded-full transition-all shrink-0"
                        onClick={(e) => {
                          e.stopPropagation();
                          // 削除対象をセットして確認ダイアログを開く
                          setBookmarkToDelete(bm);
                          setIsDeleteDialogOpen(true);
                        }}
                      >
                        <Trash2 size={14} />
                      </button>
                    </div>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* 新規保存・編集ダイアログ */}
      {isSaveDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div 
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setIsSaveDialogOpen(false)}
          ></div>
          
          <div className="relative bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl w-full max-w-sm p-6 flex flex-col gap-4">
            {/* 保存済みかどうかでタイトルを切り替え */}
            <h3 className="text-lg font-medium text-white">
              {savedQueries.includes(query.trim()) ? "ブックマークを編集" : "検索条件を保存"}
            </h3>
            
            <div>
              <p className="text-sm text-zinc-400 mb-2">クエリ: <span className="text-zinc-200">{query}</span></p>
              <input
                type="text"
                value={newBookmarkName}
                onChange={(e) => setNewBookmarkName(e.target.value)}
                placeholder="ブックマーク名を入力..."
                className={`w-full p-3 bg-[#27272a] rounded-md text-white placeholder-zinc-500 focus:outline-none focus:ring-2 ${
                  // 重複している場合は枠線を赤にする
                  allBookmarks.some(bm => bm.name.trim() === newBookmarkName.trim() && bm.query.trim() !== query.trim())
                    ? "border border-red-500 focus:ring-red-500"
                    : "focus:ring-blue-600"
                }`}
                autoFocus // ダイアログが開いた瞬間にフォーカスを当てる
              />
              {/* リアルタイム重複エラーメッセージ */}
              {allBookmarks.some(bm => bm.name.trim() === newBookmarkName.trim() && bm.query.trim() !== query.trim()) && (
                <p className="text-red-400 text-sm mt-2">
                  この名前はすでに使用されています
                </p>
              )}
            </div>

            <div className="flex flex-row justify-end gap-2 mt-2">
              <button
                onClick={() => setIsSaveDialogOpen(false)}
                className="px-4 py-2 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded-md transition-colors"
              >
                キャンセル
              </button>
              <button
                onClick={handleSaveBookmark}
                // 名前が空、または重複している場合は押せないようにする
                disabled={!newBookmarkName.trim() || allBookmarks.some(bm => bm.name.trim() === newBookmarkName.trim() && bm.query.trim() !== query.trim())}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 disabled:text-white/50 text-white rounded-md transition-colors font-medium"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}

      {/* 削除確認ダイアログ */}
      {isDeleteDialogOpen && bookmarkToDelete && (
        <div className="fixed inset-0 z-60 flex items-center justify-center p-4">
          <div 
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setIsDeleteDialogOpen(false)}
          ></div>
          
          <div className="relative bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl w-full max-w-sm p-6 flex flex-col gap-4">
            <h3 className="text-lg font-medium text-white">ブックマークの削除</h3>
            
            <p className="text-zinc-300 text-sm">
              「<span className="font-bold text-white">{bookmarkToDelete.name}</span>」を削除しますか？<br/>
              この操作は元に戻せません。
            </p>

            <div className="flex flex-row justify-end gap-2 mt-4">
              <button
                onClick={() => setIsDeleteDialogOpen(false)}
                className="px-4 py-2 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded-md transition-colors"
              >
                キャンセル
              </button>
              <button
                onClick={handleDeleteBookmark}
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