import { useEffect } from "react";
import { X, Settings, ChevronDown, RotateCcw } from "lucide-react";

const IDLE_TIMEOUT_OPTIONS = [
  { label: "1分", value: 60 },
  { label: "3分", value: 180 },
  { label: "5分 (標準)", value: 300 },
  { label: "10分", value: 600 },
  { label: "30分", value: 1800 },
  { label: "自動停止しない", value: 0 },
];

export const DEFAULT_STYLE_THRESHOLD = 0.98;

interface SettingsModalProps {
  isOpen: boolean;
  onClose: () => void;
  showSearchButton: boolean;
  onChangeShowSearchButton: (enabled: boolean) => void;
  confirmTrashInViewer: boolean;
  onChangeConfirmTrashInViewer: (enabled: boolean) => void;
  heavyIdleTimeout: number;
  onChangeHeavyIdleTimeout: (seconds: number) => void;
  styleThreshold: number;
  onChangeStyleThreshold: (value: number) => void;
  onCommitStyleThreshold: (value: number) => void;
}

export default function SettingsModal({
  isOpen,
  onClose,
  showSearchButton,
  onChangeShowSearchButton,
  confirmTrashInViewer,
  onChangeConfirmTrashInViewer,
  heavyIdleTimeout,
  onChangeHeavyIdleTimeout,
  styleThreshold,
  onChangeStyleThreshold,
  onCommitStyleThreshold,
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

  const isDefaultThreshold = Math.abs(styleThreshold - DEFAULT_STYLE_THRESHOLD) < 0.0005;

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
          {/* 1. 検索ボタンの表示 / 非表示 */}
          <div className="flex items-center justify-between gap-4">
            <div className="flex flex-col gap-1">
              <span className="font-medium text-white">
                検索ボタンの表示
              </span>
              <span className="text-xs text-zinc-400 leading-relaxed">
                検索窓の右隣にある検索（虫眼鏡）ボタンを表示します。OFFにしてもEnterキー（スマホの検索キー）で検索できます。
              </span>
            </div>

            <button
              type="button"
              role="switch"
              aria-checked={showSearchButton}
              onClick={() => onChangeShowSearchButton(!showSearchButton)}
              className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out outline-none ${
                showSearchButton ? "bg-blue-600" : "bg-zinc-700"
              }`}
            >
              <span
                className={`pointer-events-none inline-block h-5 w-5 rounded-full bg-white shadow-md transform transition duration-200 ease-in-out ${
                  showSearchButton ? "translate-x-5" : "translate-x-0"
                }`}
              />
            </button>
          </div>

          <hr className="border-zinc-800" />

          {/* 2. ビューアーでの削除時の確認ダイアログ ON/OFF */}
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

          {/* 3. 重量モードの自動停止タイムアウト時間 */}
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

          <hr className="border-zinc-800" />

          {/* 4. 絵柄検索の類似度しきい値 */}
          <div className="flex flex-col gap-3">
            <div className="flex items-center justify-between gap-2">
              <span className="font-medium text-white">
                絵柄検索の類似度しきい値
              </span>

              <div className="flex items-center gap-2">
                {!isDefaultThreshold && (
                  <button
                    type="button"
                    onClick={() => {
                      onChangeStyleThreshold(DEFAULT_STYLE_THRESHOLD);
                      onCommitStyleThreshold(DEFAULT_STYLE_THRESHOLD);
                    }}
                    className="flex items-center gap-1 px-2 py-1 rounded-md text-xs text-zinc-400 hover:text-white hover:bg-zinc-800 transition-colors cursor-pointer"
                    title="標準値 (0.980) に戻す"
                  >
                    <RotateCcw size={12} />
                    <span>標準に戻す</span>
                  </button>
                )}
                <span className="px-2.5 py-1 rounded-md bg-zinc-800 border border-zinc-700 text-blue-300 font-mono text-xs font-bold">
                  {styleThreshold.toFixed(3)}
                </span>
              </div>
            </div>

            <span className="text-xs text-zinc-400 leading-relaxed">
              絵柄検索（<code className="text-zinc-300">style:</code>）でヒットさせる類似度の足切りラインです。数値を下げるとヒット件数が増え、上げるとより厳選されます。
            </span>

            <div className="flex flex-col gap-1.5 pt-1">
              <input
                type="range"
                min={0.97}
                max={0.99}
                step={0.001}
                value={styleThreshold}
                onChange={(e) => onChangeStyleThreshold(parseFloat(e.target.value))}
                onPointerUp={(e) =>
                  onCommitStyleThreshold(parseFloat((e.target as HTMLInputElement).value))
                }
                onKeyUp={(e) =>
                  onCommitStyleThreshold(parseFloat((e.target as HTMLInputElement).value))
                }
                className="w-full h-2 bg-zinc-700 rounded-lg appearance-none cursor-pointer accent-blue-500"
              />
              <div className="flex justify-between text-[11px] text-zinc-500 font-mono">
                <span>0.970 (広め)</span>
                <span>0.980 (標準)</span>
                <span>0.990 (厳しめ)</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
