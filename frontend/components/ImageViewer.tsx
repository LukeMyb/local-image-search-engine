import { useEffect, useState } from "react";
import { X, Heart, ChevronLeft, ChevronRight } from "lucide-react";
import { API_BASE_URL } from "../lib/config";

// 検索結果のデータ構造を定義
interface SearchResult {
  id: number;
  is_favorite?: number;
  // 詳細パネルに表示するためのデータ
  file_path?: string;
  tags_combined?: string;
  [key: string]: any; // 他のプロパティも許容
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

  // スワイプ判定用のState
  const [touchStartX, setTouchStartX] = useState<number | null>(null);
  const [touchEndX, setTouchEndX] = useState<number | null>(null);
  const [touchStartY, setTouchStartY] = useState<number | null>(null);
  const [touchEndY, setTouchEndY] = useState<number | null>(null);

  // 詳細パネルの開閉状態を管理するState
  const [isDetailOpen, setIsDetailOpen] = useState(false);

  // 画像が切り替わった時は、詳細パネルを確実に閉じる
  useEffect(() => {
    setIsDetailOpen(false);
  }, [selectedImage.id]);

  // スワイプと判定する最低移動距離（ピクセル）
  const minSwipeDistance = 50;

  // タッチイベントのハンドラー群
  const onTouchStart = (e: React.TouchEvent) => {
    // 前回の終了位置をリセット
    setTouchEndX(null);
    setTouchEndY(null);

    setTouchStartX(e.targetTouches[0].clientX);
    setTouchStartY(e.targetTouches[0].clientY);
  };

  const onTouchMove = (e: React.TouchEvent) => {
    setTouchEndX(e.targetTouches[0].clientX);
    setTouchEndY(e.targetTouches[0].clientY);
  };

  const onTouchEnd = () => {
    if (!touchStartX || !touchEndX || !touchStartY || !touchEndY) return;

    // 移動距離を計算（開始位置 - 終了位置）
    // 横: 正なら左スワイプ、負なら右スワイプ
    // 縦: 正なら上スワイプ、負なら下スワイプ
    const distanceX = touchStartX - touchEndX;
    const distanceY = touchStartY - touchEndY;

    // 横方向より縦方向の移動量が大きい場合（縦スワイプの判定）
    if (Math.abs(distanceY) > Math.abs(distanceX)) {
      if (distanceY < -minSwipeDistance) {
        // 下スワイプ：パネルが開いていればパネルを閉じ、閉じていればビューアを閉じる
        if (isDetailOpen) {
          setIsDetailOpen(false);
        } else {
          onClose();
        }
      } else if (distanceY > minSwipeDistance) {
        // 上スワイプ：パネルが閉じていればパネルを開く
        if (!isDetailOpen) {
          setIsDetailOpen(true);
        }
      }
      return; // 縦スワイプと判定した場合は、左右の判定には進まない
    }

    // 左右スワイプ処理
    const isLeftSwipe = distanceX > minSwipeDistance;
    const isRightSwipe = distanceX < -minSwipeDistance;

    if (isLeftSwipe && hasSubsequent && onNext) {
      // 指を左に動かした ＝ 次の画像を見たい
      onNext();
    } else if (isRightSwipe && hasPreceding && onPrev) {
      // 指を右に動かした ＝ 前の画像を見たい
      onPrev();
    }
  };

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

  // 画面の余白タップで詳細パネルを閉じる処理
  const handleTap = () => {
    if (isDetailOpen) setIsDetailOpen(false);
  };

  // ファイルパスからファイル名だけを抽出する便利関数
  const getFileName = (path?: string) => {
    if (!path) return `Image ${selectedImage.id}`;
    // Windowsのバックスラッシュ(\)とMac/Linuxのスラッシュ(/)の両方に対応して分割
    return path.split(/[/\\]/).pop();
  };

  return (
    <div 
      // 画面全体を覆う半透明の黒い背景
      className="fixed inset-0 bg-black flex items-center justify-center z-50 touch-none overscroll-none"
      onClick={handleTap}
    >
      {/* 画像を中央に配置するコンテナ */}
      <div
        className="relative w-full h-full flex flex-col items-center"
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        >

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
          onClick={handleTap}
          src={`${API_BASE_URL}/image/${selectedImage.id}`}
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

        {/* お気に入り（ハート）ボタン */}
        <button
          onClick={(e) => onToggleFavorite(selectedImage.id, e)}
          className="absolute bottom-4 left-4 p-2 bg-black/50 rounded-full text-white hover:bg-black/80 transition-colors z-20"
        >
          <Heart 
            size={24} 
            className={selectedImage.is_favorite === 1 ? "fill-red-500 text-red-500" : "text-white"} 
          />
        </button>

        {/* 閉じるボタン */}
        <button 
          // 閉じる処理をpropsで受け取った関数に置き換え
          onClick={onClose}
          className="absolute top-4 right-4 p-2 bg-black/50 text-white hover:bg-black/80 rounded-full transition-colors z-20"
        >
          <X size={24} />
        </button>

        {/* 詳細情報パネル */}
        <div
          className={`absolute bottom-0 left-0 right-0 max-h-[50%] overflow-y-auto bg-zinc-900/95 backdrop-blur-md border-t border-zinc-700 text-white p-6 rounded-t-2xl transition-transform duration-300 ease-out flex flex-col gap-2 z-30 shadow-2xl ${
            isDetailOpen ? "translate-y-0" : "translate-y-full"
          }`}
          // パネル内の操作が後ろに抜けないようにする
          onClick={(e) => e.stopPropagation()} 
        >
          {/* ファイル名 */}
          <h3 className="text-lg font-bold break-all">
            {getFileName(selectedImage.file_path)}
          </h3>
          
          {/* ファイルパス */}
          <p className="text-xs text-zinc-400 break-all mb-2">
            {selectedImage.file_path || "パス情報なし"}
          </p>
          
          <hr className="border-zinc-700/50 my-2" />
          
          {/* タグ一覧 */}
          <p className="text-xs text-zinc-500 mb-1 font-medium">タグ一覧</p>
          <p className="text-sm text-zinc-200 leading-relaxed select-text">
            {selectedImage.tags_combined ? selectedImage.tags_combined.replace(/,/g, ', ') : "タグなし"}
          </p>
        </div>
      </div>
    </div>
  );
}