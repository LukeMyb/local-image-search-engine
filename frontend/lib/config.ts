// 環境変数を読み込み、万が一読み込めなかった場合のフォールバックも設定
export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://192.168.11.3:8000";