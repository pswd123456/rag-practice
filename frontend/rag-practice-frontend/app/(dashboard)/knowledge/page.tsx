"use client";

import { useEffect, useState } from "react";
import { Plus, MoreHorizontal, Edit2, Trash2, Database, BrainCircuit, Layers } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel
} from "@/components/ui/dropdown-menu";
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { Skeleton } from "@/components/ui/skeleton";

import { knowledgeService } from "@/lib/services/knowledge";
import { Knowledge, UserKnowledgeRole, KnowledgeStatus } from "@/lib/types";
import { KnowledgeDialog } from "@/components/business/knowledge-dialog";

export default function KnowledgePage() {
  // State
  const [data, setData] = useState<Knowledge[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Dialog States
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [editingKb, setEditingKb] = useState<Knowledge | null>(null);
  const [deletingKb, setDeletingKb] = useState<Knowledge | null>(null);

  // Fetch Data
  const fetchKnowledges = async () => {
    try {
      const res = await knowledgeService.getAll();
      setData(res);
    } catch (err) {
      toast.error("获取知识库列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchKnowledges();
  }, []);

  // Handlers
  const handleCreate = async (values: any) => {
    try {
      await knowledgeService.create({
        ...values,
        chunk_overlap: 50, // Default
      });
      toast.success("知识库创建成功");
      fetchKnowledges();
    } catch (error) {
      toast.error("创建失败，请重试");
      throw error;
    }
  };

  const handleUpdate = async (values: any) => {
    if (!editingKb) return;
    try {
      await knowledgeService.update(editingKb.id, values);
      toast.success("知识库更新成功");
      fetchKnowledges();
    } catch (error) {
      toast.error("更新失败");
      throw error;
    }
  };

  const handleDelete = async () => {
    if (!deletingKb) return;
    try {
      await knowledgeService.delete(deletingKb.id);
      toast.info("删除任务已提交，状态稍后更新");
      fetchKnowledges(); 
    } catch (error) {
      toast.error("删除失败");
    } finally {
      setDeletingKb(null);
    }
  };

  // 辅助函数：角色 Badge 样式
  const getRoleBadge = (role: UserKnowledgeRole) => {
    switch (role) {
      case UserKnowledgeRole.OWNER:
        return <Badge variant="default" className="bg-primary/80 hover:bg-primary/80">所有者</Badge>;
      case UserKnowledgeRole.EDITOR:
        return <Badge variant="secondary" className="text-blue-600 bg-blue-50 hover:bg-blue-100 dark:bg-blue-900/30 dark:text-blue-300">协作者</Badge>;
      case UserKnowledgeRole.VIEWER:
        return <Badge variant="outline" className="text-muted-foreground">访客</Badge>;
      default:
        return <Badge variant="outline">{role}</Badge>;
    }
  };

  // 辅助函数：状态显示
  const getStatusDisplay = (status: KnowledgeStatus) => {
    if (status === KnowledgeStatus.DELETING) {
      return <span className="text-red-500 flex items-center gap-1 text-xs"><span className="animate-pulse">●</span> 删除中...</span>;
    }
    if (status === KnowledgeStatus.FAILED) {
      return <span className="text-orange-500 text-xs">⚠️ 状态异常</span>;
    }
    return <span className="text-green-600 dark:text-green-400 text-xs flex items-center gap-1">● 运行正常</span>;
  };

  // 辅助函数：格式化模型名称显示 (解决名称太长的问题)
  const formatModelName = (name: string) => {
    if (name === "text-embedding-v4") return "Embedding V4";
    if (name === "text-embedding-v3") return "Embedding V3";
    // 如果有其他很长的模型名，可以在这里截断或者映射
    if (name.length > 15) return name.slice(0, 12) + "..."; 
    return name;
  };

  return (
    <div className="container mx-auto py-8 px-4 sm:px-6 space-y-8 max-w-7xl">
      {/* 头部区域 */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 border-b pb-6">
        <div>
          <h2 className="text-3xl font-bold tracking-tight text-foreground">知识库管理</h2>
          <p className="text-muted-foreground mt-1">
            在这里创建和管理您的文档集合、Embedding 索引配置以及协作权限。
          </p>
        </div>
        <Button onClick={() => setIsCreateOpen(true)} size="lg" className="shadow-sm">
          <Plus className="mr-2 h-4 w-4" /> 新建知识库
        </Button>
      </div>

      {/* 列表区域 */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {[1, 2, 3].map((i) => (
            <Skeleton key={i} className="h-[220px] rounded-xl" />
          ))}
        </div>
      ) : data.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-80 border-2 border-dashed rounded-xl bg-muted/5">
          <div className="p-4 rounded-full bg-muted/30 mb-4">
            <Database className="h-10 w-10 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-semibold text-foreground">暂无知识库</h3>
          <p className="text-muted-foreground mb-6 text-sm max-w-sm text-center">
            您还没有创建任何知识库。创建一个知识库以上传文档并开始使用 RAG 问答功能。
          </p>
          <Button onClick={() => setIsCreateOpen(true)}>立即创建</Button>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-6">
          {data.map((kb) => (
            <Card key={kb.id} className="group relative flex flex-col justify-between overflow-hidden transition-all duration-300 hover:shadow-lg hover:border-primary/50">
              <CardHeader className="pb-3">
                <div className="flex justify-between items-start">
                  <div className="space-y-1.5 min-w-0 flex-1 pr-1">
                    <CardTitle 
                      className="text-lg font-semibold leading-tight flex items-center gap-2 truncate py-0.5"
                      title={kb.name}
                    >
                      {kb.name}
                    </CardTitle>
                    <div className="flex items-center gap-2">
                      {getRoleBadge(kb.role)}
                    </div>
                  </div>
                  
                  {/* 操作菜单 */}
                  <DropdownMenu>
                    <DropdownMenuTrigger asChild>
                      <Button variant="ghost" size="icon" className="h-8 w-8 -mt-1 -mr-2 text-muted-foreground opacity-0 group-hover:opacity-100 transition-opacity shrink-0">
                        <MoreHorizontal className="h-4 w-4" />
                        <span className="sr-only">菜单</span>
                      </Button>
                    </DropdownMenuTrigger>
                    <DropdownMenuContent align="end" className="w-[160px]">
                      <DropdownMenuLabel>操作</DropdownMenuLabel>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem 
                        onClick={() => setEditingKb(kb)}
                        disabled={kb.role === UserKnowledgeRole.VIEWER || kb.status === KnowledgeStatus.DELETING}
                        className="cursor-pointer"
                      >
                        <Edit2 className="mr-2 h-4 w-4" /> 编辑信息
                      </DropdownMenuItem>
                      <DropdownMenuSeparator />
                      <DropdownMenuItem 
                        className="text-destructive focus:text-destructive cursor-pointer"
                        onClick={() => setDeletingKb(kb)}
                        disabled={kb.role !== UserKnowledgeRole.OWNER || kb.status === KnowledgeStatus.DELETING}
                      >
                        <Trash2 className="mr-2 h-4 w-4" /> 删除
                      </DropdownMenuItem>
                    </DropdownMenuContent>
                  </DropdownMenu>
                </div>
              </CardHeader>
              
              <CardContent className="pb-3">
                <CardDescription className="line-clamp-2 min-h-[40px] mb-4 text-sm">
                  {kb.description || "暂无描述信息"}
                </CardDescription>
                
                <div className="flex items-center gap-3 text-xs text-muted-foreground bg-muted/40 p-2 rounded-md">
                    <div className="flex items-center gap-1.5 min-w-0 flex-1" title={kb.embed_model}>
                        <BrainCircuit className="h-3.5 w-3.5 shrink-0" />
                        {/* 使用 formatModelName 缩短显示名称，完整名称在 Tooltip 中 */}
                        <span className="truncate">{formatModelName(kb.embed_model)}</span>
                    </div>
                    <div className="w-px h-3 bg-border"></div>
                    <div className="flex items-center gap-1.5 shrink-0">
                        <Layers className="h-3.5 w-3.5" />
                        <span>{kb.chunk_size}</span>
                    </div>
                </div>
              </CardContent>
              
              <CardFooter className="pt-3 border-t bg-muted/5 flex justify-between items-center h-12">
                 {getStatusDisplay(kb.status)}
                 <span className="text-[10px] text-muted-foreground">ID: {kb.id}</span>
              </CardFooter>
            </Card>
          ))}
        </div>
      )}

      {/* 弹窗组件 */}
      <KnowledgeDialog 
        open={isCreateOpen} 
        onOpenChange={setIsCreateOpen}
        onSubmit={handleCreate}
      />

      <KnowledgeDialog 
        open={!!editingKb} 
        onOpenChange={(open) => !open && setEditingKb(null)}
        knowledge={editingKb}
        onSubmit={handleUpdate}
      />

      <AlertDialog open={!!deletingKb} onOpenChange={(open) => !open && setDeletingKb(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>确认要删除吗？</AlertDialogTitle>
            <AlertDialogDescription>
              此操作<span className="text-destructive font-bold">不可撤销</span>。
              <br/>
              将永久删除知识库 <span className="font-semibold text-foreground">"{deletingKb?.name}"</span> 及其关联的所有文档和向量索引。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-destructive hover:bg-destructive/90">
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}