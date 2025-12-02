"use client";

import { format } from "date-fns";
import { FileText, MoreVertical, Trash2, RefreshCw } from "lucide-react";
import { 
  Table, 
  TableBody, 
  TableCell, 
  TableHead, 
  TableHeader, 
  TableRow 
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";
import { RAGDocument } from "@/lib/services/knowledge";

interface DocumentListProps {
  documents: RAGDocument[];
  onDelete: (doc: RAGDocument) => void;
  isLoading?: boolean;
}

export function DocumentList({ documents, onDelete, isLoading }: DocumentListProps) {
  
  const getStatusBadge = (status: string, error?: string) => {
    switch (status) {
      case "COMPLETED":
        return <Badge variant="default" className="bg-green-500 hover:bg-green-600">已完成</Badge>;
      case "PROCESSING":
        return (
          <Badge variant="secondary" className="gap-1">
            <RefreshCw className="h-3 w-3 animate-spin" /> 处理中
          </Badge>
        );
      case "FAILED":
        return (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger>
                <Badge variant="destructive" className="cursor-help">失败</Badge>
              </TooltipTrigger>
              <TooltipContent>
                <p>{error || "未知错误"}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        );
      default:
        return <Badge variant="outline">等待中</Badge>;
    }
  };

  if (isLoading) {
    return <div className="p-8 text-center text-muted-foreground">加载中...</div>;
  }

  if (documents.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center p-12 border rounded-lg bg-muted/5 border-dashed">
        <div className="bg-muted p-4 rounded-full mb-3">
          <FileText className="h-8 w-8 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-medium">暂无文档</h3>
        <p className="text-sm text-muted-foreground mt-1">上传文件以开始构建知识库索引。</p>
      </div>
    );
  }

  return (
    <div className="border rounded-md">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead className="w-[40%]">文件名</TableHead>
            <TableHead>状态</TableHead>
            <TableHead>上传时间</TableHead>
            <TableHead className="text-right">操作</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {documents.map((doc) => (
            <TableRow key={doc.id}>
              <TableCell className="font-medium">
                <div className="flex items-center gap-2">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  <span className="truncate max-w-[200px] md:max-w-[300px]" title={doc.filename}>
                    {doc.filename}
                  </span>
                </div>
              </TableCell>
              <TableCell>
                {getStatusBadge(doc.status, doc.error_message)}
              </TableCell>
              <TableCell className="text-muted-foreground text-sm">
                {doc.created_at ? format(new Date(doc.created_at), "yyyy-MM-dd HH:mm") : "-"}
              </TableCell>
              <TableCell className="text-right">
                <DropdownMenu>
                  <DropdownMenuTrigger asChild>
                    <Button variant="ghost" size="icon" className="h-8 w-8">
                      <MoreVertical className="h-4 w-4" />
                      <span className="sr-only">菜单</span>
                    </Button>
                  </DropdownMenuTrigger>
                  <DropdownMenuContent align="end">
                    <DropdownMenuItem 
                      className="text-destructive focus:text-destructive cursor-pointer"
                      onClick={() => onDelete(doc)}
                    >
                      <Trash2 className="mr-2 h-4 w-4" /> 删除文档
                    </DropdownMenuItem>
                  </DropdownMenuContent>
                </DropdownMenu>
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}