import { Heart } from "lucide-react";

// 検索結果のデータ構造を定義
interface SearchResult {
  id: number;
  is_favorite?: number;
}

interface ImageGridProps {
  results: SearchResult[];
  setSelectedImage: (item: SearchResult) => void;
}

export default function ImageGrid({ results, setSelectedImage }: ImageGridProps) {
  return (
    <div className="grid grid-cols-3 gap-2 md:grid-cols-6 md:gap-4 mt-4">
      {results.map((item) => (
        // 画像とボタンを重ねるため、relative を持った div で囲む
        <div key={item.id} className="relative group">
          <img
            key={item.id}
            // Python側の画像のエンドポイントを呼び出し
            src={`http://192.168.11.3:8000/thumbnail/${item.id}`}
            alt={`Image ${item.id}`}
            // クリックされたら、この画像の情報を selectedImage にセットする
            onClick={() => setSelectedImage(item)}
            // カーソルを指マーク(cursor-pointer)にし、クリックできることを強調
            className="w-full aspect-square object-cover rounded-md cursor-pointer hover:opacity-80 transition-opacity"
          />

          {/* 右上に配置されるお気に入りマーク */}
          {item.is_favorite === 1 && (
            <div className="absolute bottom-1 right-1 p-1 md:p-2 pointer-events-none">
              <Heart className="w-5 h-5 md:w-6 md:h-6 fill-white text-white drop-shadow-[0_0_8px_rgba(0,0,0,0.8)]"/>
            </div>
          )}
        </div>
      ))}
    </div>
  );
}