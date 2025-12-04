"use client";

import { useEffect, useState, useRef, useCallback } from "react";
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
  Trash2,
  Clock,
  CheckCircle2,
  AlertCircle,
  RefreshCw
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
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "@/components/ui/tooltip";

import { useAuthStore } from "@/lib/store";
import { evaluationService } from "@/lib/services/evaluation";
import { knowledgeService } from "@/lib/services/knowledge";
import { Experiment, Knowledge, Testset } from "@/lib/types";
import { MetricRadar } from "@/components/business/evaluation/metric-radar";

// --- Constants & Config ---

const METRIC_CONFIG = [
  { key: "faithfulness", label: "Faithfulness" },
  { key: "answer_relevancy", label: "Answer Relevancy" },
  { key: "context_recall", label: "Context Recall" },
  { key: "context_precision", label: "Context Precision" },
  { key: "answer_accuracy", label: "Answer Accuracy" },
  { key: "context_entities_recall", label: "Entity Recall" },
] as const;

const MODEL_OPTIONS = [
  { value: "qwen-flash", label: "Qwen Flash" },
  { value: "qwen-plus", label: "Qwen Plus" },
  { value: "qwen-max", label: "Qwen Max (推荐)" },
  { value: "deepseek-chat", label: "DeepSeek V3" },
  { value: "deepseek-reasoner", label: "DeepSeek R1" },
  { value: "google/gemini-3-pro-preview-free", label: "Gemini Pro" },
];

