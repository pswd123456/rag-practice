"use client";

import {
  Radar,
  RadarChart,
  PolarGrid,
  PolarAngleAxis,
  PolarRadiusAxis,
  ResponsiveContainer,
  Tooltip
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Experiment } from "@/lib/types";

interface MetricRadarProps {
  experiment: Experiment;
  className?: string;
}

export function MetricRadar({ experiment, className }: MetricRadarProps) {
  // 1. 定义原始数据映射
  const rawData = [
    { subject: "Faithfulness", A: experiment.faithfulness, fullMark: 1 },
    { subject: "Ans Relevancy", A: experiment.answer_relevancy, fullMark: 1 },
    { subject: "Ctx Recall", A: experiment.context_recall, fullMark: 1 },
    { subject: "Ctx Precision", A: experiment.context_precision, fullMark: 1 },
    { subject: "Ans Accuracy", A: experiment.answer_accuracy, fullMark: 1 },
    { subject: "Entity Recall", A: experiment.context_entities_recall, fullMark: 1 },
  ];

  // 2. 过滤掉分数为 0 或无效的指标
  // 这样雷达图上将只显示有实际得分的维度
  const data = rawData.filter(item => item.A > 0);

  return (
    <Card className={className}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-center">Ragas Metrics Visualization</CardTitle>
      </CardHeader>
      <CardContent className="h-[300px] w-full">
        {data.length > 0 ? (
          <ResponsiveContainer width="100%" height="100%">
            <RadarChart cx="50%" cy="50%" outerRadius="70%" data={data}>
              <PolarGrid className="stroke-muted" />
              <PolarAngleAxis 
                dataKey="subject" 
                tick={{ fill: "var(--foreground)", fontSize: 10 }} 
              />
              <PolarRadiusAxis angle={30} domain={[0, 1]} tick={false} axisLine={false} />
              <Radar
                name="Metrics"
                dataKey="A"
                stroke="hsl(var(--primary))"
                strokeWidth={2}
                fill="hsl(var(--primary))"
                fillOpacity={0.3}
              />
              <Tooltip 
                contentStyle={{ 
                  backgroundColor: "hsl(var(--popover))", 
                  borderColor: "hsl(var(--border))",
                  color: "hsl(var(--popover-foreground))",
                  fontSize: "12px",
                  borderRadius: "6px"
                }}
                formatter={(value: number) => value.toFixed(3)}
              />
            </RadarChart>
          </ResponsiveContainer>
        ) : (
          <div className="h-full flex items-center justify-center text-muted-foreground text-sm">
            暂无有效评分数据
          </div>
        )}
      </CardContent>
    </Card>
  );
}