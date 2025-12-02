"use client";

import { useEffect, useState, useRef } from "react";
import { useParams, useRouter } from "next/navigation";
import { toast } from "sonner";
import { ArrowLeft, Loader2, Settings, FileText, Users } from "lucide-react";
import { cn } from "@/lib/utils"; 

import { Button } from "@/components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Skeleton } from "@/components/ui/skeleton";
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

import { knowledgeService, RAGDocument } from "@/lib/services/knowledge";
import { Knowledge } from "@/lib/types";
import { FileUploader } from "@/components/business/file-uploader";
import { DocumentList } from "@/components/business/document-list";
import { KnowledgeBasicForm, MemberManagement } from "@/components/business/knowledge-settings";

export default function KnowledgeDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = Number(params.id);

  const [knowledge, setKnowledge] = useState<Knowledge | null>(null);
  const [documents, setDocuments] = useState<RAGDocument[]>([]);
  const [loading, setLoading] = useState(true);
  const [deleteDoc, setDeleteDoc] = useState<RAGDocument | null>(null);
  
  // 轮询控制
  const pollingRef = useRef<NodeJS.Timeout | null>(null);

  const fetchData = async () => {
    try {
      const [kbData, docsData] = await Promise.all([
        knowledgeService.getById(id),
        knowledgeService.getDocuments(id),
      ]);
      setKnowledge(kbData);
      setDocuments(docsData);
      return docsData;
    } catch (error) {
      console.error(error);
      toast.error("加载失败，请检查网络或权限");
      router.push("/knowledge"); // 回退
      return [];
    } finally {
      setLoading(false);
    }
  };

  // 刷新知识库基本信息（当修改名称/描述后调用）
  const refreshInfo = async () => {
    try {
      const kbData = await knowledgeService.getById(id);
      setKnowledge(kbData);
    } catch (e) {
      console.error(e);
    }
  };

  // 初始化加载
  useEffect(() => {
    if (!id) return;
    fetchData();
  }, [id]);

  // 轮询逻辑
  useEffect(() => {
    const checkStatus = async () => {
      try {
        const docs = await knowledgeService.getDocuments(id);
        setDocuments(docs);
        const hasProcessing = docs.some(d => d.status === "PROCESSING" || d.status === "PENDING");
        if (!hasProcessing && pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
      } catch (e) {
        console.error("Polling error", e);
      }
    };

    const hasProcessing = documents.some(d => d.status === "PROCESSING" || d.status === "PENDING");
    if (hasProcessing && !pollingRef.current) {
      pollingRef.current = setInterval(checkStatus, 3000);
    }

    return () => {
      if (pollingRef.current) clearInterval(pollingRef.current);
    };
  }, [documents, id]);

  const handleDeleteDocument = async () => {
    if (!deleteDoc) return;
    try {
      await knowledgeService.deleteDocument(deleteDoc.id);
      toast.success("文档删除成功");
      setDocuments(prev => prev.filter(d => d.id !== deleteDoc.id));
    } catch (error) {
      toast.error("删除失败");
    } finally {
      setDeleteDoc(null);
    }
  };

  if (loading) {
    return (
      <div className="container mx-auto py-8 space-y-6 max-w-5xl">
        <Skeleton className="h-10 w-1/3" />
        <Skeleton className="h-[200px] w-full" />
      </div>
    );
  }

  if (!knowledge) return null;

  return (
    <div className="container mx-auto py-6 space-y-6 max-w-6xl">
      {/* 顶部导航 */}
      <div className="flex items-center gap-4">
        <Button variant="ghost" size="icon" onClick={() => router.push("/knowledge")}>
          <ArrowLeft className="h-5 w-5" />
        </Button>
        <div>
          <h1 className="text-2xl font-bold tracking-tight">{knowledge.name}</h1>
          <p className="text-muted-foreground text-sm flex items-center gap-2">
            {knowledge.description || "暂无描述"}
            <span className="text-xs bg-muted px-2 py-0.5 rounded">ID: {knowledge.id}</span>
          </p>
        </div>
      </div>

      {/* 核心内容区 - 拆分为 3 个 Tabs */}
      <Tabs defaultValue="documents" className="space-y-6">
        <TabsList>
          <TabsTrigger value="documents" className="gap-2">
            <FileText className="h-4 w-4" /> 文档管理
          </TabsTrigger>
          <TabsTrigger value="members" className="gap-2">
            <Users className="h-4 w-4" /> 成员权限
          </TabsTrigger>
          <TabsTrigger value="settings" className="gap-2">
            <Settings className="h-4 w-4" /> 基本设置
          </TabsTrigger>
        </TabsList>

        <TabsContent value="documents" className="space-y-6 animate-in fade-in-50 duration-300">
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
            <div className="lg:col-span-2 space-y-4">
              <div className="flex items-center justify-between">
                <h3 className="text-lg font-medium">已收录文档 ({documents.length})</h3>
                <Button variant="outline" size="sm" onClick={() => fetchData()}>
                  <Loader2 className={cn("h-3 w-3 mr-2", pollingRef.current && "animate-spin")} /> 
                  刷新
                </Button>
              </div>
              <DocumentList 
                documents={documents} 
                onDelete={setDeleteDoc} 
                isLoading={loading} 
              />
            </div>
            <div className="lg:col-span-1">
              <div className="sticky top-24">
                <h3 className="text-lg font-medium mb-4">上传新文件</h3>
                <FileUploader 
                  knowledgeId={id} 
                  onUploadSuccess={fetchData} 
                />
              </div>
            </div>
          </div>
        </TabsContent>

        <TabsContent value="members" className="animate-in fade-in-50 duration-300">
          <div className="max-w-3xl">
            <MemberManagement knowledge={knowledge} />
          </div>
        </TabsContent>

        <TabsContent value="settings" className="animate-in fade-in-50 duration-300">
          <div className="max-w-3xl">
            <KnowledgeBasicForm 
              knowledge={knowledge} 
              onUpdate={refreshInfo} 
            />
          </div>
        </TabsContent>
      </Tabs>

      {/* 删除文档确认弹窗 */}
      <AlertDialog open={!!deleteDoc} onOpenChange={(open) => !open && setDeleteDoc(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>删除文档</AlertDialogTitle>
            <AlertDialogDescription>
              确定要删除 <span className="font-semibold text-foreground">"{deleteDoc?.filename}"</span> 吗？
              这将从知识库和向量索引中永久移除。
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>取消</AlertDialogCancel>
            <AlertDialogAction onClick={handleDeleteDocument} className="bg-destructive hover:bg-destructive/90">
              确认删除
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}