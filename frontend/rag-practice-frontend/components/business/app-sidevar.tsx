"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { Bot, BookOpen, BarChart2, Settings } from "lucide-react";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

interface SidebarProps extends React.HTMLAttributes<HTMLDivElement> {}

export function AppSidebar({ className }: SidebarProps) {
  const pathname = usePathname();

  const navItems = [
    {
      title: "知识库管理",
      href: "/knowledge",
      icon: BookOpen,
      match: "/knowledge",
    },
    {
      title: "对话检索",
      href: "/chat",
      icon: Bot,
      match: "/chat",
    },
    {
      title: "评测看板",
      href: "/evaluation",
      icon: BarChart2,
      match: "/evaluation",
    },
  ];

  return (
    <div className={cn("pb-12 h-full border-r bg-zinc-50/40 dark:bg-zinc-900/40", className)}>
      <div className="space-y-4 py-4">
        <div className="px-3 py-2">
          <div className="flex h-10 items-center px-4 mb-2">
            <div className="mr-2 h-6 w-6 bg-primary rounded-md flex items-center justify-center text-primary-foreground font-bold text-xs">
              RP
            </div>
            <h2 className="text-lg font-semibold tracking-tight">RAG Practice</h2>
          </div>
          <div className="space-y-1">
            {navItems.map((item) => (
              <Button
                key={item.href}
                variant={pathname.startsWith(item.match) ? "secondary" : "ghost"}
                className="w-full justify-start"
                asChild
              >
                <Link href={item.href}>
                  <item.icon className="mr-2 h-4 w-4" />
                  {item.title}
                </Link>
              </Button>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}