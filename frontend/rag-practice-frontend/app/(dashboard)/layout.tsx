// frontend/rag-practice-frontend/app/(dashboard)/layout.tsx
"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { Menu } from "lucide-react";

import { AppSidebar } from "@/components/business/app-sidebar";
import { UserNav } from "@/components/business/user-nav";
import { ModeToggle } from "@/components/business/mode-toggle"; // 🟢 引入
import { useAuthStore } from "@/lib/store";
import { Sheet, SheetContent, SheetTrigger } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";

export default function DashboardLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
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

  return (
    <div className="flex min-h-screen flex-col md:flex-row bg-background">
      {/* --- Desktop Sidebar --- */}
      <aside className="hidden w-64 flex-col md:flex fixed inset-y-0 z-50">
        <AppSidebar />
      </aside>

      {/* --- Mobile Header & Content --- */}
      <div className="flex-1 md:ml-64 flex flex-col min-h-screen">
        {/* Header */}
        <header className="sticky top-0 z-40 flex h-16 items-center gap-4 border-b bg-background/95 backdrop-blur supports-[backdrop-filter]:bg-background/60 px-6 shadow-sm">
          {/* Mobile Sidebar Trigger */}
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
            {/* Title / Breadcrumbs */}
          </div>

          <div className="flex items-center gap-2">
            <ModeToggle /> {/* 🟢 添加切换按钮 */}
            <UserNav />
          </div>
        </header>

        {/* Main Content Area */}
        <main className="flex-1 p-6 md:p-8 bg-zinc-50/50 dark:bg-zinc-950/50">
          {children}
        </main>
      </div>
    </div>
  );
}