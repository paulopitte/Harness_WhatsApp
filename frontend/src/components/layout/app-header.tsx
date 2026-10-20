"use client";

import useSWR from "swr";
import { swrFetcher } from "@/lib/swr-fetcher";
import type { HealthResponse } from "@/lib/types";
import { Activity, RefreshCw } from "lucide-react";
import { Badge } from "@/components/ui/badge";

export function AppHeader() {
  const { data: health, error, isValidating, mutate } = useSWR<HealthResponse>(
    "/admin/health",
    swrFetcher,
    {
      refreshInterval: 10000,
      revalidateOnFocus: true,
    }
  );

  const isOnline = health && !error;

  return (
    <header className="h-14 shrink-0 border-b border-slate-800/80 bg-slate-950/90 px-6 flex items-center justify-between backdrop-blur-sm select-none">
      <div className="flex items-center gap-3">
        <h1 className="text-xs font-semibold text-slate-200 tracking-tight">
          Painel de Operações & Controle
        </h1>
        <span className="text-slate-600">/</span>
        <div className="flex items-center gap-2">
          <Badge variant={isOnline ? "active" : "critical"}>
            <span
              className={`w-1.5 h-1.5 rounded-full ${
                isOnline ? "bg-emerald-400 animate-pulse" : "bg-rose-400"
              }`}
            />
            {isOnline ? "Backend Conectado" : "Offline"}
          </Badge>
          {health?.llm_provider ? (
            <span className="text-[11px] font-mono text-slate-400 bg-slate-900 px-2 py-0.5 rounded border border-slate-800">
              LLM: {health.llm_provider}
            </span>
          ) : null}
        </div>
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => mutate()}
          title="Atualizar dados agora"
          className="p-1.5 rounded text-slate-400 hover:text-slate-100 hover:bg-slate-800/60 transition-colors cursor-pointer"
        >
          <RefreshCw
            className={`w-3.5 h-3.5 ${isValidating ? "animate-spin text-emerald-400" : ""}`}
          />
        </button>
        <div className="text-[11px] text-slate-500 font-mono">Porta 8001</div>
      </div>
    </header>
  );
}

