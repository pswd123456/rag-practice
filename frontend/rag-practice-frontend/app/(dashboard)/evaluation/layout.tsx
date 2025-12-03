"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { BarChart3, Database } from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";

export default function EvaluationLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const pathname = usePathname();

  const tabs = [
    { 
      name: "测试集管理 (Testsets)", 
      href: "/evaluation/testsets", 
      icon: Database 
    },
    { 
      name: "实验运行 (Experiments)", 
      href: "/evaluation/experiments", 
      icon: BarChart3 
    },
  ];

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between border-b pb-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Ragas 评估看板</h1>
          <p className="text-muted-foreground text-sm mt-1">
            生成测试数据，运行 RAG 性能评估，并通过雷达图可视化分析指标。
          </p>
        </div>
      </div>

      <div className="flex items-center space-x-2">
        {tabs.map((tab) => {
          const isActive = pathname === tab.href;
          return (
            <Button
              key={tab.href}
              variant={isActive ? "secondary" : "ghost"}
              className={cn(
                "h-9 gap-2",
                isActive && "bg-muted font-medium text-primary"
              )}
              asChild
            >
              <Link href={tab.href}>
                <tab.icon className="h-4 w-4" />
                {tab.name}
              </Link>
            </Button>
          );
        })}
      </div>

      <div className="min-h-[600px]">
        {children}
      </div>
    </div>
  );
}