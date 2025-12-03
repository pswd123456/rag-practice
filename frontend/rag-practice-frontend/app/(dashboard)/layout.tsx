"use client";

import { useEffect, useState } from "react";
import { useRouter, usePathname } from "next/navigation";
import { Menu } from "lucide-react";

import { AppSidebar } from "@/components/business/app-sidebar";
import { UserNav } from "@/components/business/user-nav";
import { ModeToggle } from "@/components/business/mode-toggle";
import { useAuthStore } from "@/lib/store";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const { isAuthenticated } = useAuthStore();
  const [isClient, setIsClient] = useState(false);

  useEffect(() => {
    setIsClient(true);
  }, []);

  useEffect(() => {
    if (isClient && !isAuthenticated) {
      router.replace("/login");
    }
  }, [isClient, isAuthenticated, router]);

  if (!isClient) return null;
  if (!isAuthenticated) return null;

  // 检查是否为聊天页面
  const isChatPage = pathname?.startsWith("/chat");

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* --- Desktop Sidebar --- */}
      <aside className="hidden w-64 flex-col border-r md:flex bg-zinc-50/40 dark:bg-zinc-900/40">
        <AppSidebar />
      </aside>

      {/* --- Mobile & Main Content --- */}
      <div className="flex flex-1 flex-col overflow-hidden">
        {/* Header */}
        <header className="flex h-14 items-center gap-4 border-b bg-background/95 backdrop-blur px-6 shrink-0 z-50">
          <Sheet>
            <SheetTrigger asChild>
              <Button variant="outline" size="icon" className="md:hidden shrink-0">
                <Menu className="h-5 w-5" />
                <span className="sr-only">Toggle navigation menu</span>
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="p-0 w-64">
              <AppSidebar />
            </SheetContent>
          </Sheet>

          <div className="flex-1">
            {/* Breadcrumb place holder */}
          </div>

          <div className="flex items-center gap-2">
            <ModeToggle />
            <UserNav />
          </div>
        </header>

        {/* Main Content Area */}
        {/* 修复双重滚动条的关键：
            1. 外层 flex-1 overflow-hidden 防止 body 滚动。
            2. 聊天页面 (isChatPage) 不需要 padding 和自身的 overflow-y，由内部组件处理。
            3. 其他页面 (Knowledge等) 保持 padding 和 overflow-y-auto。
        */}
        <main 
          className={cn(
            "flex-1 overflow-hidden relative",
            !isChatPage && "overflow-y-auto p-6 md:p-8 bg-zinc-50/50 dark:bg-zinc-950/50"
          )}
        >
          {children}
        </main>
      </div>
    </div>
  );
}