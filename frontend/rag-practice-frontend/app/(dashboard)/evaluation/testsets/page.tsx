"use client";

import { useEffect, useState, useMemo } from "react";
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
  Clock,
  Search,
  CheckSquare,
  Square
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
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Separator } from "@/components/ui/separator";

import { useAuthStore } from "@/lib/store";
import { evaluationService } from "@/lib/services/evaluation";
import { knowledgeService, RAGDocument } from "@/lib/services/knowledge";
import { Testset, Knowledge } from "@/lib/types";
import { cn } from "@/lib/utils";

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
  
  // Doc Selection Filtering
  const [searchQuery, setSearchQuery] = useState("");

  const form = useForm({
    resolver: zodResolver(formSchema),
    defaultValues: {
      name: "",
      knowledge_id: undefined as unknown as number,
      doc_ids: [] as number[],
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
    // 轮询刷新生成中的任务
    const interval = setInterval(() => {
      setData(current => {
        if (current.some(t => t.status === "GENERATING")) {
          fetchData();
        }
        return current;
      });
    }, 5000);
    return () => clearInterval(interval);
  }, []);

  useEffect(() => {
    if (isDialogOpen) {
      const loadKBs = async () => {
        const kbs = await knowledgeService.getAll();
        setKnowledges(kbs);
      };
      loadKBs();
    }
  }, [isDialogOpen]);

  const selectedKbId = form.watch("knowledge_id");
  
  useEffect(() => {
    if (selectedKbId) {
      setLoadingDocs(true);
      setKbDocuments([]); 
      form.setValue("doc_ids", []);
      setSearchQuery(""); // 重置搜索
      
      knowledgeService.getDocuments(Number(selectedKbId))
        .then(docs => setKbDocuments(docs))
        .finally(() => setLoadingDocs(false));
    }
  }, [selectedKbId, form]);

  // Filtered Docs Logic
  const filteredDocs = useMemo(() => {
    if (!searchQuery) return kbDocuments;
    return kbDocuments.filter(doc => 
      doc.filename.toLowerCase().includes(searchQuery.toLowerCase())
    );
  }, [kbDocuments, searchQuery]);

  // Toggle All Logic
  const handleToggleAll = () => {
    const currentSelected = form.getValues("doc_ids");
    const filteredIds = filteredDocs.map(d => d.id);
    
    // Check if all filtered are currently selected
    const allSelected = filteredIds.every(id => currentSelected.includes(id));
    
    if (allSelected) {
      // Deselect filtered docs
      const newSelection = currentSelected.filter(id => !filteredIds.includes(id));
      form.setValue("doc_ids", newSelection);
    } else {
      // Select all filtered docs (merge)
      const newSelection = Array.from(new Set([...currentSelected, ...filteredIds]));
      form.setValue("doc_ids", newSelection);
    }
  };

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
      case "COMPLETED": return <Badge className="bg-green-600 hover:bg-green-700"><CheckCircle2 className="w-3 h-3 mr-1"/> 完成</Badge>;
      case "GENERATING": return <Badge variant="secondary" className="animate-pulse"><Loader2 className="w-3 h-3 mr-1 animate-spin"/> 生成中</Badge>;
      case "FAILED": return <Badge variant="destructive"><AlertCircle className="w-3 h-3 mr-1"/> 失败</Badge>;
      default: return <Badge variant="outline"><Clock className="w-3 h-3 mr-1"/> {status}</Badge>;
    }
  };

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

      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="sm:max-w-[700px]">
          <DialogHeader>
            <DialogTitle>生成新测试集 (Ragas)</DialogTitle>
            <DialogDescription>
              配置生成模型并选择源文档，系统将自动生成问答对（Golden Dataset）。
            </DialogDescription>
          </DialogHeader>

          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
              
              {/* Section 1: Basic Config */}
              <div className="space-y-4">
                <h3 className="text-sm font-medium text-muted-foreground mb-2 uppercase tracking-wider">基础配置</h3>
                <div className="grid grid-cols-2 gap-4">
                  <FormField
                    control={form.control}
                    name="name"
                    render={({ field }) => (
                      <FormItem>
                        <FormLabel>测试集名称</FormLabel>
                        <FormControl>
                          <Input placeholder="例如：Qwen2.5 文档测试" {...field} />
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
                        <FormLabel>生成模型 (Generator)</FormLabel>
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
                      <FormLabel>数据来源知识库</FormLabel>
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
              </div>

              <Separator />

              {/* Section 2: Document Selection */}
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-sm font-medium text-muted-foreground uppercase tracking-wider">
                    文档选择 <span className="text-primary normal-case">({form.watch("doc_ids").length} 已选)</span>
                  </h3>
                  
                  <div className="flex gap-2">
                    {kbDocuments.length > 0 && (
                      <>
                        <div className="relative">
                          <Search className="absolute left-2 top-1.5 h-4 w-4 text-muted-foreground" />
                          <Input 
                            placeholder="筛选文档..." 
                            className="h-7 pl-8 w-[150px] text-xs"
                            value={searchQuery}
                            onChange={(e) => setSearchQuery(e.target.value)}
                          />
                        </div>
                        <Button 
                          type="button" 
                          variant="ghost" 
                          size="sm" 
                          className="h-7 text-xs"
                          onClick={handleToggleAll}
                        >
                          全选/反选
                        </Button>
                      </>
                    )}
                  </div>
                </div>

                <FormField
                  control={form.control}
                  name="doc_ids"
                  render={() => (
                    <FormItem>
                      <div className="border rounded-md bg-muted/10 h-[280px] flex flex-col">
                        {loadingDocs ? (
                          <div className="flex-1 flex items-center justify-center text-muted-foreground flex-col gap-2">
                            <Loader2 className="h-6 w-6 animate-spin" />
                            <span className="text-sm">正在加载文档列表...</span>
                          </div>
                        ) : !selectedKbId ? (
                          <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">
                            请先在上方选择一个知识库
                          </div>
                        ) : kbDocuments.length === 0 ? (
                          <div className="flex-1 flex items-center justify-center text-muted-foreground text-sm">
                            该知识库暂无文档
                          </div>
                        ) : (
                          <ScrollArea className="flex-1">
                            <div className="p-2 grid grid-cols-1 gap-1">
                              {filteredDocs.length === 0 ? (
                                <div className="py-8 text-center text-xs text-muted-foreground">未找到匹配文档</div>
                              ) : (
                                filteredDocs.map((doc) => {
                                  const isSelected = form.watch("doc_ids").includes(doc.id);
                                  return (
                                    <div
                                      key={doc.id}
                                      className={cn(
                                        "flex items-center space-x-3 p-3 rounded-md border cursor-pointer transition-all hover:shadow-sm",
                                        isSelected 
                                          ? "bg-primary/5 border-primary/40" 
                                          : "bg-background border-transparent hover:bg-muted/50 hover:border-border"
                                      )}
                                      onClick={() => {
                                        const current = form.getValues("doc_ids");
                                        if (isSelected) {
                                          form.setValue("doc_ids", current.filter(id => id !== doc.id));
                                        } else {
                                          form.setValue("doc_ids", [...current, doc.id]);
                                        }
                                      }}
                                    >
                                      {/* Custom Checkbox */}
                                      <div className={cn(
                                        "w-4 h-4 rounded border flex items-center justify-center shrink-0 transition-colors",
                                        isSelected ? "bg-primary border-primary text-primary-foreground" : "border-muted-foreground"
                                      )}>
                                        {isSelected && <CheckSquare className="w-3 h-3" />}
                                      </div>
                                      
                                      <div className="flex-1 min-w-0 flex flex-col">
                                        <div className="flex items-center gap-2">
                                          <FileText className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                                          <span className="text-sm font-medium truncate" title={doc.filename}>{doc.filename}</span>
                                        </div>
                                        <div className="text-[10px] text-muted-foreground pl-5.5 flex gap-2">
                                          <span>{format(new Date(doc.created_at), "yyyy-MM-dd")}</span>
                                          <span>•</span>
                                          <span>{doc.status}</span>
                                        </div>
                                      </div>
                                    </div>
                                  );
                                })
                              )}
                            </div>
                          </ScrollArea>
                        )}
                      </div>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

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