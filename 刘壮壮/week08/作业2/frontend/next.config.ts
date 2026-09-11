import type { NextConfig } from "next";
import { loadEnvConfig } from "@next/env";
import path from "path";

// 与后端共用仓库根目录的 .env（NEXT_PUBLIC_API_BASE 等）
loadEnvConfig(path.resolve(__dirname, ".."));

const nextConfig: NextConfig = {};

export default nextConfig;
