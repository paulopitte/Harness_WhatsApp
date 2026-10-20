"use client";

import * as React from "react";
import useSWR from "swr";
import { swrFetcher } from "@/lib/swr-fetcher";
import { apiClient } from "@/lib/api-client";
import type { QueueItem, QueueStatsResponse, QueueStatus } from "@/lib/types";
import { formatPhoneNumber, formatTimestamp } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
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
import { RotateCcw, AlertTriangle, CheckCircle2, Clock, Play } from "lucide-react";

export default function QueuePage() {
  const [selectedStatus, setSelectedStatus] = React.useState<QueueStatus | "all">("all");
  const [reprocessing, setReprocessing] = React.useState(false);

  const {
    data: stats,
    mutate: mutateStats,
    isLoading: loadingStats,
  } = useSWR<QueueStatsResponse>("/admin/queue/stats", swrFetcher, {
    refreshInterval: 4000,
  });

  const queryPath =
    selectedStatus === "all"
      ? "/admin/queue/items"
      : `/admin/queue/items?status=${selectedStatus}`;

  const {
    data: items,
    mutate: mutateItems,
    isLoading: loadingItems,
  } = useSWR<QueueItem[]>(queryPath, swrFetcher, {
    refreshInterval: 4000,
  });

  const handleReplayAllDead = async () => {
    try {
      setReprocessing(true);
      await apiClient.replayDlqItem("");
      mutateStats();
      mutateItems();
      alert("Itens da DLQ reenviados para a fila de processamento!");
    } catch (err) {
      alert(`Falha ao reprocessar DLQ: ${err}`);
    } finally {
      setReprocessing(false);
    }
  };

  const getStatusBadge = (status: QueueStatus) => {
    switch (status) {
      case "pending":
        return <Badge variant="neutral"><Clock className="w-2.5 h-2.5" /> Pendente</Badge>;
      case "processing":
        return <Badge variant="attention"><Play className="w-2.5 h-2.5" /> Processando</Badge>;
      case "done":
        return <Badge variant="active"><CheckCircle2 className="w-2.5 h-2.5" /> Concluída</Badge>;
      case "dead":
        return <Badge variant="critical"><AlertTriangle className="w-2.5 h-2.5" /> Falha (DLQ)</Badge>;
    }
  };

  return (
    <div className="space-y-6 max-w-7xl">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
        <div>
          <h2 className="text-lg font-semibold tracking-tight text-slate-100">
            Fila Operacional & Dead Letter Queue
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Observabilidade transacional da esteira PostgreSQL com debounce e reprocessamento atômico.
          </p>
        </div>

        {(stats?.dead ?? 0) > 0 ? (
          <Button
            size="sm"
            variant="danger"
            onClick={handleReplayAllDead}
            disabled={reprocessing}
            className="text-xs flex items-center gap-1.5 shrink-0"
          >
            <RotateCcw className={`w-3.5 h-3.5 ${reprocessing ? "animate-spin" : ""}`} />
            <span>Reprocessar Todas as Mortas ({stats?.dead})</span>
          </Button>
        ) : null}
      </div>

      {/* Counters Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <button
          onClick={() => setSelectedStatus(selectedStatus === "pending" ? "all" : "pending")}
          className={`p-3 rounded-md border text-left transition-colors cursor-pointer ${
            selectedStatus === "pending"
              ? "bg-slate-800 border-slate-600"
              : "bg-slate-900/60 border-slate-800 hover:bg-slate-800/40"
          }`}
        >
          <div className="text-[11px] text-slate-400 flex items-center gap-1.5">
            <Clock className="w-3 h-3 text-slate-400" />
            <span>Aguardando Debounce</span>
          </div>
          <div className="text-xl font-bold font-mono text-slate-100 mt-1">
            {loadingStats ? <Skeleton className="h-6 w-10" /> : stats?.pending ?? 0}
          </div>
        </button>

        <button
          onClick={() => setSelectedStatus(selectedStatus === "processing" ? "all" : "processing")}
          className={`p-3 rounded-md border text-left transition-colors cursor-pointer ${
            selectedStatus === "processing"
              ? "bg-slate-800 border-slate-600"
              : "bg-slate-900/60 border-slate-800 hover:bg-slate-800/40"
          }`}
        >
          <div className="text-[11px] text-amber-300 flex items-center gap-1.5">
            <Play className="w-3 h-3 text-amber-400" />
            <span>Em Execução</span>
          </div>
          <div className="text-xl font-bold font-mono text-amber-400 mt-1">
            {loadingStats ? <Skeleton className="h-6 w-10" /> : stats?.processing ?? 0}
          </div>
        </button>

        <button
          onClick={() => setSelectedStatus(selectedStatus === "done" ? "all" : "done")}
          className={`p-3 rounded-md border text-left transition-colors cursor-pointer ${
            selectedStatus === "done"
              ? "bg-slate-800 border-slate-600"
              : "bg-slate-900/60 border-slate-800 hover:bg-slate-800/40"
          }`}
        >
          <div className="text-[11px] text-emerald-300 flex items-center gap-1.5">
            <CheckCircle2 className="w-3 h-3 text-emerald-400" />
            <span>Concluídas</span>
          </div>
          <div className="text-xl font-bold font-mono text-emerald-400 mt-1">
            {loadingStats ? <Skeleton className="h-6 w-14" /> : stats?.done ?? 0}
          </div>
        </button>

        <button
          onClick={() => setSelectedStatus(selectedStatus === "dead" ? "all" : "dead")}
          className={`p-3 rounded-md border text-left transition-colors cursor-pointer ${
            selectedStatus === "dead"
              ? "bg-rose-950/60 border-rose-700"
              : "bg-slate-900/60 border-slate-800 hover:bg-slate-800/40"
          }`}
        >
          <div className="text-[11px] text-rose-300 flex items-center gap-1.5">
            <AlertTriangle className="w-3 h-3 text-rose-400" />
            <span>Mensagens Mortas (DLQ)</span>
          </div>
          <div className="text-xl font-bold font-mono text-rose-400 mt-1">
            {loadingStats ? <Skeleton className="h-6 w-8" /> : stats?.dead ?? 0}
          </div>
        </button>
      </div>

      {/* Main Table */}
      <Card className="bg-slate-900/60 border-slate-800">
        <CardHeader className="p-4 border-b border-slate-800 flex flex-row items-center justify-between">
          <CardTitle className="text-xs font-semibold text-slate-200">
            Itens Registrados na Fila ({items?.length ?? 0})
          </CardTitle>
          {selectedStatus !== "all" ? (
            <Button
              size="sm"
              variant="ghost"
              onClick={() => setSelectedStatus("all")}
              className="text-xs text-slate-400"
            >
              Limpar filtro ({selectedStatus})
            </Button>
          ) : null}
        </CardHeader>
        <CardContent className="p-0">
          {loadingItems ? (
            <div className="p-6 space-y-3">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : !items || items.length === 0 ? (
            <div className="p-8 text-center text-xs text-slate-500">
              {selectedStatus === "dead"
                ? "A fila está saudável. Nenhuma mensagem morta ou com falha encontrada."
                : "Nenhum item encontrado para o status selecionado."}
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-36">ID da Fila</TableHead>
                  <TableHead>Telefone</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-center">Tentativas</TableHead>
                  <TableHead>Último Erro</TableHead>
                  <TableHead>Data de Entrada</TableHead>
                  <TableHead className="text-right">Ação</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => (
                  <TableRow key={item.id}>
                    <TableCell className="font-mono text-[11px] text-slate-400">
                      {item.id.slice(0, 8)}...
                    </TableCell>
                    <TableCell className="font-mono text-xs font-medium text-slate-200">
                      {formatPhoneNumber(item.phone_number)}
                    </TableCell>
                    <TableCell>{getStatusBadge(item.status)}</TableCell>
                    <TableCell className="text-center font-mono text-xs text-slate-300">
                      {item.retry_count} / {item.max_retries}
                    </TableCell>
                    <TableCell className="text-xs text-slate-400 max-w-xs truncate">
                      {item.error_message ? (
                        <span className="text-rose-400 font-mono text-[11px]">
                          {item.error_message}
                        </span>
                      ) : (
                        "-"
                      )}
                    </TableCell>
                    <TableCell className="font-mono text-[11px] text-slate-400">
                      {formatTimestamp(item.created_at)}
                    </TableCell>
                    <TableCell className="text-right">
                      {item.status === "dead" ? (
                        <Button
                          size="sm"
                          variant="secondary"
                          onClick={handleReplayAllDead}
                          className="h-7 text-xs px-2.5"
                        >
                          Reprocessar
                        </Button>
                      ) : (
                        <span className="text-[11px] text-slate-600">-</span>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

