import { X, Heart } from "lucide-react";

// 検索結果のデータ構造を定義
interface SearchResult {
  id: number;
  is_favorite?: number;
}

interface ImageViewerProps {
  selectedImage: SearchResult;
  onClose: () => void;
  onToggleFavorite: (id: number, e: React.MouseEvent) => void;
}

export default function ImageViewer({ selectedImage, onClose, onToggleFavorite }: ImageViewerProps) {
  return (
    <div 
      // 画面全体を覆う半透明の黒い背景
      className="fixed inset-0 bg-black flex items-center justify-center z-50 touch-none overscroll-none"
    >
      {/* 画像を中央に配置するコンテナ */}
      <div className="relative w-full h-full flex flex-col items-center">
        <img 
          // 本画像(/image/)を呼び出す
          src={`http://192.168.11.3:8000/image/${selectedImage.id}`} 
          alt={`Selected ${selectedImage.id}`}
          className="w-full h-full object-contain"
        />

        {/* モーダル内のボタン */}
        <button
          onClick={(e) => onToggleFavorite(selectedImage.id, e)}
          className="absolute bottom-4 left-4 p-2 bg-black/50 rounded-full text-white hover:bg-black/80 transition-colors"
        >
          <Heart 
            size={24} 
            className={selectedImage.is_favorite === 1 ? "fill-red-500 text-red-500" : "text-white"} 
          />
        </button>
        
        <button 
          // 閉じる処理をpropsで受け取った関数に置き換え
          onClick={onClose}
          className="absolute top-4 right-4 p-2 bg-black/50 text-white hover:bg-black/80 rounded-full transition-colors"
        >
          <X size={24} />
        </button>
      </div>
    </div>
  );
}