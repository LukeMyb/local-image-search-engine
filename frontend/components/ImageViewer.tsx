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

  // ピンチイン・アウトによるズーム倍率とパン（移動量）を管理するState
  const [zoomScale, setZoomScale] = useState(1);
  const [panX, setPanX] = useState(0);
  const [panY, setPanY] = useState(0);
  const [isZoomAnimating, setIsZoomAnimating] = useState(false);

  // 現在の画像DOMへの参照（パン範囲の制限計算に使用）
  const currentImgRef = useRef<HTMLImageElement>(null);

  // ピンチ・パン計算用のRef
  const pinchStartDistRef = useRef<number | null>(null);
  const pinchStartScaleRef = useRef<number>(1);
  const pinchStartPanRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const pinchStartMidRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const panStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 });
  const zoomBounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const isPinchingRef = useRef(false);
  const suppressTapRef = useRef(false);

  // 実行待ちのスワイプ操作を貯めておくキュー（レンダリングに影響を与えないようRefを使用）
  const actionQueue = useRef<('next' | 'prev')[]>([]);
  // アニメーションの重複やタップによる干渉を防ぐためのロック用フラグ
  const isProcessingQueue = useRef(false);

  // バウンス（ラバーバンド）の減衰係数
  const PAN_RUBBER_FACTOR = 0.3;
  const ZOOM_RUBBER_FACTOR = 0.35;
  const MIN_BOUNCE_SCALE = 0.65;

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

  // 端を超えた移動に対してラバーバンド（抵抗感）をかけて少しだけはみ出させる関数
  const applyRubberBandPan = useCallback((nextPanX: number, nextPanY: number, scale: number) => {
    const { maxPanX, maxPanY } = getPanBounds(scale);

    const rubberBand = (val: number, max: number) => {
      if (val > max) return max + (val - max) * PAN_RUBBER_FACTOR;
      if (val < -max) return -max + (val + max) * PAN_RUBBER_FACTOR;
      return val;
    };

    return {
      x: rubberBand(nextPanX, maxPanX),
      y: rubberBand(nextPanY, maxPanY),
    };
  }, [getPanBounds]);

  // ラバーバンド適用済みの座標から、元のドラッグ基準座標を逆算する関数（指の切り替え時のジャンプ防止用）
  const invertRubberBandPan = useCallback((currentPanX: number, currentPanY: number, scale: number) => {
    const { maxPanX, maxPanY } = getPanBounds(scale);

    const invert = (val: number, max: number) => {
      if (val > max) return max + (val - max) / PAN_RUBBER_FACTOR;
      if (val < -max) return -max + (val + max) / PAN_RUBBER_FACTOR;
      return val;
    };

    return {
      x: invert(currentPanX, maxPanX),
      y: invert(currentPanY, maxPanY),
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
  }, []); // 空配列なので「一覧から開いた最初の1回」だけ実行される

  // 画像が切り替わった時は、パネルを閉じ、ドラッグ位置・ズーム状態もリセットする
  useEffect(() => {
    if (zoomBounceTimerRef.current) {
      clearTimeout(zoomBounceTimerRef.current);
      zoomBounceTimerRef.current = null;
    }
    setIsDetailOpen(false);
    setDragX(0);
    setSwipeDirection(null);
    setZoomScale(1);
    setPanX(0);
    setPanY(0);
    setIsZoomAnimating(false);
    pinchStartDistRef.current = null;
    isPinchingRef.current = false;
  }, [selectedImage.id]);

  // 閉じるボタンや縦スワイプ時に呼ばれる、アニメーション付きの閉じる関数
  const handleClose = useCallback(() => {
    if (entranceState === 'closing') return;

    // ズーム状態をリセットして縮小アニメーションが自然に行われるようにする
    setZoomScale(1);
    setPanX(0);
    setPanY(0);

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
    if (zoomBounceTimerRef.current) {
      clearTimeout(zoomBounceTimerRef.current);
      zoomBounceTimerRef.current = null;
    }

    // 2本指が触れた場合はピンチイン・アウト操作を開始
    if (e.touches.length === 2) {
      isPinchingRef.current = true;
      suppressTapRef.current = true;
      setIsZoomAnimating(false);

      // 1本指スワイプの途中だった場合はリセット
      setDragX(0);
      setSwipeDirection(null);
      setTouchStartX(null);
      setTouchStartY(null);

      pinchStartDistRef.current = getTouchDistance(e.touches);
      pinchStartScaleRef.current = zoomScale;
      pinchStartPanRef.current = { x: panX, y: panY };

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
      if (zoomScale > 1) {
        setIsZoomAnimating(false);
        panStartRef.current = invertRubberBandPan(panX, panY, zoomScale);
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

      // 等倍（1倍）未満に縮小した時はラバーバンド（抵抗感）をかけて少しだけ等倍を通り越させる
      let newScale: number;
      if (rawScale < 1) {
        newScale = Math.max(MIN_BOUNCE_SCALE, 1 - (1 - rawScale) * ZOOM_RUBBER_FACTOR);
      } else {
        newScale = Math.min(rawScale, 5);
      }

      const cx = typeof window !== "undefined" ? window.innerWidth / 2 : 0;
      const cy = typeof window !== "undefined" ? window.innerHeight / 2 : 0;
      const currentMidX = (e.touches[0].clientX + e.touches[1].clientX) / 2 - cx;
      const currentMidY = (e.touches[0].clientY + e.touches[1].clientY) / 2 - cy;

      // ピンチ開始時の2本指の中心位置を基準に拡大・移動する
      const scaleRatio = newScale / pinchStartScaleRef.current;
      const nextPanX = currentMidX - (pinchStartMidRef.current.x - pinchStartPanRef.current.x) * scaleRatio;
      const nextPanY = currentMidY - (pinchStartMidRef.current.y - pinchStartPanRef.current.y) * scaleRatio;

      // 端を超えた分にはラバーバンドを適用する
      const rubberPanned = applyRubberBandPan(nextPanX, nextPanY, newScale);
      setZoomScale(newScale);
      setPanX(rubberPanned.x);
      setPanY(rubberPanned.y);
      return;
    }

    // ズーム中（1倍超）の1本指ドラッグによるパン（画像内移動）処理
    if (zoomScale > 1 && e.touches.length === 1) {
      if (touchStartX === null || touchStartY === null) return;
      const currentX = e.targetTouches[0].clientX;
      const currentY = e.targetTouches[0].clientY;
      const diffX = currentX - touchStartX;
      const diffY = currentY - touchStartY;

      if (Math.abs(diffX) > 5 || Math.abs(diffY) > 5) {
        suppressTapRef.current = true;
      }

      // 画像の端に到達した後はラバーバンド（バウンス用の抵抗）を効かせながら少し移動させる
      const rubberPanned = applyRubberBandPan(
        panStartRef.current.x + diffX,
        panStartRef.current.y + diffY,
        zoomScale
      );
      setPanX(rubberPanned.x);
      setPanY(rubberPanned.y);
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
    // 2本指から1本指になった瞬間（片方の指だけ離した時）
    if (e.touches.length === 1) {
      pinchStartDistRef.current = null;
      if (zoomScale > 1.02) {
        // 残った1本指の位置を新しいパン開始位置として引き継ぎ、ジャンプを防ぐ
        setTouchStartX(e.touches[0].clientX);
        setTouchStartY(e.touches[0].clientY);
        panStartRef.current = invertRubberBandPan(panX, panY, zoomScale);
      } else {
        // 等倍以下まで縮小して片指を離した場合は、なめらかに等倍へバウンス復帰させる
        setTouchStartX(null);
        setTouchStartY(null);
        setIsZoomAnimating(true);
        setZoomScale(1);
        setPanX(0);
        setPanY(0);
        zoomBounceTimerRef.current = setTimeout(() => {
          setIsZoomAnimating(false);
          zoomBounceTimerRef.current = null;
        }, 300);
      }
      return;
    }

    // ピンチ操作またはズーム中のパン操作が終了した時（すべての指が離れた時）
    if (isPinchingRef.current || zoomScale !== 1 || panX !== 0 || panY !== 0) {
      // 通常のスワイプ操作中（zoomScale === 1 かつ dragX による移動中）は下の通常スワイプ判定へ流す
      if (isPinchingRef.current || zoomScale !== 1) {
        pinchStartDistRef.current = null;
        isPinchingRef.current = false;

        if (zoomScale <= 1.02) {
          // 等倍を通り越して縮小していた（または1倍付近の）場合は、なめらかに等倍（中央）へバウンス復帰
          setIsZoomAnimating(true);
          setZoomScale(1);
          setPanX(0);
          setPanY(0);
          zoomBounceTimerRef.current = setTimeout(() => {
            setIsZoomAnimating(false);
            zoomBounceTimerRef.current = null;
          }, 300);
        } else {
          // 拡大中に画像の端を超えてドラッグしていた場合は、端の位置へなめらかにバウンス復帰
          const clamped = clampPan(panX, panY, zoomScale);
          if (clamped.x !== panX || clamped.y !== panY) {
            setIsZoomAnimating(true);
            setPanX(clamped.x);
            setPanY(clamped.y);
            zoomBounceTimerRef.current = setTimeout(() => {
              setIsZoomAnimating(false);
              zoomBounceTimerRef.current = null;
            }, 300);
          }
        }

        setTouchStartX(null);
        setTouchStartY(null);
        setTouchStartTime(null);
        setSwipeDirection(null);
        return;
      }
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
    } else {
      onToggleUI(); // パネルが閉じていればUIの出し入れを切り替え
    }
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
        onTouchCancel={onTouchEnd}
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
              <img src={`${API_BASE_URL}/image/${prevImage.id}`} className="max-w-full max-h-full object-contain" alt="Previous" />
            </div>
          )}

          {/* 現在の画像（画面中央に配置） */}
          <div className="w-full h-full flex items-center justify-center overflow-hidden">
            <img 
              ref={currentImgRef}
              src={`${API_BASE_URL}/image/${selectedImage.id}`}
              alt={`Selected ${selectedImage.id}`}
              className={`max-w-full max-h-full object-contain origin-center ${
                isZoomAnimating ? "transition-transform duration-300 ease-out" : ""
              }`}
              style={{
                transform: `translate3d(${panX}px, ${panY}px, 0) scale(${zoomScale})`,
              }}
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
            className={`absolute left-0 top-0 bottom-0 w-1/4 z-10 hidden md:flex items-center justify-start pl-4 outline-none group cursor-pointer transition-opacity duration-300 ${
              isUIVisible && entranceState !== 'closing' ? 'opacity-100' : 'opacity-0 pointer-events-none'
            }`}
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
            className={`absolute right-0 top-0 bottom-0 w-1/4 z-10 hidden md:flex items-center justify-end pr-4 outline-none group cursor-pointer transition-opacity duration-300 ${
              isUIVisible && entranceState !== 'closing' ? 'opacity-100' : 'opacity-0 pointer-events-none'
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
