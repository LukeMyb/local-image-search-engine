import { useRef, useEffect } from "react";
import { Heart } from "lucide-react";
import { API_BASE_URL } from "../lib/config";

// 検索結果のデータ構造を定義
interface SearchResult {
  id: number;
  is_favorite?: number;
}

interface ImageGridProps {
  results: SearchResult[];
  selectedImage: SearchResult | null;
  setSelectedImage: (item: SearchResult) => void;

  // 無限スクロール用の関数と判定フラグ
  loadMore?: () => void;
  hasMore?: boolean;
}

export default function ImageGrid({ 
  results, 
  selectedImage,
  setSelectedImage,
  loadMore,
  hasMore
}: ImageGridProps) {

  // 監視対象（一番下の透明な要素）への参照
  const observerTarget = useRef<HTMLDivElement>(null);

  // 最後に表示していた画像のIDを記憶しておくための変数
  const lastSelectedId = useRef<number | null>(null);

  // ビューアが閉じた瞬間に、見ていた画像の位置へスクロールする処理
  useEffect(() => {
    if (selectedImage) {
      // ビューアが開いている間は、スワイプされるたびに「今見ているID」を上書き記憶する
      lastSelectedId.current = selectedImage.id;
    } else if (lastSelectedId.current) {
      // ビューアが閉じた瞬間（selectedImageがnullになった時）
      const idToScroll = lastSelectedId.current;
      
      // システムのスクロールロック解除が終わった瞬間瞬時に実行
      setTimeout(() => {
        const el = document.getElementById(`grid-image-${idToScroll}`);
        if (el) {
          // 画面内に見えている場合は動かず、画面外にある場合のみ一番近い端にスクロール
          el.scrollIntoView({ block: "nearest", behavior: "auto" });
        }
      }, 0);

      // スクロールが終わったら記憶をリセット
      lastSelectedId.current = null;
    }
  }, [selectedImage]);

  // スクロール検知ロジック
  useEffect(() => {
    const observer = new IntersectionObserver(
      (entries) => {
        // 目印が画面に入ってきて、かつまだ続きがある場合にロードを発火
        if (entries[0].isIntersecting && hasMore && loadMore) {
          loadMore();
        }
      },
      // 画面の下端から200px手前（見えない位置）で早めに発火させる
      { rootMargin: "200px" }
    );

    if (observerTarget.current) {
      observer.observe(observerTarget.current);
    }

    return () => {
      if (observerTarget.current) {
        observer.unobserve(observerTarget.current);
      }
    };
  }, [hasMore, loadMore]);

  return (
    <>
      <div className="grid grid-cols-3 gap-2 md:grid-cols-6 md:gap-4 mt-4">
        {results.map((item) => (
          // 画像とボタンを重ねるため、relative を持った div で囲む
          <div key={item.id} className="relative group">
            <img
              key={item.id}
              id={`grid-image-${item.id}`} // スクロールのジャンプ先となる目印（ID）を付ける
              // Python側の画像のエンドポイントを呼び出し
              src={`${API_BASE_URL}/thumbnail/${item.id}`}
              alt={`Image ${item.id}`}
              // クリックされたら、この画像の情報を selectedImage にセットする
              onClick={() => setSelectedImage(item)}
              // カーソルを指マーク(cursor-pointer)にし、クリックできることを強調
              className="relative group scroll-mt-0 md:scroll-mt-24"
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

      {/* 無限スクロールの検知用タグ（この透明な箱が画面に入ったら次を読み込む） */}
      <div ref={observerTarget} className="h-4 w-full" />
    </>
  );
}