"use client";

import { useEffect } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { 
  Loader2, 
  Database, 
  FileText, 
  Settings2, 
  Cpu, 
  Layers 
} from "lucide-react";

import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Knowledge } from "@/lib/types";
import { Badge } from "@/components/ui/badge";

// 表单验证规则
const formSchema = z.object({
  name: z.string().min(2, "名称至少需要 2 个字符"),
  description: z.string().optional(),
  embed_model: z.string().min(1, "请选择一个 Embedding 模型"),
  chunk_size: z.coerce.number().min(100, "分块大小至少为 100").max(4096, "分块大小不能超过 4096"),
});

type FormValues = z.infer<typeof formSchema>;

interface KnowledgeDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  knowledge?: Knowledge | null;
  onSubmit: (values: FormValues) => Promise<void>;
}

export function KnowledgeDialog({
  open,
  onOpenChange,
  knowledge,
  onSubmit,
}: KnowledgeDialogProps) {
  const isEdit = !!knowledge;

  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      name: "",
      description: "",
      embed_model: "text-embedding-v4",
      chunk_size: 500,
    },
  });

  // 重置表单逻辑
  useEffect(() => {
    if (open) {
      form.reset({
        name: knowledge?.name || "",
        description: knowledge?.description || "",
        embed_model: knowledge?.embed_model || "text-embedding-v4",
        chunk_size: knowledge?.chunk_size || 500,
      });
    }
  }, [open, knowledge, form]);

  const handleSubmit = async (values: FormValues) => {
    try {
      await onSubmit(values);
      onOpenChange(false);
    } catch (error) {
      console.error(error);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-[600px] p-0 overflow-hidden gap-0">
        {/* 顶部标题区 */}
        <DialogHeader className="p-6 pb-4 bg-muted/10 border-b">
          <DialogTitle className="flex items-center gap-2 text-xl">
            {isEdit ? <Settings2 className="w-5 h-5 text-primary" /> : <Database className="w-5 h-5 text-primary" />}
            {isEdit ? "编辑知识库配置" : "创建新知识库"}
          </DialogTitle>
          <DialogDescription>
            {isEdit
              ? "修改知识库的基础信息。注意：索引配置通常不可变更。"
              : "配置知识库名称、描述以及底层索引参数。"}
          </DialogDescription>
        </DialogHeader>

        <Form {...form}>
          <form onSubmit={form.handleSubmit(handleSubmit)} className="flex flex-col gap-6 p-6">
            
            {/* 第一部分：基础信息 */}
            <div className="space-y-4">
              <FormField
                control={form.control}
                name="name"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="text-foreground font-medium">知识库名称</FormLabel>
                    <FormControl>
                      <Input 
                        placeholder="例如：2024年产品技术文档" 
                        className="h-10" 
                        {...field} 
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel className="text-foreground font-medium">描述信息</FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="请输入关于此知识库的简要描述..."
                        className="resize-none min-h-[80px]"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* 分割线与标题 */}
            <div className="relative">
              <div className="absolute inset-0 flex items-center">
                <span className="w-full border-t" />
              </div>
              <div className="relative flex justify-center text-xs uppercase">
                <span className="bg-background px-2 text-muted-foreground font-medium">
                  高级索引配置
                </span>
              </div>
            </div>

            {/* 第二部分：高级配置 (Grid布局 - 对称设计) */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
              <FormField
                control={form.control}
                name="embed_model"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="flex items-center gap-1.5 text-foreground font-medium h-5">
                      <Cpu className="w-3.5 h-3.5 text-muted-foreground" /> 
                      Embedding 模型
                    </FormLabel>
                    <Select
                      onValueChange={field.onChange}
                      defaultValue={field.value}
                      disabled={isEdit} 
                    >
                      <FormControl>
                        <SelectTrigger className="h-10 bg-muted/20 border-input transition-colors hover:bg-muted/30 hover:border-primary/50">
                          <SelectValue placeholder="选择模型" />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        <SelectItem value="text-embedding-v4">
                          <div className="flex items-center gap-2">
                            <span>Text Embedding V4</span>
                            <Badge variant="secondary" className="text-[10px] h-4 px-1 py-0 leading-none font-normal text-muted-foreground">推荐</Badge>
                          </div>
                        </SelectItem>
                        <SelectItem value="text-embedding-v3">
                          <div className="flex items-center gap-2">
                            <span>Text Embedding V3</span>
                          </div>
                        </SelectItem>
                      </SelectContent>
                    </Select>
                    {/* 统一 FormDescription 高度，确保对齐 */}
                    <FormDescription className="text-[11px] min-h-[16px]">
                      {isEdit ? "创建后不可修改" : "决定语义检索的核心效果"}
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <FormField
                control={form.control}
                name="chunk_size"
                render={({ field }) => (
                  <FormItem className="space-y-2">
                    <FormLabel className="flex items-center gap-1.5 text-foreground font-medium h-5">
                      <Layers className="w-3.5 h-3.5 text-muted-foreground" />
                      分块大小 (Chunk Size)
                    </FormLabel>
                    <FormControl>
                      <div className="relative">
                        <Input 
                          type="number" 
                          className="h-10 bg-muted/20 pr-12 transition-colors hover:bg-muted/30 hover:border-primary/50" 
                          {...field} 
                        />
                        <span className="absolute right-3 top-0 bottom-0 flex items-center text-xs text-muted-foreground pointer-events-none">
                          Tokens
                        </span>
                      </div>
                    </FormControl>
                    <FormDescription className="text-[11px] min-h-[16px]">
                      建议范围: 500 - 1000
                    </FormDescription>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>

            {/* 底部按钮区 */}
            <DialogFooter className="pt-2 sm:justify-end gap-3">
              <Button 
                type="button" 
                variant="outline" 
                onClick={() => onOpenChange(false)}
                className="h-10 px-6 border-muted-foreground/20 hover:bg-muted"
              >
                取消
              </Button>
              <Button 
                type="submit" 
                className="h-10 px-6 shadow-md transition-all hover:shadow-lg"
                disabled={form.formState.isSubmitting}
              >
                {form.formState.isSubmitting ? (
                  <>
                    <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                    处理中...
                  </>
                ) : (
                  isEdit ? "保存配置" : "立即创建"
                )}
              </Button>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  );
}