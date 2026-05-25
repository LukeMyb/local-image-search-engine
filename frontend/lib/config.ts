export const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL;

// 環境変数が設定されていない場合は、あえてエラーを出して明確に知らせる
if (!API_BASE_URL) {
  throw new Error("環境変数 NEXT_PUBLIC_API_URL が設定されていません。.env.local を確認してください。");
}