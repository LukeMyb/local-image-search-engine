import { useEffect } from "react";
import { X, Settings, ChevronDown } from "lucide-react";

const IDLE_TIMEOUT_OPTIONS = [
  { label: "1分", value: 60 },
  { label: "3分", value: 180 },
  { label: "5分 (標準)", value: 300 },
  { label: "10分", value: 600 },
  { label: "30分", value: 1800 },
  { label: "自動停止しない", value: 0 },
];

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  confirmTrashInViewer: boolean;
  onChangeConfirmTrashInViewer: (enabled: boolean) => void;
  heavyIdleTimeout: number;
  onChangeHeavyIdleTimeout: (seconds: number) => void;
}

export default function SettingsModal({
  isOpen,
  onClose,
  confirmTrashInViewer,
  onChangeConfirmTrashInViewer,
  heavyIdleTimeout,
  onChangeHeavyIdleTimeout,
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

          <hr className="border-zinc-800" />

          {/* 2. 重量モードの自動停止タイムアウト時間 */}
          <div className="flex items-center justify-between gap-4">
            <div className="flex flex-col gap-1">
              <span className="font-medium text-white">
                重量モードの自動停止時間
              </span>
              <span className="text-xs text-zinc-400 leading-relaxed">
                画面を閉じるか非表示にしてから一定時間が経過すると、自動で軽量モードに戻りメモリ（RAM・VRAM）を解放します。
              </span>
            </div>

            <div className="relative shrink-0">
              <select
                value={heavyIdleTimeout}
                onChange={(e) => onChangeHeavyIdleTimeout(Number(e.target.value))}
                className="appearance-none bg-zinc-800 hover:bg-zinc-700/80 border border-zinc-700 text-zinc-100 text-xs font-medium rounded-lg pl-3 pr-8 py-2 focus:outline-none focus:ring-2 focus:ring-blue-600 transition-colors cursor-pointer"
              >
                {IDLE_TIMEOUT_OPTIONS.map((opt) => (
                  <option key={opt.value} value={opt.value} className="bg-zinc-800 text-zinc-100">
                    {opt.label}
                  </option>
                ))}
              </select>
              <ChevronDown
                size={14}
                className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-400"
              />
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
