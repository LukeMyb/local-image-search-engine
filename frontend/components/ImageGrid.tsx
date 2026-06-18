import { useRef, useEffect, useState } from "react";
import { Heart, ArrowUp, CheckCircle } from "lucide-react";
import { API_BASE_URL } from "../lib/config";

// 検索結果のデータ構造を定義
interface SearchResult {
  id: number;
  is_favorite?: number;
}

interface ImageGridProps {
  results: SearchResult[];
  selectedImage: SearchResult | null;
  setSelectedImage: (item: SearchResult) => void;

  // 無限スクロール用の関数と判定フラグ
  loadMore?: () => void;
  hasMore?: boolean;

  // 選択モード用のProps
  isSelectionMode?: boolean;
  selectedIds?: number[];
  toggleSelection?: (id: number) => void;
}

export default function ImageGrid({ 
  results, 
  selectedImage,
  setSelectedImage,
  loadMore,
  hasMore,
  isSelectionMode = false,
  selectedIds = [],
  toggleSelection,
}: ImageGridProps) {
  // PC向けの列数を管理するState（初期値は6列）
  const [columns, setColumns] = useState(6);

  // 監視対象（一番下の透明な要素）への参照
  const observerTarget = useRef<HTMLDivElement>(null);

  // 最後に表示していた画像のIDを記憶しておくための変数
  const lastSelectedId = useRef<number | null>(null);

  // 上に戻るボタンを直接操作するための参照
  const scrollToTopBtnRef = useRef<HTMLButtonElement>(null);

  // Shift + ホイールでの列数変更ロジック
  useEffect(() => {
    const handleWheel = (e: WheelEvent) => {
      // Shiftキーが押されている時だけ反応する
      if (e.shiftKey) {
        // ブラウザ標準のスクロール（横移動や縦移動）を強制キャンセル
        e.preventDefault();

        if (e.deltaY > 0) {
          // 下に回した時（縮小したい＝列数を増やす）: 最大12列くらいで制限
          setColumns((prev) => Math.min(prev + 1, 12));
        } else if (e.deltaY < 0) {
          // 上に回した時（拡大したい＝列数を減らす）: 最小2列で制限
          setColumns((prev) => Math.max(prev - 1, 2));
        }
      }
    };

    // passive: false にしないと preventDefault() が効かない
    window.addEventListener("wheel", handleWheel, { passive: false });
    return () => window.removeEventListener("wheel", handleWheel);
  }, []);

  // スクロール量に応じてボタンの表示/非表示を直接切り替える処理
  useEffect(() => {
    const handleScroll = () => {
      if (!scrollToTopBtnRef.current) return;
      
      // 300px以上下にスクロールしたら表示、それ以外は隠す
      if (window.scrollY > 300) {
        scrollToTopBtnRef.current.style.opacity = "1";
        scrollToTopBtnRef.current.style.pointerEvents = "auto";
        scrollToTopBtnRef.current.style.transform = "translateY(0)";
      } else {
        scrollToTopBtnRef.current.style.opacity = "0";
        scrollToTopBtnRef.current.style.pointerEvents = "none";
        scrollToTopBtnRef.current.style.transform = "translateY(10px)";
      }
    };

    // passive: true をつけることで、スクロール操作自体の動作を軽くする
    window.addEventListener("scroll", handleScroll, { passive: true });
    return () => window.removeEventListener("scroll", handleScroll);
  }, []);

  // ビューアが閉じた瞬間に、見ていた画像の位置へスクロールする処理
  useEffect(() => {
    if (selectedImage) {
      // ビューアが開いている間は、スワイプされるたびに「今見ているID」を上書き記憶する
      lastSelectedId.current = selectedImage.id;
    } else if (lastSelectedId.current) {
      // ビューアが閉じた瞬間（selectedImageがnullになった時）
      const idToScroll = lastSelectedId.current;
      
      // システムのスクロールロック解除が終わった瞬間瞬時に実行
      setTimeout(() => {
        const el = document.getElementById(`grid-image-${idToScroll}`);
        if (el) {
          // 画面内に見えている場合は動かず、画面外にある場合のみ一番近い端にスクロール
          el.scrollIntoView({ block: "nearest", behavior: "auto" });
        }
      }, 0);

      // スクロールが終わったら記憶をリセット
      lastSelectedId.current = null;
    }
  }, [selectedImage]);

  // スクロール検知ロジック
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        // 目印が画面に入ってきて、かつまだ続きがある場合にロードを発火
        if (entries[0].isIntersecting && hasMore && loadMore) {
          loadMore();
        }
      },
      // 画面の下端から200px手前（見えない位置）で早めに発火させる
      { rootMargin: "200px" }
    );

    if (observerTarget.current) {
      observer.observe(observerTarget.current);
    }

    return () => {
      if (observerTarget.current) {
        observer.unobserve(observerTarget.current);
      }
    };
  }, [hasMore, loadMore]);

  return (
    <>
      <div 
        className="grid gap-2 md:gap-4 mt-4"
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
      >
        {results.map((item) => {
          // この画像が選択されているかどうかの判定
          const isSelected = selectedIds.includes(item.id);

          return (
            // 画像とボタンを重ねるため、relative を持った div で囲む
            <div key={item.id} className="relative group">
              {/* 選択時はパディング(白枠)をつけるためのラッパー */}
              <div 
                className={`relative w-full h-full rounded-md overflow-hidden transition-all duration-200 ${
                  isSelected ? "p-1.5 bg-white" : "p-0 bg-transparent"
                }`}
              >
                <img
                  key={item.id}
                  id={`grid-image-${item.id}`} // スクロールのジャンプ先となる目印（ID）を付ける
                  // Python側の画像のエンドポイントを呼び出し
                  src={`${API_BASE_URL}/thumbnail/${item.id}`}
                  alt={`Image ${item.id}`}

                  // 選択モードONの時は選択切り替え、OFFの時はビューアを開く
                  onClick={() => {
                    if (isSelectionMode && toggleSelection) {
                      toggleSelection(item.id);
                    } else {
                      setSelectedImage(item);
                    }
                  }}

                  className={`w-full h-full object-cover transition-all duration-200 scroll-mt-0 md:scroll-mt-24 ${
                    isSelectionMode ? "cursor-cell" : "cursor-pointer"
                  } ${isSelected ? "rounded-sm" : "rounded-md"}`}
                />
              </div>

              {/* 選択モードONで、選択されている場合のチェックマーク（右上） */}
              {isSelectionMode && isSelected && (
                <div className="absolute top-2 right-2 pointer-events-none z-10">
                  <CheckCircle className="w-5 h-5 text-white fill-blue-500 drop-shadow-md" />
                </div>
              )}

              {/* 選択モードONだが、未選択の場合の薄い丸（タップ誘導） */}
              {isSelectionMode && !isSelected && (
                <div className="absolute top-2 right-2 pointer-events-none z-10 opacity-50">
                  <div className="w-5 h-5 rounded-full border-2 border-white drop-shadow-md bg-black/20" />
                </div>
              )}

              {/* 右上に配置されるお気に入りマーク */}
              {item.is_favorite === 1 && (
                <div className="absolute bottom-1 right-1 p-1 md:p-2 pointer-events-none">
                  <Heart className="w-5 h-5 md:w-6 md:h-6 fill-white text-white drop-shadow-[0_0_8px_rgba(0,0,0,0.8)]"/>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* 無限スクロールの検知用タグ（この透明な箱が画面に入ったら次を読み込む） */}
      <div ref={observerTarget} className="h-4 w-full" />

      {/* 一番上に戻るボタン */}
      <button
        ref={scrollToTopBtnRef}
        onClick={() => window.scrollTo({ top: 0, behavior: "smooth" })}
        className="fixed bottom-6 right-6 p-3 bg-zinc-800/50 text-white rounded-full shadow-lg backdrop-blur-md transition-all duration-300 hover:bg-zinc-700/80 z-40 opacity-0 pointer-events-none translate-y-2 border border-zinc-700/50"
      >
        <ArrowUp size={24} />
      </button>
    </>
  );
}