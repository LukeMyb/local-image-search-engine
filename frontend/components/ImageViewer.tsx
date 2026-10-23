import { useEffect, useState, useCallback, useRef } from "react";
import { X, Heart, ChevronLeft, ChevronRight, Search } from "lucide-react";
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
  onSearchSimilar?: (image: SearchResult) => void;

  // 前後移動用のアクションと判定フラグ
  onNext?: () => void;
  onPrev?: () => void;
  hasSubsequent?: boolean;
  hasPreceding?: boolean;
  isUIVisible: boolean;
  onToggleUI: () => void;
}

export default function ImageViewer({
  selectedImage,
  onClose,
  onToggleFavorite,
  onSearchSimilar,
  onNext,
  onPrev,
  prevImage,
  nextImage,
  hasSubsequent = false,
  hasPreceding = false,
  isUIVisible,
  onToggleUI,
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

  // ピンチイン・アウトやPCズームモードによるズーム倍率とパン（移動量）を管理するState
  const [zoomScale, setZoomScale] = useState(1);
  const [panX, setPanX] = useState(0);
  const [panY, setPanY] = useState(0);
  // PCズームモード中にマウスホールドでドラッグしているかどうかのState（カーソル表示用）
  const [isMouseDragging, setIsMouseDragging] = useState(false);

  // 現在の画像DOMおよびビューアコンテナへの参照
  const currentImgRef = useRef<HTMLImageElement>(null);
  const viewerContainerRef = useRef<HTMLDivElement>(null);

  // ピンチ・パン・バウンスアニメーション計算用のRef
  const zoomStateRef = useRef<{ scale: number; x: number; y: number }>({ scale: 1, x: 0, y: 0 });
  const rawPanRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const zoomRafRef = useRef<number | null>(null);
  const pinchStartDistRef = useRef<number | null>(null);
  const pinchStartScaleRef = useRef<number>(1);
  const pinchStartPanRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const pinchStartMidRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const panStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const isPinchingRef = useRef(false);
  const suppressTapRef = useRef(false);

  // PCでのマウスドラッグ・ダブルクリック判定用のRef
  const isMouseDraggingRef = useRef(false);
  const mouseStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const tapTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // 実行待ちのスワイプ操作を貯めておくキュー（レンダリングに影響を与えないようRefを使用）
  const actionQueue = useRef<('next' | 'prev')[]>([]);
  // アニメーションの重複やタップによる干渉を防ぐためのロック用フラグ
  const isProcessingQueue = useRef(false);

  // iOSライクな非線形ラバーバンド（出だしは柔らかく、引っ張るほど滑らかに抵抗が増す曲線）のパラメータ
  const PAN_RUBBER_CONSTANT = 0.55;
  const ZOOM_RUBBER_CONSTANT = 0.65;
  const ZOOM_MAX_SHRINK = 0.5; // 等倍から最大0.5倍（1 - 0.5）に向かって漸近的に減衰

  // StateとRefを同期して更新する関数
  const updateZoomState = useCallback((scale: number, x: number, y: number) => {
    zoomStateRef.current = { scale, x, y };
    setZoomScale(scale);
    setPanX(x);
    setPanY(y);
  }, []);

  // 実行中のバウンスアニメーションを停止する関数
  const stopZoomAnimation = useCallback(() => {
    if (zoomRafRef.current !== null) {
      cancelAnimationFrame(zoomRafRef.current);
      zoomRafRef.current = null;
    }
  }, []);

  // CSS transitionの切り替えによる高倍率時のGPUレイヤー再生成（黒飛び・ちらつき）を防ぐため、
  // requestAnimationFrameで現在の座標・倍率から目標値へなめらかにバウンス復帰させる関数
  const animateZoomTo = useCallback(
    (targetScale: number, targetX: number, targetY: number, duration = 380) => {
      stopZoomAnimation();

      const startScale = zoomStateRef.current.scale;
      const startX = zoomStateRef.current.x;
      const startY = zoomStateRef.current.y;

      rawPanRef.current = { x: targetX, y: targetY };

      if (
        Math.abs(startScale - targetScale) < 0.001 &&
        Math.abs(startX - targetX) < 0.5 &&
        Math.abs(startY - targetY) < 0.5
      ) {
        updateZoomState(targetScale, targetX, targetY);
        return;
      }

      const startTime = performance.now();

      const step = (now: number) => {
        const elapsed = now - startTime;
        const progress = Math.min(elapsed / duration, 1);
        // 指を離した初速が自然で終端に向かって滑らかに収束するイージング (quartic ease-out)
        const ease = 1 - Math.pow(1 - progress, 4);

        const nextScale = startScale + (targetScale - startScale) * ease;
        const nextX = startX + (targetX - startX) * ease;
        const nextY = startY + (targetY - startY) * ease;

        updateZoomState(nextScale, nextX, nextY);

        if (progress < 1) {
          zoomRafRef.current = requestAnimationFrame(step);
        } else {
          zoomRafRef.current = null;
          updateZoomState(targetScale, targetX, targetY);
        }
      };

      zoomRafRef.current = requestAnimationFrame(step);
    },
    [stopZoomAnimation, updateZoomState]
  );

  // 2本指の距離をピクセル単位で計算する関数
  const getTouchDistance = (touches: React.TouchList) => {
    const dx = touches[0].clientX - touches[1].clientX;
    const dy = touches[0].clientY - touches[1].clientY;
    return Math.sqrt(dx * dx + dy * dy);
  };

  // 現在の拡大率におけるパン（移動可能範囲）の上限値を計算する関数
  const getPanBounds = useCallback((scale: number) => {
    if (scale <= 1) return { maxPanX: 0, maxPanY: 0 };

    const baseWidth = currentImgRef.current?.clientWidth || (typeof window !== "undefined" ? window.innerWidth : 0);
    const baseHeight = currentImgRef.current?.clientHeight || (typeof window !== "undefined" ? window.innerHeight : 0);

    return {
      maxPanX: (baseWidth * (scale - 1)) / 2,
      maxPanY: (baseHeight * (scale - 1)) / 2,
    };
  }, []);

  // 拡大時のパン（移動量）を画像の端ぴったりに制限する関数（バウンス復帰先）
  const clampPan = useCallback((nextPanX: number, nextPanY: number, scale: number) => {
    const { maxPanX, maxPanY } = getPanBounds(scale);
    return {
      x: Math.min(Math.max(nextPanX, -maxPanX), maxPanX),
      y: Math.min(Math.max(nextPanY, -maxPanY), maxPanY),
    };
  }, [getPanBounds]);

  // 端を超えた移動に対して、非線形ラバーバンド曲線でなめらかに減衰させる関数
  const applyRubberBandPan = useCallback((nextPanX: number, nextPanY: number, scale: number) => {
    const { maxPanX, maxPanY } = getPanBounds(scale);
    const dimX = typeof window !== "undefined" ? window.innerWidth : 400;
    const dimY = typeof window !== "undefined" ? window.innerHeight : 800;

    const rubberBand = (val: number, max: number, dim: number) => {
      if (val > max) {
        const overscroll = val - max;
        return max + (overscroll * dim * PAN_RUBBER_CONSTANT) / (dim + PAN_RUBBER_CONSTANT * overscroll);
      }
      if (val < -max) {
        const overscroll = -max - val;
        return -max - (overscroll * dim * PAN_RUBBER_CONSTANT) / (dim + PAN_RUBBER_CONSTANT * overscroll);
      }
      return val;
    };

    return {
      x: rubberBand(nextPanX, maxPanX, dimX),
      y: rubberBand(nextPanY, maxPanY, dimY),
    };
  }, [getPanBounds]);

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

    return () => {
      stopZoomAnimation();
      if (tapTimerRef.current) {
        clearTimeout(tapTimerRef.current);
      }
    };
  }, [stopZoomAnimation]); // 初回マウント時のみ実行

  // 画像が切り替わった時は、パネルを閉じ、ドラッグ位置・ズーム状態もリセットする
  useEffect(() => {
    stopZoomAnimation();
    setIsDetailOpen(false);
    setDragX(0);
    setSwipeDirection(null);
    updateZoomState(1, 0, 0);
    rawPanRef.current = { x: 0, y: 0 };
    pinchStartDistRef.current = null;
    isPinchingRef.current = false;
    isMouseDraggingRef.current = false;
    setIsMouseDragging(false);
  }, [selectedImage.id, stopZoomAnimation, updateZoomState]);

  // PCでのホイールによるズーム倍率変更（passive: false でブラウザ標準スクロール等を抑止）
  useEffect(() => {
    const el = viewerContainerRef.current;
    if (!el) return;

    const handleWheel = (e: WheelEvent) => {
      // ズームモード中（倍率 > 1）のみホイールで倍率を変更する
      const currentScale = zoomStateRef.current.scale;
      if (currentScale <= 1) return;

      e.preventDefault();
      e.stopPropagation();

      stopZoomAnimation();

      // ホイールの回転方向に応じて倍率を増減
      const zoomFactor = e.deltaY < 0 ? 1.18 : 1 / 1.18;
      const rawNewScale = currentScale * zoomFactor;

      // ズームアウトし切って等倍（1倍）以下になったらズームモードを終了する
      if (rawNewScale <= 1.02 && e.deltaY > 0) {
        isMouseDraggingRef.current = false;
        setIsMouseDragging(false);
        animateZoomTo(1, 0, 0, 220);
        return;
      }

      const newScale = Math.min(Math.max(rawNewScale, 1), 5);
      const cx = window.innerWidth / 2;
      const cy = window.innerHeight / 2;
      const cursorX = e.clientX - cx;
      const cursorY = e.clientY - cy;

      // マウスカーソルの位置を基準に拡大・縮小する
      const scaleRatio = newScale / currentScale;
      const nextPanX = cursorX - (cursorX - zoomStateRef.current.x) * scaleRatio;
      const nextPanY = cursorY - (cursorY - zoomStateRef.current.y) * scaleRatio;

      const clamped = clampPan(nextPanX, nextPanY, newScale);
      rawPanRef.current = { x: clamped.x, y: clamped.y };
      updateZoomState(newScale, clamped.x, clamped.y);
    };

    el.addEventListener("wheel", handleWheel, { passive: false });
    return () => {
      el.removeEventListener("wheel", handleWheel);
    };
  }, [animateZoomTo, clampPan, stopZoomAnimation, updateZoomState]);

  // 閉じるボタンや縦スワイプ時に呼ばれる、アニメーション付きの閉じる関数
  const handleClose = useCallback(() => {
    if (entranceState === 'closing') return;

    // ズーム状態をリセットして縮小アニメーションが自然に行われるようにする
    stopZoomAnimation();
    updateZoomState(1, 0, 0);
    rawPanRef.current = { x: 0, y: 0 };
    isMouseDraggingRef.current = false;
    setIsMouseDragging(false);

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
  }, [selectedImage.id, onClose, entranceState, stopZoomAnimation, updateZoomState]);

  // スワイプと判定する最低移動距離（ピクセル）
  const minSwipeDistance = 50;

  // 完全にスライドしきってから画像を切り替える関数（次へ）
  const executeNext = () => {
    actionQueue.current.push('next');
    processQueue();
  };

  // 完全にスライドしきってから画像を切り替える関数（前へ）
  const executePrev = () => {
    actionQueue.current.push('prev');
    processQueue();
  };

  // キューを順番に消化するエンジン
  const processQueue = useCallback(async () => {
    // アニメーション中、またはキューが空なら何もしない
    if (isProcessingQueue.current || actionQueue.current.length === 0) return;

    isProcessingQueue.current = true;
    // キューの先頭を取り出して削除
    const action = actionQueue.current.shift(); 
    setIsAnimating(true);

    if (action === 'next' && hasSubsequent && onNext) {
      setDragX(-(typeof window !== "undefined" ? window.innerWidth : 1000));
      await new Promise(resolve => setTimeout(resolve, 300));

      setIsAnimating(false);
      onNext();
      setDragX(0);
    } else if (action === 'prev' && hasPreceding && onPrev) {
      setDragX(typeof window !== "undefined" ? window.innerWidth : 1000);
      await new Promise(resolve => setTimeout(resolve, 300));

      setIsAnimating(false);
      onPrev();
      setDragX(0);
    } else {
      setDragX(0);
      await new Promise(resolve => setTimeout(resolve, 300));
      setIsAnimating(false);
    }
    
    isProcessingQueue.current = false;
  }, [hasSubsequent, hasPreceding, onNext, onPrev]);

  // アニメーション終了を検知して次のキューを自動処理する
  useEffect(() => {
    processQueue();
  }, [processQueue, selectedImage.id]);

  // タッチイベントのハンドラー群
  const onTouchStart = (e: React.TouchEvent) => {
    stopZoomAnimation();

    // 2本指が触れた場合はピンチイン・アウト操作を開始
    if (e.touches.length === 2) {
      isPinchingRef.current = true;
      suppressTapRef.current = true;

      // 1本指スワイプの途中だった場合はリセット
      setDragX(0);
      setSwipeDirection(null);
      setTouchStartX(null);
      setTouchStartY(null);

      pinchStartDistRef.current = getTouchDistance(e.touches);
      pinchStartScaleRef.current = zoomStateRef.current.scale;
      pinchStartPanRef.current = { x: zoomStateRef.current.x, y: zoomStateRef.current.y };

      const cx = typeof window !== "undefined" ? window.innerWidth / 2 : 0;
      const cy = typeof window !== "undefined" ? window.innerHeight / 2 : 0;
      pinchStartMidRef.current = {
        x: (e.touches[0].clientX + e.touches[1].clientX) / 2 - cx,
        y: (e.touches[0].clientY + e.touches[1].clientY) / 2 - cy,
      };
      return;
    }

    if (e.touches.length === 1) {
      suppressTapRef.current = false;
      setTouchStartX(e.targetTouches[0].clientX);
      setTouchStartY(e.targetTouches[0].clientY);
      setTouchStartTime(Date.now());

      // ズーム中（1倍超）の場合は1本指ドラッグによるパン移動を準備
      if (zoomStateRef.current.scale > 1) {
        panStartRef.current = { x: rawPanRef.current.x, y: rawPanRef.current.y };
        return;
      }

      // 通常時（1倍）のドラッグ開始の初期化
      if (!isProcessingQueue.current) {
        setIsAnimating(false);
        setDragX(0);
        setSwipeDirection(null);
      }
    }
  };

  const onTouchMove = (e: React.TouchEvent) => {
    // 2本指でのピンチイン・アウト処理
    if (e.touches.length === 2 && pinchStartDistRef.current !== null) {
      const currentDist = getTouchDistance(e.touches);
      const rawScale = pinchStartScaleRef.current * (currentDist / pinchStartDistRef.current);

      // 等倍（1倍）未満に縮小した時は非線形ラバーバンド曲線でなめらかに減衰させる
      let newScale: number;
      if (rawScale < 1) {
        const overshoot = 1 - rawScale;
        const shrink =
          (overshoot * ZOOM_MAX_SHRINK * ZOOM_RUBBER_CONSTANT) /
          (ZOOM_MAX_SHRINK + ZOOM_RUBBER_CONSTANT * overshoot);
        newScale = 1 - shrink;
      } else if (rawScale > 5) {
        const overshoot = rawScale - 5;
        const extra =
          (overshoot * 1.5 * ZOOM_RUBBER_CONSTANT) /
          (1.5 + ZOOM_RUBBER_CONSTANT * overshoot);
        newScale = 5 + extra;
      } else {
        newScale = rawScale;
      }

      const cx = typeof window !== "undefined" ? window.innerWidth / 2 : 0;
      const cy = typeof window !== "undefined" ? window.innerHeight / 2 : 0;
      const currentMidX = (e.touches[0].clientX + e.touches[1].clientX) / 2 - cx;
      const currentMidY = (e.touches[0].clientY + e.touches[1].clientY) / 2 - cy;

      // ピンチ開始時の2本指の中心位置を基準に拡大・移動する
      const scaleRatio = newScale / pinchStartScaleRef.current;
      const nextPanX = currentMidX - (pinchStartMidRef.current.x - pinchStartPanRef.current.x) * scaleRatio;
      const nextPanY = currentMidY - (pinchStartMidRef.current.y - pinchStartPanRef.current.y) * scaleRatio;

      rawPanRef.current = { x: nextPanX, y: nextPanY };

      // 端を超えた分には非線形ラバーバンドを適用する
      const rubberPanned = applyRubberBandPan(nextPanX, nextPanY, newScale);
      updateZoomState(newScale, rubberPanned.x, rubberPanned.y);
      return;
    }

    // ズーム中（1倍超）の1本指ドラッグによるパン（画像内移動）処理
    if (zoomStateRef.current.scale > 1 && e.touches.length === 1) {
      if (touchStartX === null || touchStartY === null) return;
      const currentX = e.targetTouches[0].clientX;
      const currentY = e.targetTouches[0].clientY;
      const diffX = currentX - touchStartX;
      const diffY = currentY - touchStartY;

      if (Math.abs(diffX) > 5 || Math.abs(diffY) > 5) {
        suppressTapRef.current = true;
      }

      const nextRawX = panStartRef.current.x + diffX;
      const nextRawY = panStartRef.current.y + diffY;
      rawPanRef.current = { x: nextRawX, y: nextRawY };

      // 画像の端に到達した後はラバーバンド（バウンス用の抵抗）を効かせながらなめらかに移動させる
      const rubberPanned = applyRubberBandPan(nextRawX, nextRawY, zoomStateRef.current.scale);
      updateZoomState(zoomStateRef.current.scale, rubberPanned.x, rubberPanned.y);
      return;
    }

    // ピンチ操作で1倍以下にした直後（まだ指が画面に残っている間）はスワイプを発火させない
    if (isPinchingRef.current) return;

    if (touchStartX === null || touchStartY === null) return;

    // アニメーション中は指への直接追従をさせない（スライド演出を見せるため）
    if (isAnimating) return;

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
    const currentScale = zoomStateRef.current.scale;
    const currentX = zoomStateRef.current.x;
    const currentY = zoomStateRef.current.y;

    // 2本指から1本指になった瞬間（片方の指だけ離した時）
    if (e.touches.length === 1) {
      pinchStartDistRef.current = null;
      if (currentScale > 1.02 && currentScale <= 5) {
        // 残った1本指の位置を新しいパン開始位置として引き継ぎ、ジャンプを防ぐ
        setTouchStartX(e.touches[0].clientX);
        setTouchStartY(e.touches[0].clientY);
        panStartRef.current = { x: rawPanRef.current.x, y: rawPanRef.current.y };
      } else {
        // 等倍以下または最大倍率超えの状態で片指を離した場合は、残った指での誤移動を防ぎつつバウンス復帰を開始
        setTouchStartX(null);
        setTouchStartY(null);
        if (currentScale <= 1.02) {
          animateZoomTo(1, 0, 0);
        } else {
          const scaledX = currentX * (5 / currentScale);
          const scaledY = currentY * (5 / currentScale);
          const clamped = clampPan(scaledX, scaledY, 5);
          animateZoomTo(5, clamped.x, clamped.y);
        }
      }
      return;
    }

    // ピンチ操作またはズーム中のパン操作が終了した時（すべての指が離れた時）
    if (isPinchingRef.current || currentScale !== 1) {
      pinchStartDistRef.current = null;
      isPinchingRef.current = false;

      if (currentScale <= 1.02) {
        // 等倍を通り越して縮小していた（または1倍付近の）場合は、なめらかに等倍（中央）へバウンス復帰
        animateZoomTo(1, 0, 0);
      } else {
        // 最大倍率（5倍）または画像の端を超えていた場合は、範囲内へなめらかにバウンス復帰
        const targetScale = Math.min(currentScale, 5);
        const adjustedX = targetScale !== currentScale ? currentX * (targetScale / currentScale) : currentX;
        const adjustedY = targetScale !== currentScale ? currentY * (targetScale / currentScale) : currentY;
        const clamped = clampPan(adjustedX, adjustedY, targetScale);
        if (targetScale !== currentScale || clamped.x !== currentX || clamped.y !== currentY) {
          animateZoomTo(targetScale, clamped.x, clamped.y);
        } else {
          rawPanRef.current = { x: currentX, y: currentY };
        }
      }

      setTouchStartX(null);
      setTouchStartY(null);
      setTouchStartTime(null);
      setSwipeDirection(null);
      return;
    }

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
      // アニメーション中の縦スワイプは安全のため無視する
      if (isAnimating) {
        setTouchStartX(null);
        setTouchStartY(null);
        setTouchStartTime(null);
        setSwipeDirection(null);
        return;
      }

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
        // アニメーション中でなければ元の位置に戻す
        if (!isProcessingQueue.current) {
          setIsAnimating(true);
          setDragX(0);
          setTimeout(() => setIsAnimating(false), 300);
        }
      }
    } else {
      // スワイプ距離や速度が足りなかった場合は元の位置に戻る
      if (!isProcessingQueue.current) {
        setIsAnimating(true);
        setDragX(0);
        setTimeout(() => setIsAnimating(false), 300);
      }
    }

    setTouchStartX(null);
    setTouchStartY(null);
    setTouchStartTime(null);
    setSwipeDirection(null);
  };

  // PCでのダブルクリックによるズームモード切り替え処理
  const handleDoubleClick = (e: React.MouseEvent) => {
    e.stopPropagation();

    // ダブルクリック時にシングルクリックのUI表示切り替えが発火しないようキャンセル
    if (tapTimerRef.current) {
      clearTimeout(tapTimerRef.current);
      tapTimerRef.current = null;
    }

    const currentScale = zoomStateRef.current.scale;
    if (currentScale > 1) {
      // すでにズームモード中なら再度ダブルクリックで等倍に戻して終了
      isMouseDraggingRef.current = false;
      setIsMouseDragging(false);
      animateZoomTo(1, 0, 0, 280);
    } else {
      // 等倍の状態でダブルクリックされたら、クリック位置を中心に2倍でズームモードに入る
      const targetScale = 2;
      const cx = typeof window !== "undefined" ? window.innerWidth / 2 : 0;
      const cy = typeof window !== "undefined" ? window.innerHeight / 2 : 0;
      const cursorX = e.clientX - cx;
      const cursorY = e.clientY - cy;

      const nextPanX = -cursorX * (targetScale - 1);
      const nextPanY = -cursorY * (targetScale - 1);
      const clamped = clampPan(nextPanX, nextPanY, targetScale);

      animateZoomTo(targetScale, clamped.x, clamped.y, 280);
    }
  };

  // PCでのマウスホールド（ドラッグ）による座標移動開始
  const onMouseDown = (e: React.MouseEvent) => {
    // 左クリックかつズームモード中（倍率 > 1）のみ有効
    if (e.button !== 0 || zoomStateRef.current.scale <= 1) return;

    e.preventDefault();
    stopZoomAnimation();
    isMouseDraggingRef.current = true;
    setIsMouseDragging(true);
    mouseStartRef.current = { x: e.clientX, y: e.clientY };
    panStartRef.current = { x: rawPanRef.current.x, y: rawPanRef.current.y };
  };

  // PCでのマウスホールド中の座標移動
  const onMouseMove = (e: React.MouseEvent) => {
    if (!isMouseDraggingRef.current || zoomStateRef.current.scale <= 1) return;

    const diffX = e.clientX - mouseStartRef.current.x;
    const diffY = e.clientY - mouseStartRef.current.y;

    if (Math.abs(diffX) > 4 || Math.abs(diffY) > 4) {
      suppressTapRef.current = true;
    }

    const nextRawX = panStartRef.current.x + diffX;
    const nextRawY = panStartRef.current.y + diffY;
    rawPanRef.current = { x: nextRawX, y: nextRawY };

    // 端を超えた場合はラバーバンド減衰を効かせる
    const rubberPanned = applyRubberBandPan(nextRawX, nextRawY, zoomStateRef.current.scale);
    updateZoomState(zoomStateRef.current.scale, rubberPanned.x, rubberPanned.y);
  };

  // PCでのマウスホールド解除時の処理（端を超えていたらバウンス復帰）
  const onMouseUpOrLeave = () => {
    if (!isMouseDraggingRef.current) return;

    isMouseDraggingRef.current = false;
    setIsMouseDragging(false);

    const currentScale = zoomStateRef.current.scale;
    const currentX = zoomStateRef.current.x;
    const currentY = zoomStateRef.current.y;
    const clamped = clampPan(currentX, currentY, currentScale);

    if (clamped.x !== currentX || clamped.y !== currentY) {
      animateZoomTo(currentScale, clamped.x, clamped.y);
    } else {
      rawPanRef.current = { x: currentX, y: currentY };
    }
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

  // 画面の余白や画像のタップでUIを隠す処理
  const handleTap = () => {
    // ピンチ操作やズーム中のドラッグ直後はタップによるUI切り替えを発火させない
    if (suppressTapRef.current) {
      suppressTapRef.current = false;
      return;
    }
    if (isDetailOpen) {
      setIsDetailOpen(false); // パネルが開いていたら閉じるのを優先
      return;
    }
    // ダブルクリック判定と干渉してUIが点滅するのを防ぐため、わずかに遅延させて実行
    if (tapTimerRef.current) {
      clearTimeout(tapTimerRef.current);
    }
    tapTimerRef.current = setTimeout(() => {
      onToggleUI();
      tapTimerRef.current = null;
    }, 220);
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
        ref={viewerContainerRef}
        // アニメーションの状態（scaleとopacity）を制御し、サムネイルの座標を中心に拡大させる
        className={`relative w-full h-full flex flex-col items-center overflow-hidden select-none ${
          entranceState === 'init' || entranceState === 'closing' ? 'scale-50 opacity-0' : 'scale-100 opacity-100'
        } ${
          entranceState !== 'done' ? 'transition-all duration-300 ease-out' : ''
        } ${
          zoomScale > 1 ? (isMouseDragging ? 'cursor-grabbing' : 'cursor-grab') : ''
        }`}
        style={{ transformOrigin }}
        onTouchStart={onTouchStart}
        onTouchMove={onTouchMove}
        onTouchEnd={onTouchEnd}
        onTouchCancel={onTouchEnd}
        onMouseDown={onMouseDown}
        onMouseMove={onMouseMove}
        onMouseUp={onMouseUpOrLeave}
        onMouseLeave={onMouseUpOrLeave}
        onDoubleClick={handleDoubleClick}
        onClick={(e) => {
          e.stopPropagation();
          handleTap();
        }}
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
              <img src={`${API_BASE_URL}/image/${prevImage.id}`} draggable={false} className="max-w-full max-h-full object-contain" alt="Previous" />
            </div>
          )}

          {/* 現在の画像（画面中央に配置） */}
          <div className="w-full h-full flex items-center justify-center overflow-hidden">
            <img 
              ref={currentImgRef}
              src={`${API_BASE_URL}/image/${selectedImage.id}`}
              alt={`Selected ${selectedImage.id}`}
              draggable={false}
              className="max-w-full max-h-full object-contain origin-center will-change-transform"
              style={{
                transform: `translate3d(${panX}px, ${panY}px, 0) scale(${zoomScale})`,
              }}
            />
          </div>

          {/* 次の画像（画面右外に配置） */}
          {nextImage && (
            <div className="absolute -right-full w-full h-full flex items-center justify-center">
              <img src={`${API_BASE_URL}/image/${nextImage.id}`} draggable={false} className="max-w-full max-h-full object-contain" alt="Next" />
            </div>
          )}
        </div>

        {/* 左移動ボタン (PCでのみ表示・ズームモード中はドラッグやダブルクリックを妨げないよう無効化) */}
        {hasPreceding && onPrev && (
          <button
            onClick={(e) => { e.stopPropagation(); executePrev(); }}
            className={`absolute left-0 top-0 bottom-0 w-1/4 z-10 hidden md:flex items-center justify-start pl-4 outline-none group cursor-pointer transition-opacity duration-300 ${
              isUIVisible && entranceState !== 'closing' && zoomScale <= 1 ? 'opacity-100' : 'opacity-0 pointer-events-none'
            }`}
          >
            {/* アイコンの背景の丸い部分を div に分離し、group-hover で反応させる */}
            <div className="p-4 bg-black/50 group-hover:bg-black/80 text-white rounded-full transition-colors flex items-center justify-center">
              <ChevronLeft size={32} />
            </div>
          </button>
        )}

        {/* 右移動ボタン (PCでのみ表示・ズームモード中はドラッグやダブルクリックを妨げないよう無効化) */}
        {hasSubsequent && onNext && (
          <button
            onClick={(e) => { e.stopPropagation(); executeNext(); }}
            className={`absolute right-0 top-0 bottom-0 w-1/4 z-10 hidden md:flex items-center justify-end pr-4 outline-none group cursor-pointer transition-opacity duration-300 ${
              isUIVisible && entranceState !== 'closing' && zoomScale <= 1 ? 'opacity-100' : 'opacity-0 pointer-events-none'
            }`}
          >
            {/* アイコンの背景部分 */}
            <div className="p-4 bg-black/50 group-hover:bg-black/80 text-white rounded-full transition-colors flex items-center justify-center">
              <ChevronRight size={32} />
            </div>
          </button>
        )}

        {/* お気に入り（ハート）ボタン */}
        <button
          onClick={(e) => { e.stopPropagation(); onToggleFavorite(selectedImage.id, e); }}
          // 外側の button: 見た目の位置（左・下パディング）は維持しつつ、上・右に透明な大きなパディングを持たせて左下カドの広範囲を当たり判定にする
          className={`absolute bottom-0 left-0 pb-4 pl-4 pt-12 pr-12 sm:pb-6 sm:pl-6 sm:pt-16 sm:pr-16 z-20 group cursor-pointer outline-none transition-all duration-300 ease-out ${
            isUIVisible && entranceState !== 'closing' ? 'translate-y-0 opacity-100' : 'translate-y-12 opacity-0 pointer-events-none'
          }`}
        >
          {/* 内側の div: 実際の見た目 */}
          <div className="p-3 bg-black/50 text-white group-hover:bg-black/80 rounded-full transition-colors flex items-center justify-center shadow-lg">
            <Heart 
              size={26} 
              className={selectedImage.is_favorite === 1 ? "fill-red-500 text-red-500" : "text-white"} 
            />
          </div>
        </button>

        {/* 類似画像検索ボタン */}
        <button
          onClick={(e) => { 
            e.stopPropagation();
            if (onSearchSimilar) {
              onSearchSimilar(selectedImage);
            }
          }}
          // 外側の button: 透明な大きなパディングを持たせ、画面の右下カドの広範囲を当たり判定にする
          className={`absolute bottom-0 right-0 p-4 sm:p-6 z-20 outline-none transition-all duration-300 ease-out ${
            isUIVisible && entranceState !== 'closing' ? 'translate-y-0 opacity-100' : 'translate-y-12 opacity-0 pointer-events-none'
          }`}
          title="類似画像（同じ髪色）を検索"
        >
          {/* 内側の div: 実際の見た目 */}
          <div className="p-3 bg-black/50 text-white hover:bg-black/80 rounded-full transition-colors flex items-center justify-center shadow-lg gap-2">
            <Search size={22} />
            <span className="text-sm font-medium pr-1 hidden sm:inline">類似画像</span>
          </div>
        </button>

        {/* 閉じるボタン */}
        <button 
          onClick={(e) => { e.stopPropagation(); handleClose(); }}
          // 外側の button: 画面の右上カドの広範囲を当たり判定にする
          className={`absolute top-0 right-0 p-4 sm:p-6 z-20 outline-none transition-all duration-300 ease-out ${
            isUIVisible && entranceState !== 'closing' ? 'translate-y-0 opacity-100' : '-translate-y-12 opacity-0 pointer-events-none'
          }`}
        >
          {/* 内側の div: 実際の見た目 */}
          <div className="p-3 bg-black/50 text-white group-hover:bg-black/80 rounded-full transition-colors flex items-center justify-center shadow-lg">
            <X size={26} />
          </div>
        </button>

        {/* 詳細情報パネル */}
        <div
          className={`absolute bottom-0 left-0 right-0 max-h-[50%] overflow-y-auto overscroll-contain bg-zinc-900/95 backdrop-blur-md border-t border-zinc-700 text-white p-6 rounded-t-2xl transition-transform duration-300 ease-out flex flex-col gap-2 z-30 shadow-2xl ${
            isDetailOpen ? "translate-y-0" : "translate-y-full"
          }`}
          // パネル内の操作が後ろに抜けないようにする
          onClick={(e) => e.stopPropagation()} 
          onTouchStart={(e) => e.stopPropagation()}
          onTouchMove={(e) => e.stopPropagation()}
          onTouchEnd={(e) => e.stopPropagation()}
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
