import { ArrowDown, ArrowUp, Box, Check, Pencil, Plus, Trash2, X } from "lucide-react";
import { useState } from "react";
import type { ReactNode } from "react";
import type { StudioAsset } from "../types/studio";
import { Panel } from "./Panel";

interface AssetBrowserProps {
  assets: StudioAsset[];
  selectedAssetId: string;
  onSelectAsset: (assetId: string) => void;
  onNewAsset: () => void;
  onRenameAsset: (assetId: string, newAssetId: string) => void;
  onDeleteAsset: (assetId: string) => void;
  onMoveAsset: (assetId: string, direction: "up" | "down") => void;
}

export function AssetBrowser({
  assets,
  selectedAssetId,
  onSelectAsset,
  onNewAsset,
  onRenameAsset,
  onDeleteAsset,
  onMoveAsset
}: AssetBrowserProps) {
  const [editingAssetId, setEditingAssetId] = useState<string | null>(null);
  const [draftAssetId, setDraftAssetId] = useState("");

  const beginRename = (assetId: string) => {
    setEditingAssetId(assetId);
    setDraftAssetId(assetId);
  };

  const submitRename = () => {
    if (!editingAssetId) {
      return;
    }
    const next = draftAssetId.trim();
    if (next && next !== editingAssetId) {
      onRenameAsset(editingAssetId, next);
    }
    setEditingAssetId(null);
    setDraftAssetId("");
  };

  return (
    <Panel
      title="Asset Browser"
      subtitle="Project assets"
      actions={
        <button
          type="button"
          onClick={onNewAsset}
          className="studio-readout flex items-center gap-1 border border-studio-cyan bg-studio-cyan/15 px-2 py-1 text-[9px] font-black uppercase text-studio-cyan hover:border-studio-accent hover:text-studio-text"
        >
          <Plus size={13} aria-hidden="true" />
          New Asset
        </button>
      }
    >
      <div className="space-y-2" role="list" aria-label="Asset list">
        {assets.map((asset, index) => {
          const selected = asset.id === selectedAssetId;
          const editing = editingAssetId === asset.id;
          return (
            <div
              key={asset.id}
              className={`studio-panel-chrome grid min-w-0 grid-cols-[1fr_auto] gap-2 border px-2 py-2 transition ${
                selected
                  ? "border-studio-accent bg-studio-accent/15 text-white shadow-[var(--studio-shadow-cyan)]"
                  : "border-studio-border bg-studio-panelAlt text-studio-text hover:border-studio-accent/80"
              }`}
            >
              {editing ? (
                <div className="min-w-0">
                  <input
                    value={draftAssetId}
                    onChange={(event) => setDraftAssetId(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        submitRename();
                      } else if (event.key === "Escape") {
                        setEditingAssetId(null);
                      }
                    }}
                    className="studio-readout w-full border border-studio-accent bg-studio-panel px-2 py-1 text-xs text-studio-text outline-none"
                    aria-label={`Rename ${asset.id}`}
                    autoFocus
                  />
                  <span className="studio-readout mt-1 block truncate text-[9px] uppercase text-studio-muted">{asset.coverage}</span>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => onSelectAsset(asset.id)}
                  className="flex min-w-0 items-center gap-3 text-left"
                  aria-label={`Select asset ${asset.id}`}
                  aria-pressed={selected}
                >
                  <Box size={16} aria-hidden="true" className="shrink-0" />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium">{asset.id}</span>
                    <span className="studio-readout block truncate text-[10px] uppercase text-studio-muted">{asset.coverage}</span>
                  </span>
                  {asset.availableSprites ? (
                    <span className="studio-readout border border-studio-border bg-studio-panel px-1.5 py-0.5 text-[9px] text-studio-muted">
                      {Object.values(asset.availableSprites).filter(Boolean).length}v
                    </span>
                  ) : null}
                </button>
              )}

              <div className="flex shrink-0 items-start gap-1">
                {editing ? (
                  <>
                    <IconButton label={`Save ${asset.id} rename`} onClick={submitRename} icon={<Check size={13} />} />
                    <IconButton
                      label={`Cancel ${asset.id} rename`}
                      onClick={() => setEditingAssetId(null)}
                      icon={<X size={13} />}
                    />
                  </>
                ) : (
                  <>
                    <IconButton
                      label={`Move ${asset.id} up`}
                      onClick={() => onMoveAsset(asset.id, "up")}
                      disabled={index === 0}
                      icon={<ArrowUp size={13} />}
                    />
                    <IconButton
                      label={`Move ${asset.id} down`}
                      onClick={() => onMoveAsset(asset.id, "down")}
                      disabled={index === assets.length - 1}
                      icon={<ArrowDown size={13} />}
                    />
                    <IconButton label={`Rename ${asset.id}`} onClick={() => beginRename(asset.id)} icon={<Pencil size={13} />} />
                    <IconButton
                      label={`Delete ${asset.id}`}
                      onClick={() => {
                        if (window.confirm(`Delete asset ${asset.id}?`)) {
                          onDeleteAsset(asset.id);
                        }
                      }}
                      danger
                      icon={<Trash2 size={13} />}
                    />
                  </>
                )}
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

function IconButton({
  label,
  icon,
  onClick,
  disabled = false,
  danger = false
}: {
  label: string;
  icon: ReactNode;
  onClick: () => void;
  disabled?: boolean;
  danger?: boolean;
}) {
  return (
    <button
      type="button"
      aria-label={label}
      title={label}
      disabled={disabled}
      onClick={onClick}
      className={`border p-1 disabled:cursor-not-allowed disabled:opacity-40 ${
        danger
          ? "border-studio-fail/70 bg-studio-fail/10 text-studio-fail hover:border-studio-fail"
          : "border-studio-border bg-studio-panel text-studio-muted hover:border-studio-cyan hover:text-studio-text"
      }`}
    >
      {icon}
    </button>
  );
}
