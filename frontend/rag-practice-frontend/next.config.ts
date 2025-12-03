import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
  // 移除下面这段，Next.js 15/16 可能不再支持在 config 中配置它，
  // 或者 Turbopack 对此有严格校验。
  // eslint: {
  //   ignoreDuringBuilds: true,
  // },
};

export default nextConfig;