"use client";

import { useState, useCallback } from "react";
import { useDropzone } from "react-dropzone";
import { UploadCloud, File as FileIcon, X, Loader2, CheckCircle2, AlertCircle } from "lucide-react";
import { toast } from "sonner";
import { Progress } from "@/components/ui/progress";
import { Button } from "@/components/ui/button";
import { knowledgeService } from "@/lib/services/knowledge";
import { cn } from "@/lib/utils";

interface FileUploaderProps {
  knowledgeId: number;
  onUploadSuccess?: () => void;
}

interface UploadingFile {
  file: File;
  progress: number;
  status: "uploading" | "success" | "error";
  error?: string;
}

export function FileUploader({ knowledgeId, onUploadSuccess }: FileUploaderProps) {
  const [uploadQueue, setUploadQueue] = useState<UploadingFile[]>([]);

  const onDrop = useCallback(async (acceptedFiles: File[]) => {
    // 过滤掉已经在队列中的文件
    const newFiles = acceptedFiles.map(file => ({
      file,
      progress: 0,
      status: "uploading" as const
    }));

    setUploadQueue(prev => [...prev, ...newFiles]);

    // 并行上传
    newFiles.forEach(item => uploadFile(item.file));
  }, [knowledgeId]);

  const uploadFile = async (file: File) => {
    try {
      await knowledgeService.uploadFile(knowledgeId, file, (event) => {
        const percent = Math.round((event.loaded * 100) / event.total);
        updateFileStatus(file.name, { progress: percent });
      });

      updateFileStatus(file.name, { status: "success", progress: 100 });
      toast.success(`${file.name} 上传成功`);
      onUploadSuccess?.();
    } catch (error: any) {
      console.error(error);
      const errMsg = error.response?.data?.detail || "上传失败";
      updateFileStatus(file.name, { status: "error", error: errMsg });
      toast.error(`${file.name} 上传失败: ${errMsg}`);
    }
  };

  const updateFileStatus = (fileName: string, updates: Partial<UploadingFile>) => {
    setUploadQueue(prev => prev.map(item => 
      item.file.name === fileName ? { ...item, ...updates } : item
    ));
  };

  const removeFile = (fileName: string) => {
    setUploadQueue(prev => prev.filter(item => item.file.name !== fileName));
  };

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'application/pdf': ['.pdf'],
      'application/vnd.openxmlformats-officedocument.wordprocessingml.document': ['.docx'],
      'application/msword': ['.doc'],
      'text/plain': ['.txt', '.md']
    },
    maxSize: 50 * 1024 * 1024, // 50MB
  });

  return (
    <div className="space-y-4">
      {/* 拖拽区域 */}
      <div
        {...getRootProps()}
        className={cn(
          "border-2 border-dashed rounded-lg p-8 text-center cursor-pointer transition-colors duration-200 ease-in-out",
          isDragActive 
            ? "border-primary bg-primary/5" 
            : "border-muted-foreground/25 hover:border-primary/50 hover:bg-muted/30"
        )}
      >
        <input {...getInputProps()} />
        <div className="flex flex-col items-center justify-center gap-2">
          <div className="p-3 bg-muted rounded-full">
            <UploadCloud className="h-6 w-6 text-muted-foreground" />
          </div>
          <div className="text-sm font-medium">
            <span className="text-primary">点击上传</span> 或拖拽文件到这里
          </div>
          <p className="text-xs text-muted-foreground">
            支持 PDF, DOCX, TXT, MD (最大 50MB)
          </p>
        </div>
      </div>

      {/* 上传列表 */}
      {uploadQueue.length > 0 && (
        <div className="space-y-2">
          {uploadQueue.map((item) => (
            <div key={item.file.name} className="flex items-center gap-3 p-3 bg-background border rounded-md shadow-sm">
              <div className="shrink-0">
                <FileIcon className="h-8 w-8 text-blue-500/20 fill-blue-500/20" />
              </div>
              
              <div className="flex-1 min-w-0 space-y-1">
                <div className="flex justify-between items-center">
                  <p className="text-sm font-medium truncate max-w-[200px]" title={item.file.name}>
                    {item.file.name}
                  </p>
                  {item.status === "uploading" && <span className="text-xs text-muted-foreground">{item.progress}%</span>}
                </div>
                
                {item.status === "uploading" && (
                  <Progress value={item.progress} className="h-1.5" />
                )}
                
                {item.status === "error" && (
                  <p className="text-xs text-destructive flex items-center gap-1">
                    <AlertCircle className="h-3 w-3" /> {item.error}
                  </p>
                )}
              </div>

              <div className="shrink-0">
                {item.status === "uploading" ? (
                  <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
                ) : item.status === "success" ? (
                  <CheckCircle2 className="h-5 w-5 text-green-500" />
                ) : (
                  <Button variant="ghost" size="icon" className="h-6 w-6" onClick={() => removeFile(item.file.name)}>
                    <X className="h-4 w-4" />
                  </Button>
                )}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}