const formSchema = z.object({
  knowledge_id: z.number().min(1, "请选择知识库"),
  testset_id: z.number().min(1, "请选择测试集"),
  student_model: z.string(),
  judge_model: z.string(),
  top_k: z.number().min(1).max(20).default(3),
  strategy: z.enum(["hybrid", "dense", "rerank"]).default("hybrid"),
});

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

  // Polling control
  const pollingTimerRef = useRef<NodeJS.Timeout | null>(null);

  const form = useForm({
    resolver: zodResolver(formSchema),
    defaultValues: {
      knowledge_id: 0, 
      testset_id: 0,   
      student_model: "qwen-max",
      judge_model: "qwen-max",
      top_k: 3,
      strategy: "hybrid" as const
    },
  });

  // 核心数据获取函数
  const fetchData = useCallback(async () => {
    try {
      const res = await evaluationService.getExperiments();
      setData(res);
      return res; // 返回数据供轮询判断
    } catch (err) {
      toast.error("获取实验列表失败");
      return [];
    } finally {
      setLoading(false);
    }
  }, []);

  // 智能轮询逻辑
  const startPolling = useCallback(() => {
    // 如果已有定时器，先清除
    if (pollingTimerRef.current) clearTimeout(pollingTimerRef.current);

    pollingTimerRef.current = setTimeout(async () => {
      const currentData = await fetchData();
      
      // 检查是否有未完成的任务
      const hasActiveTasks = currentData.some(e => 
        ["PENDING", "RUNNING"].includes(e.status)
      );

      // 如果有活跃任务，继续轮询
      if (hasActiveTasks) {
        startPolling();
      }
    }, 3000); // 3秒轮询一次
  }, [fetchData]);

  // 初始化加载
  useEffect(() => {
    fetchData().then((res) => {
      // 如果初始加载就有活跃任务，启动轮询
      const hasActive = res.some(e => ["PENDING", "RUNNING"].includes(e.status));
      if (hasActive) startPolling();
    });

    return () => {
      if (pollingTimerRef.current) clearTimeout(pollingTimerRef.current);
    };
  }, [fetchData, startPolling]);

  // Dialog 打开时加载选项
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
      
      toast.success("实验任务已提交");
      setIsDialogOpen(false);
      
      // 提交后立即刷新并强制启动轮询
      setLoading(true); 
      await fetchData(); 
      startPolling(); 

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

  const renderStatusBadge = (status: string, error?: string) => {
    switch (status) {
      case "PENDING":
        return (
          <Badge variant="outline" className="bg-yellow-50 text-yellow-700 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-400 dark:border-yellow-800">
            <Clock className="w-3 h-3 mr-1" /> 等待中
          </Badge>
        );
      case "RUNNING":
        return (
          <Badge variant="secondary" className="animate-pulse bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300">
            <Loader2 className="w-3 h-3 mr-1 animate-spin"/> 运行中
          </Badge>
        );
      case "COMPLETED":
        return (
          <Badge className="bg-green-600 hover:bg-green-700">
            <CheckCircle2 className="w-3 h-3 mr-1"/> 完成
          </Badge>
        );
      case "FAILED":
        return (
          <TooltipProvider>
            <Tooltip>
              <TooltipTrigger>
                <Badge variant="destructive" className="cursor-help">
                  <AlertCircle className="w-3 h-3 mr-1"/> 失败
                </Badge>
              </TooltipTrigger>
              <TooltipContent className="max-w-[300px]">
                <p className="text-xs">{error || "未知错误"}</p>
              </TooltipContent>
            </Tooltip>
          </TooltipProvider>
        );
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  const canRun = user?.is_superuser;

  return (
    <div className="space-y-4">
      <div className="flex justify-between items-center">
        <h2 className="text-lg font-medium">实验运行记录</h2>
        <div className="flex gap-2">
          <Button variant="outline" size="sm" onClick={() => fetchData()}>
            <RefreshCw className="h-4 w-4 mr-2"/> 刷新
          </Button>
          <Button onClick={() => setIsDialogOpen(true)} disabled={!canRun}>
            <Play className="mr-2 h-4 w-4" /> 运行新实验
          </Button>
        </div>
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
                <TableCell colSpan={8} className="text-center py-8 text-muted-foreground">
                  <Loader2 className="w-6 h-6 animate-spin mx-auto"/>
                </TableCell>
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
                      {exp.status === "COMPLETED" && (
                        <Button variant="ghost" size="sm" className="h-6 w-6 p-0" onClick={() => toggleRow(exp.id)}>
                          {expandedRows.includes(exp.id) ? <ChevronUp className="h-4 w-4"/> : <ChevronDown className="h-4 w-4"/>}
                        </Button>
                      )}
                    </TableCell>
                    <TableCell>#{exp.id}</TableCell>
                    <TableCell>KB-{exp.knowledge_id}</TableCell>
                    <TableCell>TS-{exp.testset_id}</TableCell>
                    <TableCell>
                      <div className="flex flex-col text-xs text-muted-foreground gap-1">
                        <Badge variant="outline" className="w-fit border-primary/20 text-primary">{exp.runtime_params?.strategy || "Hybrid"}</Badge>
                        <span>{exp.runtime_params?.student_model}</span>
                      </div>
                    </TableCell>
                    <TableCell>
                      {renderStatusBadge(exp.status, exp.error_message)}
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
                  {expandedRows.includes(exp.id) && exp.status === "COMPLETED" && (
                    <TableRow>
                      <TableCell colSpan={8} className="p-0 border-b">
                        <div className="p-6 bg-muted/20 flex flex-col md:flex-row gap-8 items-center justify-center animate-in fade-in slide-in-from-top-2 duration-300">
                          <div className="flex-1 max-w-md w-full bg-background rounded-lg border shadow-sm p-4">
                            <MetricRadar experiment={exp} />
                          </div>
                          <div className="flex-1 grid grid-cols-2 lg:grid-cols-3 gap-4 max-w-2xl">
                            {/* 动态渲染存在的指标卡片 */}
                            {METRIC_CONFIG.map((metric) => {
                              // @ts-ignore
                              const val = exp[metric.key];
                              // 只有当值存在且大于0时才显示
                              if (val === undefined || val === null || val <= 0) return null;
                              
                              return (
                                <MetricCard 
                                  key={metric.key} 
                                  label={metric.label} 
                                  value={val} 
                                />
                              );
                            })}
                          </div>
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
            <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6 pt-4">
              <div className="grid grid-cols-2 gap-6">
                <FormField
                  control={form.control}
                  name="knowledge_id"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>目标知识库</FormLabel>
                      <Select 
                        onValueChange={(val) => field.onChange(Number(val))}
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

              <div className="grid grid-cols-2 gap-6">
                <FormField
                  control={form.control}
                  name="strategy"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>检索策略</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
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
                        <Input type="number" {...field} onChange={e => field.onChange(Number(e.target.value))} />
                      </FormControl>
                      <FormDescription className="text-xs">单次检索返回的切片数</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <div className="grid grid-cols-2 gap-6">
                <FormField
                  control={form.control}
                  name="student_model"
                  render={({ field }) => (
                    <FormItem>
                      <FormLabel>被测模型 (Student)</FormLabel>
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl><SelectTrigger><SelectValue/></SelectTrigger></FormControl>
                        <SelectContent>
                          {MODEL_OPTIONS.map(opt => (
                            <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                          ))}
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
                      <Select onValueChange={field.onChange} value={field.value}>
                        <FormControl><SelectTrigger><SelectValue/></SelectTrigger></FormControl>
                        <SelectContent>
                          {MODEL_OPTIONS.map(opt => (
                            <SelectItem key={opt.value} value={opt.value}>{opt.label}</SelectItem>
                          ))}
                        </SelectContent>
                      </Select>
                      <FormDescription className="text-[10px]">用于 Ragas 打分</FormDescription>
                      <FormMessage />
                    </FormItem>
                  )}
                />
              </div>

              <DialogFooter className="pt-4">
                <Button type="button" variant="outline" onClick={() => setIsDialogOpen(false)}>取消</Button>
                <Button type="submit" disabled={form.formState.isSubmitting}>
                  {form.formState.isSubmitting && <Loader2 className="mr-2 h-4 w-4 animate-spin"/>}
                  启动实验
                </Button>
              </DialogFooter>
            </form>
          </Form>
        </DialogContent>
      </Dialog>
    </div>
  );
}

function MetricCard({ label, value }: { label: string, value: number }) {
  const getScoreColor = (score: number) => {
    if (score >= 0.8) return "text-green-600 dark:text-green-400";
    if (score >= 0.5) return "text-yellow-600 dark:text-yellow-400";
    return "text-red-600 dark:text-red-400";
  };

  return (
    <div className="bg-background p-4 rounded-lg border shadow-sm flex flex-col items-center justify-center hover:bg-muted/30 transition-colors animate-in zoom-in-95 duration-200">
      <span className={`text-2xl font-bold ${getScoreColor(value)}`}>
        {(value * 100).toFixed(1)}%
      </span>
      <span className="text-[10px] text-muted-foreground uppercase tracking-wider text-center mt-1 font-medium">
        {label}
      </span>
    </div>
  );
}