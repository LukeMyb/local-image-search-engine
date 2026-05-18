"use client";

import { useState, useEffect } from "react";
import { Search, X, Heart, Menu, BookmarkPlus } from "lucide-react";

// 検索結果のデータ構造を定義
interface SearchResult {
  id: number;
  is_favorite?: number;
}

// ブックマークのデータ構造を定義
interface Bookmark {
  id: number;
  name: string;
  query: string;
  last_used_at: string;
}

export default function Home() {
  // ステータスを管理する変数
  const [statusMessage, setStatusMessage] = useState("システム待機中...");
  // 検索キーワードを管理する変数
  const [query, setQuery] = useState("");

  // 画像のデータ（配列）
  const [results, setResults] = useState<SearchResult[]>([]);
  // 選択された画像（モーダルで表示する画像）を管理する変数
  const [selectedImage, setSelectedImage] = useState<SearchResult | null>(null);

  // ドロワーの開閉状態を管理する変数
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);
  // 取得したブックマーク一覧を保持する変数
  const [bookmarks, setBookmarks] = useState<Bookmark[]>([]);
  // ドロワー内の検索フィルター文字を管理する変数
  const [drawerFilter, setDrawerFilter] = useState("");

  // ブックマーク保存ダイアログの開閉と入力内容を管理
  const [isSaveDialogOpen, setIsSaveDialogOpen] = useState(false);
  const [newBookmarkName, setNewBookmarkName] = useState("");

  // iOSの強制ズーム（ピンチ＆ダブルタップ）をJavaScriptで完全にブロックする
  useEffect(() => {
    // 1. ピンチイン・ピンチアウト（2本指でのズーム）を防ぐ
    const handleTouchMove = (e: TouchEvent) => {
      if (e.touches.length > 1) {
        e.preventDefault();
      }
    };

    // 2. ダブルタップによるズームを防ぐ
    let lastTouchEnd = 0;
    const handleTouchEnd = (e: TouchEvent) => {
      const now = new Date().getTime();
      if (now - lastTouchEnd <= 300) {
        e.preventDefault();
      }
      lastTouchEnd = now;
    };

    // イベントリスナーを登録（passive: false にすることで preventDefault が効くようになる）
    document.addEventListener("touchmove", handleTouchMove, { passive: false });
    document.addEventListener("touchend", handleTouchEnd, { passive: false });

    // クリーンアップ関数（アプリ終了時や画面移動時にイベントを解除する）
    return () => {
      document.removeEventListener("touchmove", handleTouchMove);
      document.removeEventListener("touchend", handleTouchEnd);
    };
  }, []); // <- 空の配列にすることで、アプリ起動時に1回だけ実行される

  // 開閉に合わせて背景のスクロールを制御する
  useEffect(() => {
    if (selectedImage || isDrawerOpen) {
      // 開いている時: ブラウザ全体のスクロールを隠す（無効化）
      document.documentElement.style.overflow = "hidden";
      document.documentElement.style.overscrollBehavior = "none";
      document.body.style.overflow = "hidden";
      document.body.style.overscrollBehavior = "none";
    } else {
      // 閉じた時: スクロール設定を元に戻す
      document.documentElement.style.overflow = "";
      document.documentElement.style.overscrollBehavior = "";
      document.body.style.overflow = "";
      document.body.style.overscrollBehavior = "";
    }

    // 安全装置: この画面から別のページへ移動した時などに、スクロール不可のままになるのを防ぐ
    return () => {
      document.documentElement.style.overflow = "";
      document.documentElement.style.overscrollBehavior = "";
      document.body.style.overflow = "";
      document.body.style.overscrollBehavior = "";
    };
  }, [selectedImage, isDrawerOpen]); // <- これらが変化するたびにこの処理を走らせる

  // ドロワーが開いている時に、ブックマーク一覧をサーバーから取得する
  useEffect(() => {
    if (!isDrawerOpen) return;

    const fetchBookmarks = async () => {
      try {
        // filter_text 引数を付けてPythonのAPIを叩く
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

  const handleSearch = async (e?: React.FormEvent, overrideQuery?: string) => {
    // フォーム送信によるページリロードを確実に阻止する
    if (e) e.preventDefault();

    // 検索実行時にスマホのキーボードを強制的に閉じる（フォーカスを外す）
    if (document.activeElement instanceof HTMLElement) {
      document.activeElement.blur();
    }

    // 直接渡されたキーワードがあればそれを使い、なければ検索窓(query)の値を使う
    const currentQuery = overrideQuery !== undefined ? overrideQuery : query;

    // 空文字（スペースのみ含む）の判定
    const isQueryEmpty = !currentQuery.trim();
    
    // 変数 endpoint を作成
    const endpoint = isQueryEmpty ? `/favorites` : `/search?q=${encodeURIComponent(currentQuery)}`;

    setStatusMessage(currentQuery ? `「${currentQuery}」を検索中...` : `お気に入り一覧を取得中...`);
    setResults([]); // 検索開始時に前の画像をクリア

    try {
      // Python側のAPIを叩く
      const response = await fetch(`http://192.168.11.3:8000${endpoint}`);

      if (!response.ok) {
        throw new Error(`HTTPエラー: ${response.status}`);
      }

      const data = await response.json();

      // 数千件の画像を一度に描画するとブラウザがフリーズするため、
      // 表示用の安全装置として先頭の50件だけ
      setResults(data.results.slice(0, 50));
      setStatusMessage(`${data.results.length}件の検索が完了しました（先頭50件を表示中）`);

    } catch (error) {
      console.error(error);
      setStatusMessage("通信エラーが発生しました。");
    }
  };

  // ブックマークをサーバーに保存する処理
  const handleSaveBookmark = async () => {
    if (!newBookmarkName.trim() || !query.trim()) return;

    try {
      const response = await fetch("http://192.168.11.3:8000/bookmark", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({
          name: newBookmarkName,
          query: query,
        }),
      });

      if (!response.ok) throw new Error("保存に失敗しました");

      // 成功したらダイアログを閉じて入力欄をリセット
      setIsSaveDialogOpen(false);
      setNewBookmarkName("");
      
      // ドロワーを開いた時に最新化されるため、ここでの再取得は不要
      
    } catch (error) {
      console.error(error);
      alert("保存に失敗しました");
    }
  };

  // お気に入りボタンを押した時の処理
  const toggleFavorite = async (image_id: number, e: React.MouseEvent) => {
    // 画像自体のクリック判定（モーダルを開く）が発動するのを防ぐ
    e.stopPropagation();

    try {
      // POSTでAPIを叩く
      const response = await fetch(`http://192.168.11.3:8000/favorite/${image_id}`, {
        method: "POST",
      });
      if (!response.ok) throw new Error("通信エラー");

      const data = await response.json();

      // 画面上のハートの色を即座に更新するため、resultsの配列を書き換える
      setResults(results.map(item => 
        item.id === image_id ? { ...item, is_favorite: data.is_favorite } : item
      ));
      
      // もしモーダルを開いている最中なら、モーダル側のデータも更新する
      if (selectedImage && selectedImage.id === image_id) {
        setSelectedImage({ ...selectedImage, is_favorite: data.is_favorite });
      }

    } catch (error) {
      console.error(error);
    }
  };

  return (
    // レイアウト
    <div className="p-2 min-h-screen bg-zinc-900 text-green-400 flex flex-col gap-4">
      <p className="text-lg font-medium">{statusMessage}</p>

      {/* 操作系をすべて1行にまとめるコンテナ */}
      <div className="flex flex-row gap-2 w-full max-w-md">
        {/* ドロワーメニュー展開ボタン */}
        <button
          type="button"
          onClick={() => setIsDrawerOpen(true)}
          className="p-3 bg-[#27272a] hover:bg-zinc-700 text-zinc-400 hover:text-white rounded-md transition-colors flex items-center justify-center shrink-0"
        >
          <Menu size={16} />
        </button>

        {/* 検索フォーム（中央で可能な限り広がるように flex-grow を指定） */}
        <form onSubmit={handleSearch} className="flex flex-row gap-2 grow">
          {/* 検索窓とクリアボタンを重ねるためのコンテナ */}
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
            {/* 虫眼鏡アイコンの本体 */}
            <Search size={16} />
          </button>
        </form>

        {/* ブックマーク保存ボタン（右端） */}
        <button
          type="button"
          // クエリが入力されている時だけダイアログを開けるようにする
          onClick={() => query.trim() && setIsSaveDialogOpen(true)}
          className={`p-3 rounded-md transition-colors flex items-center justify-center shrink-0 ${
            query.trim() 
              ? "bg-[#27272a] hover:bg-zinc-700 text-zinc-400 hover:text-white" 
              : "bg-[#27272a] text-zinc-600 cursor-not-allowed" // 空欄の時は押せない見た目に
          }`}
        >
          <BookmarkPlus size={16} />
        </button>
      </div>

      {/* 取得したIDを使って画像を並べる処理 */}
      <div className="grid grid-cols-3 gap-2 md:grid-cols-6 md:gap-4 mt-4">
        {results.map((item) => (
          // 画像とボタンを重ねるため、relative を持った div で囲む
          <div key={item.id} className="relative group">
            <img
              key={item.id}
              // Python側の画像のエンドポイントを呼び出し
              src={`http://192.168.11.3:8000/thumbnail/${item.id}`}
              alt={`Image ${item.id}`}
              // クリックされたら、この画像の情報を selectedImage にセットする
              onClick={() => setSelectedImage(item)}
              // カーソルを指マーク(cursor-pointer)にし、クリックできることを強調
              className="w-full aspect-square object-cover rounded-md cursor-pointer hover:opacity-80 transition-opacity"
            />

            {/* 右上に配置されるお気に入りマーク */}
            {item.is_favorite === 1 && (
              <div className="absolute bottom-1 right-1 p-1 md:p-2 pointer-events-none">
                <Heart className="w-5 h-5 md:w-6 md:h-6 fill-white text-white drop-shadow-[0_0_8px_rgba(0,0,0,0.8)]"/>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* モーダルの描画処理 (selectedImage に中身がある時だけ表示される) */}
      {selectedImage && (
        <div 
          // 画面全体を覆う半透明の黒い背景
          className="fixed inset-0 bg-black flex items-center justify-center z-50 touch-none overscroll-none"
        >
          {/* 画像を中央に配置するコンテナ */}
          <div className="relative w-full h-full flex flex-col items-center">
            <img 
              // 本画像(/image/)を呼び出す
              src={`http://192.168.11.3:8000/image/${selectedImage.id}`} 
              alt={`Selected ${selectedImage.id}`}
              className="w-full h-full object-contain"
            />

            {/* モーダル内のボタン */}
            <button
              onClick={(e) => toggleFavorite(selectedImage.id, e)}
              className="absolute bottom-4 left-4 p-2 bg-black/50 rounded-full text-white hover:bg-black/80 transition-colors"
            >
              <Heart 
                size={24} 
                className={selectedImage.is_favorite === 1 ? "fill-red-500 text-red-500" : "text-white"} 
              />
            </button>
            
            <button 
              onClick={() => setSelectedImage(null)}
              className="absolute top-4 right-4 p-2 bg-black/50 text-white hover:bg-black/80 rounded-full transition-colors"
            >
              <X size={24} />
            </button>
          </div>
        </div>
      )}

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
                    // タップ時の連動処理
                    onClick={() => {
                      setQuery(bm.query); // 検索窓の見た目を更新
                      setIsDrawerOpen(false); // ドロワーを閉じる
                      handleSearch(undefined, bm.query); // 即座に検索を実行
                    }}

                    className="w-full p-3 border-b border-zinc-800/50 last:border-0 hover:bg-zinc-800/30 active:bg-zinc-700 active:scale-[0.98] transition-all duration-75 flex flex-row items-center justify-between cursor-pointer group"
                  >
                    {/* 名前とクエリ */}
                    <div className="flex flex-col min-w-0 pr-2">
                      <span className="text-sm font-medium text-zinc-200 truncate">
                        {bm.name}
                      </span>
                      <span className="text-xs text-zinc-500 truncate mt-0.5">
                        {bm.query}
                      </span>
                    </div>

                    {/* 削除ボタン */}
                    <button
                      type="button"
                      className="p-2 text-zinc-500 hover:text-red-400 rounded-full hover:bg-zinc-700/50 transition-colors shrink-0 opacity-0 group-hover:opacity-100 focus:opacity-100"
                      onClick={(e) => e.stopPropagation()} // 親要素のクリック発動を防ぐ
                    >
                      <X size={14} /> {/* 一旦 X アイコンで代用 */}
                    </button>
                  </div>
                ))
              )}
            </div>
          </div>
        </div>
      )}

      {/* 新規保存ダイアログ */}
      {isSaveDialogOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
          <div 
            className="absolute inset-0 bg-black/60 backdrop-blur-sm"
            onClick={() => setIsSaveDialogOpen(false)}
          ></div>
          
          <div className="relative bg-zinc-900 border border-zinc-800 rounded-xl shadow-2xl w-full max-w-sm p-6 flex flex-col gap-4">
            <h3 className="text-lg font-medium text-white">検索条件を保存</h3>
            
            <div>
              <p className="text-sm text-zinc-400 mb-2">クエリ: <span className="text-zinc-200">{query}</span></p>
              <input
                type="text"
                value={newBookmarkName}
                onChange={(e) => setNewBookmarkName(e.target.value)}
                placeholder="ブックマーク名を入力..."
                className="w-full p-3 bg-[#27272a] rounded-md text-white placeholder-zinc-500 focus:outline-none focus:ring-2 focus:ring-blue-600"
                autoFocus // ダイアログが開いた瞬間にフォーカスを当てる
              />
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
                disabled={!newBookmarkName.trim()} // 名前が空なら押せない
                className="px-4 py-2 bg-blue-600 hover:bg-blue-500 disabled:bg-blue-600/50 disabled:text-white/50 text-white rounded-md transition-colors font-medium"
              >
                保存
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}