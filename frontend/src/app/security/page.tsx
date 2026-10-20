"use client";

import * as React from "react";
import useSWR from "swr";
import { swrFetcher } from "@/lib/swr-fetcher";
import type { AuditRunItem } from "@/lib/types";
import { formatPhoneNumber, formatTimestamp } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Skeleton } from "@/components/ui/skeleton";
import { ShieldCheck, ShieldAlert, CheckCircle2, Lock, Flame } from "lucide-react";

export default function SecurityPage() {
  const [filterBlocked, setFilterBlocked] = React.useState(false);

  const queryPath = filterBlocked
    ? "/admin/audit/logs?status=blocked"
    : "/admin/audit/logs";

  const { data: logs, isLoading } = useSWR<AuditRunItem[]>(
    queryPath,
    swrFetcher,
    { refreshInterval: 6000 }
  );

  const totalRuns = logs?.length ?? 0;
  const blockedCount = logs?.filter((l) => l.status === "blocked").length ?? 0;
  const avgLatency =
    totalRuns > 0
      ? Math.round(
          (logs?.reduce((acc, l) => acc + (l.latency_ms || 0), 0) ?? 0) /
            totalRuns
        )
      : 0;

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Header */}
      <div>
        <h2 className="text-lg font-semibold tracking-tight text-slate-100">
          Central de Segurança & Auditoria de Guardrails
        </h2>
        <p className="text-xs text-slate-400 mt-0.5">
          Rastreabilidade completa de turnos de IA, filtros contra Prompt Injection e prevenção de vazamento de PII.
        </p>
      </div>

      {/* Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        <Card className="bg-slate-900/60 border-slate-800">
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0 p-4">
            <CardTitle className="text-xs font-medium text-slate-400">
              Total de Execuções Auditadas
            </CardTitle>
            <ShieldCheck className="w-4 h-4 text-emerald-400" />
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <div className="text-2xl font-bold font-mono text-slate-100">
              {isLoading ? <Skeleton className="h-7 w-16" /> : totalRuns}
            </div>
            <p className="text-[11px] text-slate-500 mt-1">Registros na tabela audit_runs</p>
          </CardContent>
        </Card>

        <Card className="bg-slate-900/60 border-slate-800">
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0 p-4">
            <CardTitle className="text-xs font-medium text-rose-300">
              Tentativas Bloqueadas
            </CardTitle>
            <ShieldAlert className="w-4 h-4 text-rose-400" />
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <div className="text-2xl font-bold font-mono text-rose-400">
              {isLoading ? <Skeleton className="h-7 w-12" /> : blockedCount}
            </div>
            <p className="text-[11px] text-slate-500 mt-1">Injeção de prompt ou conteúdo tóxico</p>
          </CardContent>
        </Card>

        <Card className="bg-slate-900/60 border-slate-800">
          <CardHeader className="flex flex-row items-center justify-between pb-2 space-y-0 p-4">
            <CardTitle className="text-xs font-medium text-slate-400">
              Latência Média da LLM
            </CardTitle>
            <Flame className="w-4 h-4 text-amber-400" />
          </CardHeader>
          <CardContent className="p-4 pt-0">
            <div className="text-2xl font-bold font-mono text-slate-100">
              {isLoading ? <Skeleton className="h-7 w-20" /> : `${avgLatency} ms`}
            </div>
            <p className="text-[11px] text-slate-500 mt-1">Tempo ponta a ponta por turno</p>
          </CardContent>
        </Card>
      </div>

      {/* Main Table */}
      <Card className="bg-slate-900/60 border-slate-800">
        <CardHeader className="p-4 border-b border-slate-800 flex flex-row items-center justify-between">
          <CardTitle className="text-xs font-semibold text-slate-200">
            Logs de Auditoria ({totalRuns})
          </CardTitle>
          <div className="flex items-center gap-2">
            <button
              onClick={() => setFilterBlocked(!filterBlocked)}
              className={`px-2.5 py-1 text-xs rounded border transition-colors cursor-pointer ${
                filterBlocked
                  ? "bg-rose-950/80 border-rose-800 text-rose-300 font-semibold"
                  : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200"
              }`}
            >
              {filterBlocked ? "Exibindo apenas bloqueios" : "Filtrar apenas bloqueios"}
            </button>
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-3">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : !logs || logs.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-500">
              {filterBlocked
                ? "Nenhum evento bloqueado encontrado no período recente. Todos os turnos foram processados com sucesso."
                : "Nenhum log de auditoria encontrado."}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-32">Run ID</TableHead>
                  <TableHead>Conversa / Telefone</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-center">Latência</TableHead>
                  <TableHead className="text-center">Tokens</TableHead>
                  <TableHead>Motivo / Alerta</TableHead>
                  <TableHead className="text-right">Timestamp</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.map((log) => {
                  const isBlocked = log.status === "blocked";
                  return (
                    <TableRow key={log.id}>
                      <TableCell className="font-mono text-[11px] text-slate-400">
                        {log.id.slice(0, 8)}...
                      </TableCell>
                      <TableCell className="font-mono text-xs font-medium text-slate-200">
                        {formatPhoneNumber(log.thread_id.replace(/^wa:/, ""))}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={
                            isBlocked
                              ? "critical"
                              : log.status === "success"
                              ? "active"
                              : "neutral"
                          }
                        >
                          {isBlocked ? (
                            <>
                              <Lock className="w-2.5 h-2.5" /> Bloqueado
                            </>
                          ) : (
                            <>
                              <CheckCircle2 className="w-2.5 h-2.5" /> Sucesso
                            </>
                          )}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-center font-mono text-xs text-slate-300">
                        {log.latency_ms} ms
                      </TableCell>
                      <TableCell className="text-center font-mono text-xs text-slate-400">
                        {log.tokens_used ?? "-"}
                      </TableCell>
                      <TableCell className="text-xs max-w-sm truncate">
                        {isBlocked ? (
                          <span className="text-rose-400 font-semibold">
                            {log.blocked_reason || "Tentativa de injeção ou violação de segurança"}
                          </span>
                        ) : (
                          <span className="text-slate-500">-</span>
                        )}
                      </TableCell>
                      <TableCell className="text-right font-mono text-[11px] text-slate-400">
                        {formatTimestamp(log.created_at)}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

