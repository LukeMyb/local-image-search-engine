import { useEffect } from "react";

interface UseSystemUIProps {
  selectedImage: any;
  isDrawerOpen: boolean;
}

/**
 * PWAとしての挙動やブラウザのシステム制御（ズーム禁止・スクロールロック）を管理するカスタムフック
 */
export function useSystemUI({ selectedImage, isDrawerOpen }: UseSystemUIProps) {
  // iOSの強制ズーム（ピンチ＆ダブルタップ）をJavaScriptで完全にブロックする
  useEffect(() => {
    const handleTouchMove = (e: TouchEvent) => {
      // 2本指以上の操作（ピンチ）を制限
      if (e.touches.length > 1) {
        e.preventDefault();
      }
    };

    let lastTouchEnd = 0;
    const handleTouchEnd = (e: TouchEvent) => {
      const now = new Date().getTime();
      // 300ms以内の連続タップ（ダブルタップズーム）を制限
      if (now - lastTouchEnd <= 300) {
        e.preventDefault();
      }
      lastTouchEnd = now;
    };

    // イベントリスナーを登録（passive: false にすることで preventDefault が効くようになる）
    document.addEventListener("touchmove", handleTouchMove, { passive: false });
    document.addEventListener("touchend", handleTouchEnd, { passive: false });

    return () => {
      // クリーンアップ関数（アプリ終了時や画面移動時にイベントを解除する）
      document.removeEventListener("touchmove", handleTouchMove);
      document.removeEventListener("touchend", handleTouchEnd);
    };
  }, []); // <- 空の配列にすることで、アプリ起動時に1回だけ実行される

  // モーダルやドロワーの開閉に合わせて背景のスクロールを制御する
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
}