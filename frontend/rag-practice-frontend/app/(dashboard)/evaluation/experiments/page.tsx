"use client";

import { useEffect, useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import * as z from "zod";
import { format } from "date-fns";
import { toast } from "sonner";
import { 
  Loader2, 
  Play,
  ChevronDown,
  ChevronUp,
  BarChart2,
  Trash2
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

import { useAuthStore } from "@/lib/store";
import { evaluationService } from "@/lib/services/evaluation";
import { knowledgeService } from "@/lib/services/knowledge";
import { Experiment, Knowledge, Testset } from "@/lib/types";
import { MetricRadar } from "@/components/business/evaluation/metric-radar";

// [Fix] 使用 z.number() 替代 z.coerce.number()
// 因为我们在前端组件 onChange 中已经手动转换了类型，使用严格类型可以避免 RHF 类型推断错误
const formSchema = z.object({
  knowledge_id: z.number().min(1, "请选择知识库"),
  testset_id: z.number().min(1, "请选择测试集"),
  student_model: z.string(),
  judge_model: z.string(),
  top_k: z.number().min(1).max(20).default(3),
  strategy: z.enum(["hybrid", "dense", "rerank"]).default("hybrid"),
});

// 推断类型
type FormValues = z.infer<typeof formSchema>;

export default function ExperimentsPage() {
  const { user } = useAuthStore();
  const [data, setData] = useState<Experiment[]>([]);
  const [loading, setLoading] = useState(true);
  
  // Create Dialog
  const [isDialogOpen, setIsDialogOpen] = useState(false);
  const [knowledges, setKnowledges] = useState<Knowledge[]>([]);
  const [testsets, setTestsets] = useState<Testset[]>([]);
  
  // Expanded Rows for Radar Chart
  const [expandedRows, setExpandedRows] = useState<number[]>([]);

  // [Fix] 显式指定泛型 FormValues
  const form = useForm<FormValues>({
    resolver: zodResolver(formSchema),
    defaultValues: {
      knowledge_id: 0, // 初始值 0，匹配 number 类型
      testset_id: 0,   // 初始值 0
      student_model: "qwen-max",
      judge_model: "qwen-max",
      top_k: 3,
      strategy: "hybrid"
    },
  });

  const fetchData = async () => {
    try {
      const res = await evaluationService.getExperiments();
      setData(res);
    } catch (err) {
      toast.error("获取实验列表失败");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    if (isDialogOpen) {
      Promise.all([
        knowledgeService.getAll(),
        evaluationService.getTestsets()
      ]).then(([kbs, tss]) => {
        setKnowledges(kbs);
        setTestsets(tss.filter(t => t.status === 'COMPLETED'));
      });
    }
  }, [isDialogOpen]);

  const onSubmit = async (values: FormValues) => {
    try {
      const runtime_params = {
        student_model: values.student_model,
        judge_model: values.judge_model,
        top_k: values.top_k,
        strategy: values.strategy
      };

      await evaluationService.createExperiment({
        knowledge_id: values.knowledge_id,
        testset_id: values.testset_id,
        runtime_params
      });
      
      toast.success("实验已开始运行");
      setIsDialogOpen(false);
      fetchData();
    } catch (error: any) {
      toast.error("提交失败: " + error.message);
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("确定要删除此实验记录吗？")) return;
    try {
      await evaluationService.deleteExperiment(id);
      setData(prev => prev.filter(e => e.id !== id));
      toast.success("删除成功");
    } catch (e) {
      toast.error("删除失败");
    }
  };

  const toggleRow = (id: number) => {
    setExpandedRows(prev => 
      prev.includes(id) ? prev.filter(r => r !== id) : [...prev, id]
    );
  };

  const canRun = user?.is_superuser;

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-medium">实验运行记录</h2>
        <Button onClick={() => setIsDialogOpen(true)} disabled={!canRun}>
          <Play className="mr-2 h-4 w-4" /> 运行新实验
        </Button>
      </div>

      <div className="border rounded-md bg-background">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead className="w-[50px]"></TableHead>
              <TableHead>ID</TableHead>
              <TableHead>知识库 ID</TableHead>
              <TableHead>测试集 ID</TableHead>
              <TableHead>策略 / 模型</TableHead>
              <TableHead>状态</TableHead>
              <TableHead>运行时间</TableHead>
              <TableHead className="text-right">操作</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading ? (
              <TableRow>
                <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">加载中...</TableCell>
              </TableRow>
            ) : data.length === 0 ? (
              <TableRow>
                <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">暂无实验记录</TableCell>
              </TableRow>
            ) : (
              data.map((exp) => (
                <>
                  <TableRow key={exp.id} className={expandedRows.includes(exp.id) ? "border-b-0 bg-muted/50" : ""}>
                    <TableCell>
                      <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => toggleRow(exp.id)}>
                        {expandedRows.includes(exp.id) ? <ChevronUp className="h-4 w-4"/> : <ChevronDown className="h-4 w-4"/>}
                      </Button>
                    </TableCell>
                    <TableCell>#{exp.id}</TableCell>
                    <TableCell>KB-{exp.knowledge_id}</TableCell>
                    <TableCell>TS-{exp.testset_id}</TableCell>
                    <TableCell>
                      <div className="flex flex-col text-xs text-muted-foreground gap-1">
                        <Badge variant="outline" className="w-fit">{exp.runtime_params?.strategy}</Badge>
                        <span>{exp.runtime_params?.student_model}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      {exp.status === "RUNNING" ? (
                        <Badge variant="secondary" className="animate-pulse"><Loader2 className="w-3 h-3 mr-1 animate-spin"/> Running</Badge>
                      ) : exp.status === "COMPLETED" ? (
                        <Badge className="bg-green-500">Completed</Badge>
                      ) : (
                        <Badge variant="destructive">Failed</Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {format(new Date(exp.created_at), "MM-dd HH:mm")}
                    </TableCell>
                    <TableCell className="text-right">
                      <Button variant="ghost" size="icon" onClick={() => handleDelete(exp.id)}>
                        <Trash2 className="h-4 w-4 text-muted-foreground hover:text-destructive" />
                      </Button>
                    </TableCell>
                  </TableRow>
                  
                  {/* Expanded Content: Radar Chart & Metrics */}
                  {expandedRows.includes(exp.id) && (
                    <TableRow>
                      <TableCell colSpan={8} className="p-0 border-b">
                        <div className="p-6 bg-muted/20 flex flex-col md:flex-row gap-8 items-center justify-center">
                          {exp.status === "COMPLETED" ? (
                            <>
                              <div className="flex-1 max-w-md w-full">
                                <MetricRadar experiment={exp} />
                              </div>
                              <div className="flex-1 grid grid-cols-2 gap-4 max-w-md">
                                <MetricCard label="Faithfulness" value={exp.faithfulness} />
                                <MetricCard label="Answer Relevancy" value={exp.answer_relevancy} />
                                <MetricCard label="Context Recall" value={exp.context_recall} />
                                <MetricCard label="Context Precision" value={exp.context_precision} />
                              </div>
                            </>
                          ) : (
                            <div className="py-8 text-muted-foreground flex items-center gap-2">
                              <BarChart2 className="w-5 h-5" />
                              {exp.status === "FAILED" ? "实验失败，无法查看图表" : "实验运行中，请稍后..."}
                              {exp.error_message && <div className="text-xs text-destructive mt-2">{exp.error_message}</div>}
                            </div>
                          )}
                        </div>
                      </TableCell>
                    </TableRow>
                  )}
                </>
              ))
            )}
          </TableBody>
        </Table>
      </div>

      {/* New Experiment Dialog */}
      <Dialog open={isDialogOpen} onOpenChange={setIsDialogOpen}>
        <DialogContent className="max-w-xl">
          <DialogHeader>
            <DialogTitle>发起新实验</DialogTitle>
            <DialogDescription>
              配置检索策略和模型，对指定知识库进行 Ragas 评估。
            </DialogDescription>
          </DialogHeader>

          <Form {...form}>
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="knowledge_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>目标知识库</FormLabel>
                      <Select 
                        onValueChange={(val) => field.onChange(Number(val))}
                        // 转换 0 为 undefined 以显示 placeholder，或者 toString()
                        value={field.value ? field.value.toString() : undefined} 
                      >
                        <FormControl><SelectTrigger><SelectValue placeholder="选择..." /></SelectTrigger></FormControl>
                        <SelectContent>
                          {knowledges.map(kb => <SelectItem key={kb.id} value={kb.id.toString()}>{kb.name}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                
                <FormField
                  control={form.control}
                  name="testset_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>测试集</FormLabel>
                      <Select 
                        onValueChange={(val) => field.onChange(Number(val))}
                        value={field.value ? field.value.toString() : undefined}
                      >
                        <FormControl><SelectTrigger><SelectValue placeholder="选择..." /></SelectTrigger></FormControl>
                        <SelectContent>
                          {testsets.map(ts => <SelectItem key={ts.id} value={ts.id.toString()}>{ts.name}</SelectItem>)}
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="strategy"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>检索策略</FormLabel>
                      <Select onValueChange={field.onChange} defaultValue={field.value}>
                        <FormControl><SelectTrigger><SelectValue/></SelectTrigger></FormControl>
                        <SelectContent>
                          <SelectItem value="hybrid">Hybrid (Vector + Keyword)</SelectItem>
                          <SelectItem value="rerank">Rerank (Hybrid + BGE-Reranker)</SelectItem>
                          <SelectItem value="dense">Dense Only</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />

                <FormField
                  control={form.control}
                  name="top_k"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>Top K ({field.value})</FormLabel>
                      <FormControl>
                        {/* 手动转换 value 为 number */}
                        <Input type="number" {...field} onChange={e => field.onChange(Number(e.target.value))} />
                      </FormControl>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <div className="grid grid-cols-2 gap-4">
                <FormField
                  control={form.control}
                  name="student_model"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>被测模型 (Student)</FormLabel>
                      <Select onValueChange={field.onChange} defaultValue={field.value}>
                        <FormControl><SelectTrigger><SelectValue/></SelectTrigger></FormControl>
                        <SelectContent>
                          <SelectItem value="qwen-max">Qwen Max</SelectItem>
                          <SelectItem value="qwen-plus">Qwen Plus</SelectItem>
                          <SelectItem value="deepseek-chat">DeepSeek V3</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormMessage />
                    </FormItem>
                  )}
                />
                
                <FormField
                  control={form.control}
                  name="judge_model"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>裁判模型 (Judge)</FormLabel>
                      <Select onValueChange={field.onChange} defaultValue={field.value}>
                        <FormControl><SelectTrigger><SelectValue/></SelectTrigger></FormControl>
                        <SelectContent>
                          <SelectItem value="qwen-max">Qwen Max (推荐)</SelectItem>
                          <SelectItem value="deepseek-chat">DeepSeek V3</SelectItem>
                        </SelectContent>
                      </Select>
                      <FormDescription className="text-[10px]">用于 Ragas 打分的 LLM</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <DialogFooter>
                <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>取消</Button>
                <Button type="submit">启动实验</Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function MetricCard({ label, value }: { label: string, value: number }) {
  return (
    <div className="bg-background p-3 rounded border flex flex-col items-center justify-center">
      <span className="text-2xl font-bold text-primary">{(value * 100).toFixed(1)}%</span>
      <span className="text-xs text-muted-foreground">{label}</span>
    </div>
  );
}