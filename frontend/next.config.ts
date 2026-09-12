import type { NextConfig } from "next";
import fs from "fs";
import path from "path";

// プロジェクト直下の .env を読み込む
const envPath = path.join(process.cwd(), "..", ".env");
if (fs.existsSync(envPath)) {
  const envContent = fs.readFileSync(envPath, "utf-8");
  envContent.split("\n").forEach((line) => {
    const match = line.match(/^\s*([\w.-]+)\s*=\s*(.*)?\s*$/);
    if (match) {
      process.env[match[1]] = match[2].replace(/(^['"]|['"]$)/g, "").trim();
    }
  });
}

const host = process.env.API_HOST || "127.0.0.1";
const port = process.env.API_PORT || "8715";

const nextConfig: NextConfig = {
  env: {
    NEXT_PUBLIC_API_URL: `http://${host}:${port}`,
  },
};

export default nextConfig;
