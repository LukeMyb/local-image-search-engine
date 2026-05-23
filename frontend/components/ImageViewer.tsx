import { useEffect } from "react";
import { X, Heart, ChevronLeft, ChevronRight } from "lucide-react";

// 検索結果のデータ構造を定義
interface SearchResult {
  id: number;
  is_favorite?: number;
}

interface ImageViewerProps {
  selectedImage: SearchResult;
  onClose: () => void;
  onToggleFavorite: (id: number, e: React.MouseEvent) => void;

  // 前後移動用のアクションと判定フラグ
  onNext?: () => void;
  onPrev?: () => void;
  hasSubsequent?: boolean;
  hasPreceding?: boolean;
}

export default function ImageViewer({
  selectedImage,
  onClose,
  onToggleFavorite,
  onNext,
  onPrev,
  hasSubsequent = false,
  hasPreceding = false,
}: ImageViewerProps) {

  // キーボード操作（← →）を検知して画像を切り替える処理
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight" && hasSubsequent && onNext) {
        onNext();
      } else if (e.key === "ArrowLeft" && hasPreceding && onPrev) {
        onPrev();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
    };
  }, [hasSubsequent, hasPreceding, onNext, onPrev]);

  return (
    <div 
      // 画面全体を覆う半透明の黒い背景
      className="fixed inset-0 bg-black flex items-center justify-center z-50 touch-none overscroll-none"
    >
      {/* 画像を中央に配置するコンテナ */}
      <div className="relative w-full h-full flex flex-col items-center">

        {/* 左移動ボタン (PCでのみ表示) */}
        {hasPreceding && onPrev && (
          <button
            onClick={(e) => { e.stopPropagation(); onPrev(); }}
            className="absolute left-0 top-0 bottom-0 w-1/4 z-10 hidden md:flex items-center justify-start pl-4 outline-none group cursor-pointer"
          >
            {/* アイコンの背景の丸い部分を div に分離し、group-hover で反応させる */}
            <div className="p-4 bg-black/50 group-hover:bg-black/80 text-white rounded-full transition-colors flex items-center justify-center">
              <ChevronLeft size={32} />
            </div>
          </button>
        )}

        <img 
          // 本画像(/image/)を呼び出す
          src={`http://192.168.11.3:8000/image/${selectedImage.id}`} 
          alt={`Selected ${selectedImage.id}`}
          className="w-full h-full object-contain"
        />

        {/* 右移動ボタン (PCでのみ表示) */}
        {hasSubsequent && onNext && (
          <button
            onClick={(e) => { e.stopPropagation(); onNext(); }}
            className="absolute right-0 top-0 bottom-0 w-1/4 z-10 hidden md:flex items-center justify-end pr-4 outline-none group cursor-pointer"
          >
            {/* アイコンの背景部分 */}
            <div className="p-4 bg-black/50 group-hover:bg-black/80 text-white rounded-full transition-colors flex items-center justify-center">
              <ChevronRight size={32} />
            </div>
          </button>
        )}

        {/* モーダル内のボタン */}
        <button
          onClick={(e) => onToggleFavorite(selectedImage.id, e)}
          className="absolute bottom-4 left-4 p-2 bg-black/50 rounded-full text-white hover:bg-black/80 transition-colors z-20"
        >
          <Heart 
            size={24} 
            className={selectedImage.is_favorite === 1 ? "fill-red-500 text-red-500" : "text-white"} 
          />
        </button>
        
        <button 
          // 閉じる処理をpropsで受け取った関数に置き換え
          onClick={onClose}
          className="absolute top-4 right-4 p-2 bg-black/50 text-white hover:bg-black/80 rounded-full transition-colors z-20"
        >
          <X size={24} />
        </button>
      </div>
    </div>
  );
}