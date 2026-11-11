import { useEffect } from "react";
import { X, Settings } from "lucide-react";

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  confirmTrashInViewer: boolean;
  onChangeConfirmTrashInViewer: (enabled: boolean) => void;
}

export default function SettingsModal({
  isOpen,
  onClose,
  confirmTrashInViewer,
  onChangeConfirmTrashInViewer,
}: SettingsModalProps) {
  // Escキーでモーダルを閉じる処理
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        onClose();
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* 背景の半透明オーバーレイ（クリックで閉じる） */}
      <div
        className="absolute inset-0 bg-black/60 backdrop-blur-sm"
        onClick={onClose}
      />

      {/* モーダル本体 */}
      <div className="relative bg-zinc-900 border border-zinc-800 rounded-2xl shadow-2xl w-full max-w-md overflow-hidden flex flex-col max-h-[85vh]">
        {/* ヘッダー */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800">
          <div className="flex items-center gap-2 text-white">
            <Settings size={18} className="text-zinc-400" />
            <h2 className="text-base font-bold">設定</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="p-1.5 text-zinc-400 hover:text-white hover:bg-zinc-800 rounded-full transition-colors cursor-pointer"
            title="閉じる"
          >
            <X size={18} />
          </button>
        </div>

        {/* 設定項目リスト領域 */}
        <div className="p-6 overflow-y-auto flex flex-col gap-6 text-sm text-zinc-300">
          {/* 1. ビューアーでの削除時の確認ダイアログ ON/OFF */}
          <div className="flex items-center justify-between gap-4">
            <div className="flex flex-col gap-1">
              <span className="font-medium text-white">
                ゴミ箱移動時の確認ダイアログ
              </span>
              <span className="text-xs text-zinc-400 leading-relaxed">
                ビューアーで画像をゴミ箱へ移動する際、確認ポップアップを表示します。OFFにするとワンタップで即座に移動します。
              </span>
            </div>

            <button
              type="button"
              role="switch"
              aria-checked={confirmTrashInViewer}
              onClick={() => onChangeConfirmTrashInViewer(!confirmTrashInViewer)}
              className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out outline-none ${
                confirmTrashInViewer ? "bg-blue-600" : "bg-zinc-700"
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-md transform transition duration-200 ease-in-out ${
                  confirmTrashInViewer ? "translate-x-5" : "translate-x-0"
                }`}
              />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
