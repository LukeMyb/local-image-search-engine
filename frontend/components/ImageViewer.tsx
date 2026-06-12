import { useEffect, useState, useCallback } from "react";
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
  prevImage?: SearchResult | null;
  nextImage?: SearchResult | null;

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
  prevImage,
  nextImage,
  hasSubsequent = false,
  hasPreceding = false,
}: ImageViewerProps) {

  // スワイプ判定用のState
  const [touchStartX, setTouchStartX] = useState<number | null>(null);
  const [touchStartY, setTouchStartY] = useState<number | null>(null);
  // スワイプの速度を計算するために、指が触れた瞬間の時間を記録するState
  const [touchStartTime, setTouchStartTime] = useState<number | null>(null);

  // ドラッグによるX軸の移動量と、各種状態の判定フラグ
  const [dragX, setDragX] = useState(0);
  const [isAnimating, setIsAnimating] = useState(false); 

  // 方向を完全にロックするための swipeDirection
  const [swipeDirection, setSwipeDirection] = useState<'horizontal' | 'vertical' | null>(null);

  // 詳細パネルの開閉状態を管理するState
  const [isDetailOpen, setIsDetailOpen] = useState(false);

  // 展開アニメーションの状態と、起点（座標）を管理するState
  const [entranceState, setEntranceState] = useState<'init' | 'animating' | 'done' | 'closing'>('init');
  const [transformOrigin, setTransformOrigin] = useState("center center");

  // 初回マウント時（画像を開いた瞬間）のみ、サムネイルの位置を取得してアニメーションを発火
  useEffect(() => {
    // 裏側にあるサムネイルのDOM要素を取得
    const el = document.getElementById(`grid-image-${selectedImage.id}`);
    if (el) {
      const rect = el.getBoundingClientRect();
      // 画面全体から見たサムネイルの中央の座標を計算して起点に設定
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      setTransformOrigin(`${cx}px ${cy}px`);
    }

    // 次の描画フレームでアニメーションを開始 (init -> animating)
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        setEntranceState('animating');
        // アニメーション完了（300ms）後にtransitionクラスを外し、通常のスワイプに影響が出ないようにする
        setTimeout(() => {
          setEntranceState('done');
        }, 300);
      });
    });
  }, []); // 空配列なので「一覧から開いた最初の1回」だけ実行される

  // 画像が切り替わった時は、パネルを閉じ、ドラッグ位置も0にリセットする
  useEffect(() => {
    setIsDetailOpen(false);
    setDragX(0);
    setSwipeDirection(null);
  }, [selectedImage.id]);

  // 閉じるボタンや縦スワイプ時に呼ばれる、アニメーション付きの閉じる関数
  const handleClose = useCallback(() => {
    if (entranceState === 'closing') return;

    // アニメーション開始直前に、useSystemUIによるスクロールロックを先行して解除する
    // これにより、閉じるアニメーションの最中に裏側のスクロールバーやヘッダーのレイアウトが先行して復元される
    document.documentElement.style.overflow = "";
    document.documentElement.style.overscrollBehavior = "";
    document.body.style.overflow = "";
    document.body.style.overscrollBehavior = "";

    // 現在表示している画像のサムネイルDOMを取得
    const el = document.getElementById(`grid-image-${selectedImage.id}`);
    
    if (el) {
      // 画面外にある場合は一番近い端にスクロールさせる
      el.scrollIntoView({ block: "nearest" });

      // スクロール直後の「新しい座標」を取得し、吸い込まれるゴール地点としてセットする
      const rect = el.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      setTransformOrigin(`${cx}px ${cy}px`);
    }

    // アニメーション状態を 'closing' にして、縮小＆フェードアウトを開始
    setEntranceState('closing');

    // アニメーション完了（300ms）後に、親から渡された本当の onClose を呼んで破棄する
    setTimeout(() => {
      onClose();
    }, 300);
  }, [selectedImage.id, onClose, entranceState]);

  // スワイプと判定する最低移動距離（ピクセル）
  const minSwipeDistance = 50;

  // 完全にスライドしきってから画像を切り替える関数（次へ）
  const executeNext = useCallback(() => {
    if (!hasSubsequent || !onNext || isAnimating) return; // 連打防止
    
    setIsAnimating(true);
    // 画面幅分だけ左へ完全にスライドさせる
    setDragX(-(typeof window !== "undefined" ? window.innerWidth : 1000));
    
    // スライド完了（300ms）を待ってから、位置を0に戻して画像を切り替える
    setTimeout(() => {
      setIsAnimating(false);
      setDragX(0);
      onNext();
    }, 300);
  }, [hasSubsequent, onNext, isAnimating]);

  // 完全にスライドしきってから画像を切り替える関数（前へ）
  const executePrev = useCallback(() => {
    if (!hasPreceding || !onPrev || isAnimating) return; // 連打防止

    setIsAnimating(true);
    // 画面幅分だけ右へ完全にスライドさせる
    setDragX(typeof window !== "undefined" ? window.innerWidth : 1000);
    
    setTimeout(() => {
      setIsAnimating(false);
      setDragX(0);
      onPrev();
    }, 300);
  }, [hasPreceding, onPrev, isAnimating]);

  // タッチイベントのハンドラー群
  const onTouchStart = (e: React.TouchEvent) => {
    // アニメーション中（ページめくり中）は画面へのタッチ操作を無効化し、誤引き戻しを防ぐ
    if (isAnimating) return;

    setTouchStartX(e.targetTouches[0].clientX);
    setTouchStartY(e.targetTouches[0].clientY);
    setTouchStartTime(Date.now());

    // ドラッグ開始の初期化
    setIsAnimating(false);
    setDragX(0);
    setSwipeDirection(null);
  };

  const onTouchMove = (e: React.TouchEvent) => {
    if (touchStartX === null || touchStartY === null) return;

    const currentX = e.targetTouches[0].clientX;
    const currentY = e.targetTouches[0].clientY;
    const diffX = currentX - touchStartX;
    const diffY = currentY - touchStartY;

    // 最初の10pxの動きで「縦」か「横」かを一度だけ確定し、以後変更しない
    let currentDirection = swipeDirection;
    if (currentDirection === null) {
      if (Math.abs(diffX) > 10 || Math.abs(diffY) > 10) {
        if (Math.abs(diffY) > Math.abs(diffX)) {
          currentDirection = 'vertical';
        } else {
          currentDirection = 'horizontal';
        }
        setSwipeDirection(currentDirection);
      }
    }

    // 「横」に確定している場合のみ、どんなにXが0をまたいでも追従を続ける
    if (currentDirection === 'horizontal') {
      let moveX = diffX;
      if ((moveX > 0 && !hasPreceding) || (moveX < 0 && !hasSubsequent)) {
        moveX = moveX * 0.25;
      }
      setDragX(moveX);
    }
  };

  const onTouchEnd = (e: React.TouchEvent) => {
    if (touchStartX === null || touchStartY === null) return;

    const endX = e.changedTouches[0].clientX;
    const endY = e.changedTouches[0].clientY;

    // 移動距離を計算（開始位置 - 終了位置）
    const distanceX = touchStartX - endX;
    const distanceY = touchStartY - endY;

    // 指が触れていた時間（ミリ秒）から、X軸の移動速度（ピクセル/ミリ秒）を計算
    const elapsedTime = touchStartTime ? Date.now() - touchStartTime : 1;
    const velocityX = Math.abs(distanceX) / elapsedTime;

    // 縦スワイプだった場合（詳細パネル・閉じる処理）
    if (swipeDirection === 'vertical' || (swipeDirection === null && Math.abs(distanceY) > Math.abs(distanceX))) {
      if (distanceY < -minSwipeDistance) {
        if (isDetailOpen) setIsDetailOpen(false);
        else handleClose();
      } else if (distanceY > minSwipeDistance) {
        if (!isDetailOpen) setIsDetailOpen(true);
      }
      // リセット
      setIsAnimating(true);
      setDragX(0);
      setTimeout(() => setIsAnimating(false), 300);
      setTouchStartX(null);
      setTouchStartY(null);
      setTouchStartTime(null);
      setSwipeDirection(null);
      return;
    }

    // 画面幅の40%以上移動したか、または速度が0.4px/ms以上の素早いフリックだったかを判定
    const thresholdX = typeof window !== "undefined" ? window.innerWidth * 0.4 : 150;
    const isHorizontalFlick = velocityX > 0.4 && Math.abs(distanceX) > 30;

    // 横スワイプだった場合（画像の切り替え処理）
    if (Math.abs(distanceX) > thresholdX || isHorizontalFlick) {
      if (distanceX > 0 && hasSubsequent && onNext) {
        executeNext();
      } else if (distanceX < 0 && hasPreceding && onPrev) {
        executePrev();
      } else {
        // 条件を満たしたが、次の画像（または前の画像）が存在しない場合は元の位置に戻る
        setIsAnimating(true);
        setDragX(0);
        setTimeout(() => setIsAnimating(false), 300);
      }
    } else {
      // スワイプ距離や速度が足りなかった場合は元の位置に戻る
      setIsAnimating(true);
      setDragX(0);
      setTimeout(() => setIsAnimating(false), 300);
    }

    setTouchStartX(null);
    setTouchStartY(null);
    setTouchStartTime(null);
    setSwipeDirection(null);
  };

  // キーボード操作（← →）を検知して画像を切り替える処理
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "ArrowRight") {
        executeNext();
      } else if (e.key === "ArrowLeft") {
        executePrev();
      } else if (e.key === "Escape") { // Escキーでも閉じるように
        handleClose();
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
      className="fixed inset-0 z-50 touch-none overscroll-none"
      onClick={handleTap}
    >
      {/* アニメーションで独立してフェードインする黒い背景 */}
      <div 
        className={`absolute inset-0 bg-black transition-opacity duration-300 ease-out ${
          entranceState === 'init' || entranceState === 'closing' ? 'opacity-0' : 'opacity-100'
        }`}
      />

      {/* 画像を中央に配置するコンテナ */}
      <div
        // アニメーションの状態（scaleとopacity）を制御し、サムネイルの座標を中心に拡大させる
        className={`relative w-full h-full flex flex-col items-center overflow-hidden ${
          entranceState === 'init' || entranceState === 'closing' ? 'scale-50 opacity-0' : 'scale-100 opacity-100'
        } ${
          entranceState !== 'done' ? 'transition-all duration-300 ease-out' : ''
        }`}
        style={{ transformOrigin }}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onClick={(e) => e.stopPropagation()}
      >

        {/* ドラッグでスライドする3枚の画像のコンテナ（レール） */}
        <div
          className={`absolute inset-0 w-full h-full flex items-center ${
            // ドラッグ中はアニメーションを切って指に完全追従させ、離した時はtransitionで滑らかに動かす
            isAnimating ? "transition-transform duration-300 ease-out" : ""
          }`}
          style={{ transform: `translateX(${dragX}px)` }}
        >
          {/* 前の画像（画面左外に配置） */}
          {prevImage && (
            <div className="absolute -left-full w-full h-full flex items-center justify-center">
              <img src={`${API_BASE_URL}/image/${prevImage.id}`} className="max-w-full max-h-full object-contain" alt="Previous" />
            </div>
          )}

          {/* 現在の画像（画面中央に配置） */}
          <div className="w-full h-full flex items-center justify-center">
            <img 
              onClick={handleTap}
              src={`${API_BASE_URL}/image/${selectedImage.id}`}
              alt={`Selected ${selectedImage.id}`}
              className="max-w-full max-h-full object-contain"
            />
          </div>

          {/* 次の画像（画面右外に配置） */}
          {nextImage && (
            <div className="absolute -right-full w-full h-full flex items-center justify-center">
              <img src={`${API_BASE_URL}/image/${nextImage.id}`} className="max-w-full max-h-full object-contain" alt="Next" />
            </div>
          )}
        </div>

        {/* 左移動ボタン (PCでのみ表示) */}
        {hasPreceding && onPrev && (
          <button
            onClick={(e) => { e.stopPropagation(); executePrev(); }}
            className="absolute left-0 top-0 bottom-0 w-1/4 z-10 hidden md:flex items-center justify-start pl-4 outline-none group cursor-pointer"
          >
            {/* アイコンの背景の丸い部分を div に分離し、group-hover で反応させる */}
            <div className="p-4 bg-black/50 group-hover:bg-black/80 text-white rounded-full transition-colors flex items-center justify-center">
              <ChevronLeft size={32} />
            </div>
          </button>
        )}

        {/* 右移動ボタン (PCでのみ表示) */}
        {hasSubsequent && onNext && (
          <button
            onClick={(e) => { e.stopPropagation(); executeNext(); }}
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
          onClick={handleClose}
          className={`absolute top-4 right-4 p-2 bg-black/50 text-white hover:bg-black/80 rounded-full transition-all duration-300 z-20 ${
            entranceState === 'closing' ? 'opacity-0' : 'opacity-100'
          }`}
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