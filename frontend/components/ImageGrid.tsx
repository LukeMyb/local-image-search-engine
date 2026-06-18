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

  // 列数管理用のPropsを受け取る
  gridColsPC?: number;
  setGridColsPC?: (cols: number) => void;
  gridColsMobile?: number;
  setGridColsMobile?: (cols: number) => void;
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
  gridColsPC = 6,
  setGridColsPC,
  gridColsMobile = 3,
  setGridColsMobile,
}: ImageGridProps) {
  // PC向けの列数を管理するState（初期値は6列）
  const [columns, setColumns] = useState(6);

  // 監視対象（一番下の透明な要素）への参照
  const observerTarget = useRef<HTMLDivElement>(null);

  // 最後に表示していた画像のIDを記憶しておくための変数
  const lastSelectedId = useRef<number | null>(null);

  // 上に戻るボタンを直接操作するための参照
  const scrollToTopBtnRef = useRef<HTMLButtonElement>(null);

  // スマホ向けピンチ操作の計算用Ref
  const initialDistance = useRef<number | null>(null);
  const initialCols = useRef<number | null>(null);
  const currentMobileColsRef = useRef<number>(gridColsMobile);
  // 親から列数が変わったら Ref も同期しておく
  useEffect(() => {
    currentMobileColsRef.current = gridColsMobile;
  }, [gridColsMobile]);

  // スマホのピンチ操作検知ロジック
  // 2点間の距離をピクセル単位で計算する関数
  const getDistance = (touches: React.TouchList) => {
    const dx = touches[0].clientX - touches[1].clientX;
    const dy = touches[0].clientY - touches[1].clientY;
    return Math.sqrt(dx * dx + dy * dy);
  };

  const handleTouchStart = (e: React.TouchEvent) => {
    // 指が2本触れた時だけ初期値を記録
    if (e.touches.length === 2 && setGridColsMobile) {
      initialDistance.current = getDistance(e.touches);
      initialCols.current = currentMobileColsRef.current;
    }
  };

  const handleTouchMove = (e: React.TouchEvent) => {
    if (e.touches.length === 2 && initialDistance.current !== null && initialCols.current !== null && setGridColsMobile) {
      const currentDistance = getDistance(e.touches);
      const scale = currentDistance / initialDistance.current;
      
      // スケールに応じて列数を計算 (拡大 = 列数減, 縮小 = 列数増)
      let newCols = Math.round(initialCols.current / scale);

      // スマホ向けの列数制限（1列 〜 最大8列くらいに制限）
      if (newCols < 1) newCols = 1;
      if (newCols > 8) newCols = 8;

      // 列数が変わったタイミングだけ親のStateを更新する（連続実行の防止）
      if (currentMobileColsRef.current !== newCols) {
        setGridColsMobile(newCols);
        currentMobileColsRef.current = newCols;
      }
    }
  };

  const handleTouchEnd = (e: React.TouchEvent) => {
    // 指が離れて2本未満になったら状態をリセット
    if (e.touches.length < 2) {
      initialDistance.current = null;
      initialCols.current = null;
    }
  };


  // Shift + ホイールでのPC向け列数変更ロジック
  useEffect(() => {
    const handleWheel = (e: WheelEvent) => {
      // Shiftキーが押されており、かつ更新関数が渡されている時のみ反応
      if (e.shiftKey && setGridColsPC) {
        e.preventDefault(); // デフォルトのスクロールを止める

        if (e.deltaY > 0) {
          // 下に回した時（縮小＝列数を増やす、最大12列）
          setGridColsPC(Math.min(gridColsPC + 1, 12));
        } else if (e.deltaY < 0) {
          // 上に回した時（拡大＝列数を減らす、最小2列）
          setGridColsPC(Math.max(gridColsPC - 1, 2));
        }
      }
    };

    window.addEventListener("wheel", handleWheel, { passive: false });
    return () => window.removeEventListener("wheel", handleWheel);
  }, [gridColsPC, setGridColsPC]); // ★変更: stateの最新値を依存配列に入れる

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
      {/* CSSのメディアクエリを使って、PCとスマホの列数を自動で切り替えるスタイルを定義 */}
      <style>{`
        .custom-dynamic-grid {
          grid-template-columns: repeat(${gridColsMobile}, minmax(0, 1fr));
        }
        @media (min-width: 768px) {
          .custom-dynamic-grid {
            grid-template-columns: repeat(${gridColsPC}, minmax(0, 1fr));
          }
        }
      `}</style>

      <div 
        className="grid gap-2 md:gap-4 mt-4 custom-dynamic-grid"
        onTouchStart={handleTouchStart}
        onTouchMove={handleTouchMove}
        onTouchEnd={handleTouchEnd}
        onTouchCancel={handleTouchEnd} // スクロールキャンセル時などの安全装置
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