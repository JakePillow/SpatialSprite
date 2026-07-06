interface DepthHeatmapProps {
  title: string;
  src?: string;
  emptyLabel?: string;
}

export function DepthHeatmap({ title, src, emptyLabel = "not emitted" }: DepthHeatmapProps) {
  return (
    <figure className="border border-studio-border bg-studio-panelAlt p-2">
      <figcaption className="studio-readout mb-2 text-[10px] uppercase text-studio-muted">{title}</figcaption>
      {src ? (
        <img src={src} alt={title} className="h-28 w-full object-contain [image-rendering:pixelated]" />
      ) : (
        <div className="studio-readout grid h-28 place-items-center text-[10px] text-studio-muted">{emptyLabel}</div>
      )}
    </figure>
  );
}
