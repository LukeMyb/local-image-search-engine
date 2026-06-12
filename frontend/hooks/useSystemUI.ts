import { useEffect } from "react";

interface UseSystemUIProps {
  selectedImage: any;
  isDrawerOpen: boolean;
}

/**
 * PWAとしての挙動やブラウザのシステム制御（ズーム禁止・スクロールロック）を管理するカスタムフック
 */
export function useSystemUI({ selectedImage, isDrawerOpen }: UseSystemUIProps) {
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