"use client";

import Link from "next/link";
import useSWR from "swr";
import { swrFetcher } from "@/lib/swr-fetcher";
import type {
  AuditRunItem,
  HealthResponse,
  QueueStatsResponse,
  ThreadItem,
} from "@/lib/types";
import { formatPhoneNumber, formatTimestamp } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import {
  MessageSquare,
  ListOrdered,
  ShieldCheck,
  Cpu,
  ArrowUpRight,
  UserCheck,
  Bot,
} from "lucide-react";

export default function DashboardPage() {
  const { data: queueStats, isLoading: loadingQueue } =
    useSWR<QueueStatsResponse>("/admin/queue/stats", swrFetcher, {
      refreshInterval: 5000,
    });

  const { data: threads, isLoading: loadingThreads } = useSWR<ThreadItem[]>(
    "/admin/threads",
    swrFetcher,
    { refreshInterval: 5000 }
  );

  const { data: auditLogs, isLoading: loadingAudit } = useSWR<AuditRunItem[]>(
    "/admin/audit/logs",
    swrFetcher,
    { refreshInterval: 10000 }
  );

  const { data: health } = useSWR<HealthResponse>(
    "/admin/health",
    swrFetcher,
    { refreshInterval: 15000 }
  );

  const totalMessages =
    (queueStats?.done ?? 0) +
    (queueStats?.pending ?? 0) +
    (queueStats?.processing ?? 0) +
    (queueStats?.dead ?? 0);

  const activeThreadsCount = threads?.length ?? 0;
  const humanThreadsCount =
    threads?.filter((t) => t.mode === "human").length ?? 0;
  const botThreadsCount = activeThreadsCount - humanThreadsCount;

  const blockedRunsCount =
    auditLogs?.filter((r) => r.status === "blocked").length ?? 0;

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Page Title & Context */}
      <div>
        <h2 className="text-lg font-semibold tracking-tight text-slate-100">
          Visão Geral do Cockpit
        </h2>
        <p className="text-xs text-slate-400 mt-0.5">
          Métricas em tempo real da ingestão do WhatsApp, motor cognitivo e intervenções humanas.
        </p>
      </div>

      {/* KPI Grid */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* KPI 1: Volume */}
        <Card className="bg-slate-900/60 border-slate-800">
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0 p-4">
            <CardTitle className="text-xs font-medium text-slate-400">
              Total de Mensagens
            </CardTitle>
            <MessageSquare className="w-4 h-4 text-emerald-400" />
          </CardHeader>
          <CardContent className="p-4 pt-0">
            {loadingQueue ? (
              <Skeleton className="h-7 w-20" />
            ) : (
              <div className="text-2xl font-bold tracking-tight text-slate-100 font-mono">
                {totalMessages.toLocaleString("pt-BR")}
              </div>
            )}
            <p className="text-[11px] text-slate-500 mt-1">
              {queueStats?.done ?? 0} entregues com sucesso
            </p>
          </CardContent>
        </Card>

        {/* KPI 2: Conversas & Handoff */}
        <Card className="bg-slate-900/60 border-slate-800">
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0 p-4">
            <CardTitle className="text-xs font-medium text-slate-400">
              Conversas Ativas
            </CardTitle>
            <UserCheck className="w-4 h-4 text-amber-400" />
          </CardHeader>
          <CardContent className="p-4 pt-0">
            {loadingThreads ? (
              <Skeleton className="h-7 w-16" />
            ) : (
              <div className="text-2xl font-bold tracking-tight text-slate-100 font-mono">
                {activeThreadsCount}
              </div>
            )}
            <div className="flex items-center gap-2 mt-1 text-[11px] text-slate-400">
              <span className="flex items-center gap-1 text-emerald-400 font-mono">
                <Bot className="w-3 h-3" /> {botThreadsCount} Bot
              </span>
              <span>•</span>
              <span className="flex items-center gap-1 text-amber-400 font-mono">
                <UserCheck className="w-3 h-3" /> {humanThreadsCount} Humano
              </span>
            </div>
          </CardContent>
        </Card>

        {/* KPI 3: Fila & DLQ */}
        <Card className="bg-slate-900/60 border-slate-800">
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0 p-4">
            <CardTitle className="text-xs font-medium text-slate-400">
              Esteira de Mensagens
            </CardTitle>
            <ListOrdered className="w-4 h-4 text-blue-400" />
          </CardHeader>
          <CardContent className="p-4 pt-0">
            {loadingQueue ? (
              <Skeleton className="h-7 w-24" />
            ) : (
              <div className="text-2xl font-bold tracking-tight text-slate-100 font-mono">
                {(queueStats?.pending ?? 0) + (queueStats?.processing ?? 0)}
              </div>
            )}
            <div className="flex items-center gap-2 mt-1 text-[11px]">
              <span className="text-slate-400 font-mono">
                {queueStats?.pending ?? 0} na fila
              </span>
              <span>•</span>
              <span
                className={`font-mono ${
                  (queueStats?.dead ?? 0) > 0
                    ? "text-rose-400 font-semibold"
                    : "text-slate-500"
                }`}
              >
                {queueStats?.dead ?? 0} mortas (DLQ)
              </span>
            </div>
          </CardContent>
        </Card>

        {/* KPI 4: Guardrails */}
        <Card className="bg-slate-900/60 border-slate-800">
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0 p-4">
            <CardTitle className="text-xs font-medium text-slate-400">
              Guardrails & Segurança
            </CardTitle>
            <ShieldCheck className="w-4 h-4 text-rose-400" />
          </CardHeader>
          <CardContent className="p-4 pt-0">
            {loadingAudit ? (
              <Skeleton className="h-7 w-12" />
            ) : (
              <div className="text-2xl font-bold tracking-tight text-slate-100 font-mono">
                {blockedRunsCount}
              </div>
            )}
            <p className="text-[11px] text-slate-500 mt-1">
              Bloqueios por injeção ou toxicidade
            </p>
          </CardContent>
        </Card>
      </div>

      {/* Main Grid: Conversas Recentes & Status dos Serviços */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left 2 Cols: Conversas Recentes */}
        <Card className="lg:col-span-2 bg-slate-900/60 border-slate-800">
          <CardHeader className="flex flex-row items-center justify-between p-4 border-b border-slate-800">
            <div>
              <CardTitle className="text-xs font-semibold text-slate-200">
                Últimas Conversas no WhatsApp
              </CardTitle>
              <p className="text-[11px] text-slate-500 mt-0.5">
                Contatos recentes e status do atendimento automatizado.
              </p>
            </div>
            <Link
              href="/conversations"
              className="text-xs text-emerald-400 hover:text-emerald-300 flex items-center gap-1 font-medium transition-colors"
            >
              Abrir Inbox
              <ArrowUpRight className="w-3 h-3" />
            </Link>
          </CardHeader>
          <CardContent className="p-0">
            {loadingThreads ? (
              <div className="p-4 space-y-3">
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
                <Skeleton className="h-10 w-full" />
              </div>
            ) : !threads || threads.length === 0 ? (
              <div className="p-8 text-center text-xs text-slate-500">
                Nenhuma conversa registrada ainda. Novas mensagens do WhatsApp aparecerão aqui automaticamente.
              </div>
            ) : (
              <div className="divide-y divide-slate-800/60">
                {threads.slice(0, 5).map((thread) => (
                  <Link
                    key={thread.id}
                    href={`/conversations?thread=${encodeURIComponent(thread.id)}`}
                    className="flex items-center justify-between p-3.5 hover:bg-slate-800/40 transition-colors block"
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="w-8 h-8 rounded-full bg-slate-800 border border-slate-700 flex items-center justify-center text-xs font-mono font-semibold text-slate-300 shrink-0">
                        {thread.phone_number.slice(-2)}
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-2">
                          <span className="text-xs font-mono font-medium text-slate-200">
                            {formatPhoneNumber(thread.phone_number)}
                          </span>
                          <Badge
                            variant={
                              thread.mode === "bot"
                                ? "active"
                                : thread.mode === "human"
                                ? "attention"
                                : "neutral"
                            }
                          >
                            {thread.mode === "bot"
                              ? "IA Ativa"
                              : thread.mode === "human"
                              ? "Atendimento Humano"
                              : "Pausado"}
                          </Badge>
                        </div>
                        <p className="text-[11px] text-slate-400 truncate max-w-md mt-0.5">
                          {thread.last_message || "Sem mensagens recentes"}
                        </p>
                      </div>
                    </div>
                    <span className="text-[10px] font-mono text-slate-500 shrink-0 ml-4">
                      {formatTimestamp(thread.updated_at)}
                    </span>
                  </Link>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {/* Right 1 Col: Status dos Serviços */}
        <div className="space-y-4">
          <Card className="bg-slate-900/60 border-slate-800">
            <CardHeader className="p-4 border-b border-slate-800">
              <CardTitle className="text-xs font-semibold text-slate-200 flex items-center gap-2">
                <Cpu className="w-4 h-4 text-emerald-400" />
                Infraestrutura do Sistema
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 space-y-3">
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">Borda FastAPI</span>
                <Badge variant="active">Porta 8000</Badge>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">Admin API</span>
                <Badge variant="active">Porta 8001</Badge>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">PostgreSQL (Debounce & RAG)</span>
                <Badge variant="active">Ativo</Badge>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">Motor Cognitivo</span>
                <Badge variant="neutral">LangGraph</Badge>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-slate-400">Provedor LLM</span>
                <span className="font-mono text-xs text-slate-300">
                  {health?.llm_provider || "Ollama / Gemini"}
                </span>
              </div>
            </CardContent>
          </Card>

          <Card className="bg-slate-900/60 border-slate-800 p-4">
            <h4 className="text-xs font-medium text-slate-300 mb-2">Acesso Rápido</h4>
            <div className="space-y-1.5">
              <Link
                href="/queue"
                className="text-xs text-slate-400 hover:text-emerald-400 flex items-center justify-between p-2 rounded hover:bg-slate-800/60 transition-colors"
              >
                <span>Inspecionar Fila de Mensagens</span>
                <ArrowUpRight className="w-3 h-3" />
              </Link>
              <Link
                href="/security"
                className="text-xs text-slate-400 hover:text-emerald-400 flex items-center justify-between p-2 rounded hover:bg-slate-800/60 transition-colors"
              >
                <span>Logs de Auditoria e Guardrails</span>
                <ArrowUpRight className="w-3 h-3" />
              </Link>
              <Link
                href="/agents"
                className="text-xs text-slate-400 hover:text-emerald-400 flex items-center justify-between p-2 rounded hover:bg-slate-800/60 transition-colors"
              >
                <span>Configurar Prompts & Deep Research</span>
                <ArrowUpRight className="w-3 h-3" />
              </Link>
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
