/**
 * frontend/rag-practice-frontend/components/business/app-sidebar.tsx
 */
"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { 
  BookOpen, 
  BarChart2, 
  MessageSquare, 
  Bot, 
  Zap, 
  Plus, 
  Trash2, 
  MoreHorizontal,
  Loader2,
  MessageSquareDashed
} from "lucide-react";
import { format } from "date-fns";
import { toast } from "sonner";

import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
} from "@/components/ui/dialog";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Label } from "@/components/ui/label";

import { chatService } from "@/lib/services/chat";
import { knowledgeService } from "@/lib/services/knowledge";
import { Knowledge } from "@/lib/types";
import { useChatStore, useAuthStore } from "@/lib/store"; // 🟢 [修改] 引入 useAuthStore

interface SidebarProps extends React.HTMLAttributes<HTMLDivElement> {}

// Icon Mapping helper
const getSessionIcon = (iconName: string) => {
  switch (iconName) {
    case "bot": return Bot;
    case "zap": return Zap;
    case "book-open": return BookOpen;
    default: return MessageSquare;
  }
};

export function AppSidebar({ className }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();

  // 🟢 [修改] 获取当前用户权限信息
  const { user } = useAuthStore();
  
  // 🟢 使用全局 Store
  const { sessions, isLoading: sessionsLoading, fetchSessions, addSession, removeSession } = useChatStore();
  
  const [knowledges, setKnowledges] = useState<Knowledge[]>([]);
  const [isNewChatOpen, setIsNewChatOpen] = useState(false);
  const [selectedKbId, setSelectedKbId] = useState<string>("");
  const [creating, setCreating] = useState(false);

  // 初始化加载
  useEffect(() => {
    fetchSessions(); // 加载会话 (Store 负责)
    
    // 加载知识库 (本地 State 即可，其他地方不太需要共享)
    const loadKb = async () => {
      try {
        const data = await knowledgeService.getAll();
        setKnowledges(data);
      } catch (e) {
        console.error(e);
      }
    };
    loadKb();
  }, []); // 只在挂载时加载一次，后续由操作触发更新

  const handleCreateSession = async () => {
    if (!selectedKbId) {
      toast.error("请选择一个知识库");
      return;
    }
    setCreating(true);
    try {
      const session = await chatService.createSession(Number(selectedKbId));
      addSession(session); // 🟢 更新全局 Store
      setIsNewChatOpen(false);
      router.push(`/chat/${session.id}`);
      toast.success("新会话已创建");
    } catch (error) {
      toast.error("创建失败");
    } finally {
      setCreating(false);
    }
  };

  const handleDeleteSession = async (e: React.MouseEvent, id: string) => {
    e.preventDefault();
    e.stopPropagation();
    
    if (!confirm("确定要删除此会话吗？")) return;

    try {
      await chatService.deleteSession(id);
      removeSession(id); // 🟢 更新全局 Store
      
      if (pathname === `/chat/${id}`) {
        router.push("/chat");
      }
      toast.success("会话已删除");
    } catch (error) {
      toast.error("删除失败");
    }
  };

  // 🟢 [修改] 根据权限动态生成菜单
  const staticNavItems = [
    { 
      title: "知识库管理", 
      href: "/knowledge", 
      icon: BookOpen, 
      match: "/knowledge",
      visible: true 
    },
    { 
      title: "评测看板", 
      href: "/evaluation", 
      icon: BarChart2, 
      match: "/evaluation",
      // 仅管理员可见
      visible: user?.is_superuser 
    },
  ];

  return (
    <div className={cn("flex flex-col h-full border-r bg-zinc-50/40 dark:bg-zinc-900/40", className)}>
      
      <div className="px-6 py-4 flex items-center h-16 shrink-0">
        <div className="mr-2 h-6 w-6 bg-primary rounded-md flex items-center justify-center text-primary-foreground font-bold text-xs">
          RP
        </div>
        <h2 className="text-lg font-semibold tracking-tight">RAG Practice</h2>
      </div>

      <div className="px-3 space-y-1 shrink-0">
        {staticNavItems.map((item) => {
          // 🟢 [修改] 如果不可见则不渲染
          if (!item.visible) return null;

          return (
            <Button
              key={item.href}
              variant={pathname.startsWith(item.match) ? "secondary" : "ghost"}
              className="w-full justify-start font-normal"
              asChild
            >
              <Link href={item.href}>
                <item.icon className="mr-2 h-4 w-4" />
                {item.title}
              </Link>
            </Button>
          );
        })}
      </div>

      <Separator className="my-4" />

      <div className="px-4 flex items-center justify-between shrink-0 mb-2">
        <h3 className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
          对话列表
        </h3>
        
        <Dialog open={isNewChatOpen} onOpenChange={setIsNewChatOpen}>
          <DialogTrigger asChild>
            <Button variant="ghost" size="icon" className="h-6 w-6" title="新建对话">
              <Plus className="h-4 w-4" />
            </Button>
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>开始新对话</DialogTitle>
            </DialogHeader>
            <div className="grid gap-4 py-4">
              <div className="grid gap-2">
                <Label>默认知识库</Label>
                <Select onValueChange={setSelectedKbId} value={selectedKbId}>
                  <SelectTrigger>
                    <SelectValue placeholder="选择初始知识库..." />
                  </SelectTrigger>
                  <SelectContent>
                    {knowledges.map((kb) => (
                      <SelectItem key={kb.id} value={String(kb.id)}>
                        {kb.name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
                <p className="text-xs text-muted-foreground">创建后可在设置中添加更多知识库。</p>
              </div>
            </div>
            <DialogFooter>
              <Button onClick={handleCreateSession} disabled={creating}>
                {creating && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                创建
              </Button>
            </DialogFooter>
          </DialogContent>
        </Dialog>
      </div>

      <div className="flex-1 overflow-y-auto px-3 min-h-0">
        {sessionsLoading && sessions.length === 0 ? (
          <div className="flex justify-center py-4">
            <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
          </div>
        ) : sessions.length === 0 ? (
          <div className="text-center py-8 px-4 border-2 border-dashed rounded-lg mx-2">
            <MessageSquareDashed className="h-8 w-8 text-muted-foreground mx-auto mb-2" />
            <p className="text-xs text-muted-foreground">暂无历史会话</p>
            <Button variant="link" size="sm" onClick={() => setIsNewChatOpen(true)} className="mt-1 h-auto p-0">
              立即创建
            </Button>
          </div>
        ) : (
          <div className="space-y-1 pb-4">
            {sessions.map((session) => {
              const isActive = pathname === `/chat/${session.id}`;
              const Icon = getSessionIcon(session.icon || "message-square");
              
              return (
                <Link
                  key={session.id}
                  href={`/chat/${session.id}`}
                  className={cn(
                    "group flex items-center gap-3 rounded-md px-3 py-2 text-sm transition-colors relative",
                    isActive 
                      ? "bg-primary/10 text-primary font-medium" 
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  )}
                >
                  <Icon className="h-4 w-4 shrink-0" />
                  <div className="flex-1 truncate text-left pr-6">
                    <div className="truncate">{session.title || "新对话"}</div>
                    <div className="text-[10px] opacity-60 font-normal truncate">
                      {format(new Date(session.updated_at), "MM-dd HH:mm")}
                    </div>
                  </div>
                  
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button
                        variant="ghost"
                        size="icon"
                        className={cn(
                          "h-6 w-6 absolute right-2 opacity-0 group-hover:opacity-100 transition-opacity",
                          isActive && "opacity-100"
                        )}
                        onClick={(e) => e.stopPropagation()}
                      >
                        <MoreHorizontal className="h-3 w-3" />
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end">
                      <DropdownMenuItem 
                        className="text-destructive focus:text-destructive cursor-pointer"
                        onClick={(e) => handleDeleteSession(e, session.id)}
                      >
                        <Trash2 className="mr-2 h-4 w-4" /> 删除会话
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}