"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { format } from "date-fns";
import { toast } from "sonner";
import { 
  Loader2, 
  Plus, 
  Trash2, 
  FileText, 
  CheckCircle2, 
  AlertCircle,
  Clock 
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
  DialogFooter,
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
// import { Checkbox } from "@/components/ui/checkbox"; 
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

import { useAuthStore } from "@/lib/store";
import { evaluationService } from "@/lib/services/evaluation";
import { knowledgeService, RAGDocument } from "@/lib/services/knowledge";
import { Testset, Knowledge } from "@/lib/types";

// Schema for creating testset
const formSchema = z.object({
  name: z.string().min(2, "名称至少 2 个字符"),
  knowledge_id: z.coerce.number().min(1, "请选择知识库"),
  doc_ids: z.array(z.number()).min(1, "请至少选择一个文档"),
  generator_llm: z.string(),
});

export default function TestsetsPage() {
  const { user } = useAuthStore();
  const [data, setData] = useState<Testset[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Dialog States
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [knowledges, setKnowledges] = useState<Knowledge[]>([]);
  const [kbDocuments, setKbDocuments] = useState<RAGDocument[]>([]);
  const [loadingDocs, setLoadingDocs] = useState(false);

  // Form
  // [Fix] 移除显式泛型 <z.infer<typeof formSchema>>
  // 原因：zodResolver 会自动推断输入/输出类型，显式泛型会导致与 z.coerce 的输入类型冲突
  const form = useForm({
    resolver: zodResolver(formSchema),
    defaultValues: {
      name: "",
      // @ts-ignore - 初始值为 undefined 以便 Select 显示 placeholder，虽然 schema 要求 number
      knowledge_id: undefined,
      doc_ids: [],
      generator_llm: "qwen-max",
    },
  });

  const fetchData = async () => {
    try {
      const res = await evaluationService.getTestsets();
      setData(res);
    } catch (err) {
      toast.error("获取测试集列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  // Fetch KBs when dialog opens
  useEffect(() => {
    if (isDialogOpen) {
      const loadKBs = async () => {
        const kbs = await knowledgeService.getAll();
        setKnowledges(kbs);
      };
      loadKBs();
    }
  }, [isDialogOpen]);

  // Fetch docs when KB changes
  const selectedKbId = form.watch("knowledge_id");
  useEffect(() => {
    if (selectedKbId) {
      setLoadingDocs(true);
      setKbDocuments([]); // clear previous
      form.setValue("doc_ids", []); // clear selection
      
      // [Fix] 显式转换为 Number，解决 TypeScript 类型检查错误
      knowledgeService.getDocuments(Number(selectedKbId))
        .then(docs => setKbDocuments(docs))
        .finally(() => setLoadingDocs(false));
    }
  }, [selectedKbId, form]);

  const onSubmit = async (values: z.infer<typeof formSchema>) => {
    try {
      await evaluationService.createTestset({
        name: values.name,
        source_doc_ids: values.doc_ids,
        generator_llm: values.generator_llm
      });
      toast.success("测试集生成任务已提交");
      setIsDialogOpen(false);
      form.reset();
      fetchData();
    } catch (error: any) {
      toast.error("创建失败: " + (error.response?.data?.detail || error.message));
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("确定要删除此测试集吗？")) return;
    try {
      await evaluationService.deleteTestset(id);
      toast.success("删除成功");
      setData(prev => prev.filter(item => item.id !== id));
    } catch (error) {
      toast.error("删除失败");
    }
  };

  const getStatusBadge = (status: string) => {
    switch(status) {
      case "COMPLETED": return <Badge className="bg-green-500 hover:bg-green-600"><CheckCircle2 className="w-3 h-3 mr-1"/> 完成</Badge>;
      case "GENERATING": return <Badge variant="secondary" className="animate-pulse"><Loader2 className="w-3 h-3 mr-1 animate-spin"/> 生成中</Badge>;
      case "FAILED": return <Badge variant="destructive"><AlertCircle className="w-3 h-3 mr-1"/> 失败</Badge>;
      default: return <Badge variant="outline"><Clock className="w-3 h-3 mr-1"/> {status}</Badge>;
    }
  };

  // 权限控制：仅 SuperUser 可创建
  const canCreate = user?.is_superuser;

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-medium">测试集列表</h2>
        <Button onClick={() => setIsDialogOpen(true)} disabled={!canCreate}>
          <Plus className="mr-2 h-4 w-4" /> 生成新测试集
        </Button>
      </div>

      <div className="border rounded-md bg-background">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[100px]">ID</TableHead>
              <TableHead>名称</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>创建时间</TableHead>
              <TableHead>描述</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">加载中...</TableCell>
              </TableRow>
            ) : data.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="text-center py-8 text-muted-foreground">暂无测试集</TableCell>
              </TableRow>
            ) : (
              data.map((item) => (
                <TableRow key={item.id}>
                  <TableCell>#{item.id}</TableCell>
                  <TableCell className="font-medium">{item.name}</TableCell>
                  <TableCell>{getStatusBadge(item.status)}</TableCell>
                  <TableCell className="text-muted-foreground text-xs">
                    {format(new Date(item.created_at), "MM-dd HH:mm")}
                  </TableCell>
                  <TableCell className="text-muted-foreground text-xs max-w-[200px] truncate" title={item.description || ""}>
                    {item.description || "-"}
                  </TableCell>
                  <TableCell className="text-right">
                    <Button variant="ghost" size="icon" onClick={() => handleDelete(item.id)}>
                      <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                    </Button>
                  </TableCell>
                </TableRow>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* Create Dialog */}
      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="max-w-2xl">
          <DialogHeader>
            <DialogTitle>生成新测试集 (Ragas)</DialogTitle>
            <DialogDescription>
              选择文档，使用 LLM 自动生成 QA 对作为评估基准（Golden Dataset）。
            </DialogDescription>
          </DialogHeader>

          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="name"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>测试集名称</FormLabel>
                      <FormControl>
                        <Input placeholder="e.g. Qwen2.5 Doc Test" {...field} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                
                <FormField
                  control={form.control}
                  name="generator_llm"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>生成模型</FormLabel>
                      <Select onValueChange={field.onChange} defaultValue={field.value}>
                        <FormControl>
                          <SelectTrigger>
                            <SelectValue placeholder="选择模型" />
                          </SelectTrigger>
                        </FormControl>
                        <SelectContent>
                          <SelectItem value="qwen-max">Qwen Max (推荐)</SelectItem>
                          <SelectItem value="qwen-plus">Qwen Plus</SelectItem>
                          <SelectItem value="deepseek-chat">DeepSeek V3</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription className="text-xs">
                        用于生成问题和答案的模型。
                      </FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <FormField
                control={form.control}
                name="knowledge_id"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>选择来源知识库</FormLabel>
                    <Select 
                      onValueChange={(val) => field.onChange(Number(val))} 
                      value={field.value?.toString()}
                    >
                      <FormControl>
                        <SelectTrigger>
                          <SelectValue placeholder="选择知识库..." />
                        </SelectTrigger>
                      </FormControl>
                      <SelectContent>
                        {knowledges.map(kb => (
                          <SelectItem key={kb.id} value={kb.id.toString()}>{kb.name}</SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                    <FormMessage />
                  </FormItem>
                )}
              />

              {/* Document Selection Area */}
              <FormField
                control={form.control}
                name="doc_ids"
                render={() => (
                  <FormItem>
                    <FormLabel>选择文档 ({form.watch("doc_ids")?.length || 0} 已选)</FormLabel>
                    <div className="border rounded-md p-2 h-[200px] overflow-hidden bg-muted/20">
                      {loadingDocs ? (
                        <div className="h-full flex items-center justify-center text-muted-foreground">
                          <Loader2 className="h-4 w-4 animate-spin mr-2" /> 加载文档中...
                        </div>
                      ) : !selectedKbId ? (
                        <div className="h-full flex items-center justify-center text-muted-foreground text-sm">
                          请先选择知识库
                        </div>
                      ) : kbDocuments.length === 0 ? (
                        <div className="h-full flex items-center justify-center text-muted-foreground text-sm">
                          该知识库暂无文档
                        </div>
                      ) : (
                        <ScrollArea className="h-full">
                          <div className="space-y-1 p-1">
                            {kbDocuments.map((doc) => {
                              const isSelected = form.watch("doc_ids").includes(doc.id);
                              return (
                                <div
                                  key={doc.id}
                                  className={`flex items-center space-x-2 p-2 rounded cursor-pointer transition-colors ${isSelected ? 'bg-primary/10' : 'hover:bg-muted'}`}
                                  onClick={() => {
                                    const current = form.getValues("doc_ids");
                                    if (isSelected) {
                                      form.setValue("doc_ids", current.filter(id => id !== doc.id));
                                    } else {
                                      form.setValue("doc_ids", [...current, doc.id]);
                                    }
                                  }}
                                >
                                  <div className={`w-4 h-4 rounded border flex items-center justify-center ${isSelected ? 'bg-primary border-primary' : 'border-muted-foreground'}`}>
                                    {isSelected && <div className="w-2 h-2 bg-white rounded-full" />}
                                  </div>
                                  <FileText className="h-4 w-4 text-muted-foreground" />
                                  <span className="text-sm truncate flex-1">{doc.filename}</span>
                                  <Badge variant="outline" className="text-[10px]">{doc.status}</Badge>
                                </div>
                              );
                            })}
                          </div>
                        </ScrollArea>
                      )}
                    </div>
                    <FormMessage />
                  </FormItem>
                )}
              />

              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>取消</Button>
                <Button type="submit" disabled={form.formState.isSubmitting}>
                  {form.formState.isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  开始生成
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
    </div>
  );
}