import { useEffect } from "react";

interface UseDrawerSwipeProps {
  isDrawerOpen: boolean;
  setIsDrawerOpen: (open: boolean) => void;
  // 画像ビューワー展開中かどうかを判定するために受け取る
  selectedImage: any;
}

/**
 * 画面左端からの右スワイプを検知してドロワーを開くカスタムフック
 */
export function useDrawerSwipe({ isDrawerOpen, setIsDrawerOpen, selectedImage }: UseDrawerSwipeProps) {
  useEffect(() => {
    // 画像ビューワーが開いている時や、すでにドロワーが開いている時はイベントを登録しない
    if (selectedImage || isDrawerOpen) return;

    const EDGE_SWIPE_THRESHOLD = 40; // 左端から40px以内
    const MIN_SWIPE_DISTANCE = 50;   // 50px以上の移動で判定

    let startX: number | null = null;
    let endX: number | null = null;

    const handleTouchStart = (e: TouchEvent) => {
      const touchX = e.targetTouches[0].clientX;
      if (touchX <= EDGE_SWIPE_THRESHOLD) {
        startX = touchX;
        endX = null;
      } else {
        startX = null;
      }
    };

    const handleTouchMove = (e: TouchEvent) => {
      if (startX === null) return;
      endX = e.targetTouches[0].clientX;
    };

    const handleTouchEnd = () => {
      if (startX === null || endX === null) return;

      const distance = endX - startX;
      if (distance >= MIN_SWIPE_DISTANCE) {
        setIsDrawerOpen(true);
      }

      // 判定後にリセット
      startX = null;
      endX = null;
    };

    // document全体でタッチイベントを監視
    document.addEventListener("touchstart", handleTouchStart);
    document.addEventListener("touchmove", handleTouchMove);
    document.addEventListener("touchend", handleTouchEnd);

    return () => {
      document.removeEventListener("touchstart", handleTouchStart);
      document.removeEventListener("touchmove", handleTouchMove);
      document.removeEventListener("touchend", handleTouchEnd);
    };
  }, [isDrawerOpen, setIsDrawerOpen, selectedImage]);
}