"use client";

import useSWR from "swr";
import { swrFetcher } from "@/lib/swr-fetcher";
import type { ThreadFactsResponse } from "@/lib/types";
import { formatPhoneNumber } from "@/lib/utils";
import { Brain, Sparkles, User, FileText } from "lucide-react";
import { Skeleton } from "@/components/ui/skeleton";

interface CustomerPanelProps {
  threadId: string | null;
}

export function CustomerPanel({ threadId }: CustomerPanelProps) {
  const { data: factsData, isLoading } = useSWR<ThreadFactsResponse>(
    threadId ? `/admin/threads/${encodeURIComponent(threadId)}/facts` : null,
    swrFetcher,
    { refreshInterval: 6000 }
  );

  if (!threadId) {
    return (
      <aside className="w-80 shrink-0 border-l border-slate-800 bg-slate-950 p-6 flex flex-col items-center justify-center text-center text-xs text-slate-500">
        <Brain className="w-6 h-6 text-slate-600 mb-2" />
        <p>Selecione um cliente para carregar a memória semântica.</p>
      </aside>
    );
  }

  const facts = factsData?.semantic_facts || {};
  const factKeys = Object.keys(facts);
  const summary = factsData?.conversation_summary;

  return (
    <aside className="w-80 shrink-0 border-l border-slate-800 bg-slate-950 flex flex-col h-full overflow-y-auto">
      {/* Header */}
      <div className="h-14 px-4 border-b border-slate-800/80 flex items-center gap-2 shrink-0">
        <Brain className="w-4 h-4 text-emerald-400" />
        <h3 className="text-xs font-semibold text-slate-200">
          Inteligência do Cliente
        </h3>
      </div>

      <div className="p-4 space-y-5">
        {/* Contact Quick Info */}
        <div className="p-3 rounded-md bg-slate-900/60 border border-slate-800/80 space-y-1.5">
          <div className="flex items-center gap-2 text-xs font-semibold text-slate-200">
            <User className="w-3.5 h-3.5 text-slate-400" />
            <span className="font-mono">
              {formatPhoneNumber(factsData?.phone_number || "")}
            </span>
          </div>
          <p className="text-[10px] text-slate-500 font-mono">
            {factsData?.thread_id}
          </p>
        </div>

        {/* Semantic Facts */}
        <div>
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300 mb-2">
            <Sparkles className="w-3.5 h-3.5 text-emerald-400" />
            <h4>Fatos & Preferências Extraídos</h4>
          </div>

          {isLoading ? (
            <div className="space-y-2">
              <Skeleton className="h-8 w-full" />
              <Skeleton className="h-8 w-full" />
            </div>
          ) : factKeys.length === 0 ? (
            <div className="p-3 rounded bg-slate-900/40 border border-slate-800/60 text-[11px] text-slate-500">
              Ainda não foram extraídos fatos sobre este cliente. Conforme o cliente conversar com o assistente, suas preferências aparecerão aqui.
            </div>
          ) : (
            <div className="space-y-1.5">
              {factKeys.map((key) => (
                <div
                  key={key}
                  className="p-2.5 rounded bg-slate-900/80 border border-slate-800 flex flex-col gap-0.5"
                >
                  <span className="text-[10px] uppercase font-mono font-medium text-slate-500 tracking-wider">
                    {key}
                  </span>
                  <span className="text-xs text-slate-200 font-medium">
                    {facts[key]}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Operational Memory Summary */}
        <div>
          <div className="flex items-center gap-1.5 text-xs font-semibold text-slate-300 mb-2">
            <FileText className="w-3.5 h-3.5 text-blue-400" />
            <h4>Resumo da Conversa</h4>
          </div>

          {isLoading ? (
            <Skeleton className="h-20 w-full" />
          ) : !summary ? (
            <div className="p-3 rounded bg-slate-900/40 border border-slate-800/60 text-[11px] text-slate-500">
              Conversa curta ou em andamento. O resumo compacto será gerado automaticamente quando o histórico atingir o limite de contexto.
            </div>
          ) : (
            <div className="p-3 rounded bg-slate-900/80 border border-slate-800 text-xs text-slate-300 leading-relaxed">
              {summary}
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}

