"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import useSWR from "swr";
import { swrFetcher } from "@/lib/swr-fetcher";
import { apiClient } from "@/lib/api-client";
import type { AgentConfig } from "@/lib/types";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { Button } from "@/components/ui/button";
import { Bot, Search, Globe, Cpu, Check, Sliders } from "lucide-react";

// Vercel Best Practice: bundle-dynamic-imports
const YamlEditor = dynamic(() => import("@/components/agents/yaml-editor"), {
  ssr: false,
  loading: () => <Skeleton className="h-64 w-full" />,
});

const defaultYaml = `name: assistente_atendimento
version: 1.0.0
description: Assistente corporativo com RAG institucional e memória semântica
system_prompt: |
  Você é o assistente virtual corporativo no WhatsApp.
  Responda de forma cortês, objetiva e formate suas mensagens
  usando Markdown claro e conciso para dispositivos móveis.
  Utilize as informações do catálogo e da base de conhecimento
  para responder dúvidas sobre produtos e horários.
`;

export default function AgentsPage() {
  const { data: config, mutate, isLoading } = useSWR<AgentConfig>(
    "/admin/agents/config",
    swrFetcher,
    { revalidateOnFocus: false }
  );

  const [deepResearch, setDeepResearch] = React.useState(false);
  const [websiteCrawler, setWebsiteCrawler] = React.useState(false);
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    if (config) {
      setDeepResearch(config.deep_research_enabled ?? false);
      setWebsiteCrawler(config.website_crawler_enabled ?? false);
    }
  }, [config]);

  const handleSaveFlags = async () => {
    try {
      setSaving(true);
      await apiClient.saveAgentConfig({
        deep_research_enabled: deepResearch,
        website_crawler_enabled: websiteCrawler,
      });
      mutate();
      alert("Configurações do agente salvas com sucesso!");
    } catch (err) {
      alert(`Falha ao salvar configurações: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-6 max-w-5xl">
      {/* Header */}
      <div>
        <h2 className="text-lg font-semibold tracking-tight text-slate-100">
          Agentes & Configuração de Cognição
        </h2>
        <p className="text-xs text-slate-400 mt-0.5">
          Gestão de modelos LLM, prompts de sistema e ativação do sub-motor de Pesquisa Profunda (Deep Research).
        </p>
      </div>

      {/* Grid: 2 Colunas */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Col 1: Modelo & Parâmetros */}
        <Card className="bg-slate-900/60 border-slate-800">
          <CardHeader className="p-4 border-b border-slate-800">
            <CardTitle className="text-xs font-semibold text-slate-200 flex items-center gap-2">
              <Cpu className="w-4 h-4 text-emerald-400" />
              Modelo & Provedor Ativo
            </CardTitle>
            <CardDescription>
              Configuração base injetada no motor LangGraph.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-4 space-y-4">
            {isLoading ? (
              <div className="space-y-2">
                <Skeleton className="h-8 w-full" />
                <Skeleton className="h-8 w-full" />
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">Provedor LLM</span>
                  <Badge variant="active" className="font-mono">
                    {config?.model_provider || "ollama"}
                  </Badge>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">Modelo Selecionado</span>
                  <span className="font-mono text-xs text-slate-200">
                    {config?.model_name || "llama3.2"}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">Temperatura</span>
                  <span className="font-mono text-xs text-slate-200">
                    {config?.temperature ?? 0.2}
                  </span>
                </div>
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-400">Prompt Ativo</span>
                  <span className="font-mono text-xs text-emerald-400">
                    {config?.default_prompt_name || "default_prompt.yaml"}
                  </span>
                </div>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Col 2: Feature Flags Cognitivas */}
        <Card className="bg-slate-900/60 border-slate-800">
          <CardHeader className="p-4 border-b border-slate-800">
            <CardTitle className="text-xs font-semibold text-slate-200 flex items-center gap-2">
              <Sliders className="w-4 h-4 text-amber-400" />
              Ferramentas de Cognição
            </CardTitle>
            <CardDescription>
              Habilite ou desabilite recursos adicionais da IA.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-4 space-y-4">
            {/* Deep Research Switch */}
            <div className="flex items-start justify-between gap-3 p-3 rounded-md bg-slate-950/60 border border-slate-800">
              <div className="space-y-0.5">
                <div className="text-xs font-medium text-slate-200 flex items-center gap-1.5">
                  <Search className="w-3.5 h-3.5 text-blue-400" />
                  <span>Pesquisa Profunda (Deep Research)</span>
                </div>
                <p className="text-[11px] text-slate-500 leading-normal">
                  Ativa o sub-agente com DuckDuckGo para buscar na web quando a dúvida não constar na base local.
                </p>
              </div>
              <input
                type="checkbox"
                checked={deepResearch}
                onChange={(e) => setDeepResearch(e.target.checked)}
                className="mt-1 h-4 w-4 rounded accent-emerald-500 cursor-pointer"
              />
            </div>

            {/* Website Crawler Switch */}
            <div className="flex items-start justify-between gap-3 p-3 rounded-md bg-slate-950/60 border border-slate-800">
              <div className="space-y-0.5">
                <div className="text-xs font-medium text-slate-200 flex items-center gap-1.5">
                  <Globe className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Crawler de Websites & Catálogos</span>
                </div>
                <p className="text-[11px] text-slate-500 leading-normal">
                  Permite ingestão e atualização contínua do site institucional no PGVector/Qdrant.
                </p>
              </div>
              <input
                type="checkbox"
                checked={websiteCrawler}
                onChange={(e) => setWebsiteCrawler(e.target.checked)}
                className="mt-1 h-4 w-4 rounded accent-emerald-500 cursor-pointer"
              />
            </div>

            <Button
              size="sm"
              onClick={handleSaveFlags}
              disabled={saving}
              className="w-full text-xs"
            >
              <Check className="w-3.5 h-3.5 mr-1" />
              <span>Salvar preferências das ferramentas</span>
            </Button>
          </CardContent>
        </Card>
      </div>

      {/* Full Width: YAML Prompt Editor */}
      <Card className="bg-slate-900/60 border-slate-800">
        <CardHeader className="p-4 border-b border-slate-800">
          <CardTitle className="text-xs font-semibold text-slate-200 flex items-center gap-2">
            <Bot className="w-4 h-4 text-emerald-400" />
            Editor do Prompt de Sistema (PromptOps)
          </CardTitle>
          <CardDescription>
            Definição de regras de comportamento, tom de voz e diretrizes de atendimento ao cliente.
          </CardDescription>
        </CardHeader>
        <CardContent className="p-4">
          <YamlEditor initialContent={defaultYaml} />
        </CardContent>
      </Card>
    </div>
  );
}

