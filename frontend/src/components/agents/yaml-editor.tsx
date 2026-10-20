"use client";

import * as React from "react";
import { Button } from "@/components/ui/button";
import { Save } from "lucide-react";

interface YamlEditorProps {
  initialContent?: string;
  onSave?: (content: string) => Promise<void>;
}

export default function YamlEditor({ initialContent = "", onSave }: YamlEditorProps) {
  const [content, setContent] = React.useState(initialContent);
  const [saving, setSaving] = React.useState(false);

  React.useEffect(() => {
    setContent(initialContent);
  }, [initialContent]);

  const handleSave = async () => {
    if (!onSave) return;
    try {
      setSaving(true);
      await onSave(content);
      alert("Prompt atualizado com sucesso!");
    } catch (err) {
      alert(`Falha ao salvar prompt: ${err}`);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <span className="text-xs text-slate-400 font-mono">
          configs/prompts/default_prompt.yaml
        </span>
        <Button
          size="sm"
          onClick={handleSave}
          disabled={saving}
          className="h-8 text-xs flex items-center gap-1.5"
        >
          <Save className="w-3.5 h-3.5" />
          <span>Salvar alterações</span>
        </Button>
      </div>

      <div className="relative rounded-md border border-slate-800 bg-slate-950 p-2 font-mono text-xs">
        <textarea
          value={content}
          onChange={(e) => setContent(e.target.value)}
          rows={14}
          className="w-full bg-transparent text-emerald-400 focus:outline-none resize-none font-mono text-xs leading-relaxed"
          placeholder="# Definição do Prompt de Sistema em YAML..."
        />
      </div>
    </div>
  );
}

