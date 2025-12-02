"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function DashboardPage() {
  const router = useRouter();

  useEffect(() => {
    // 默认跳转到知识库管理页
    router.replace("/knowledge");
  }, [router]);

  return (
    <div className="flex items-center justify-center h-[50vh] text-muted-foreground">
      正在跳转...
    </div>
  );
}