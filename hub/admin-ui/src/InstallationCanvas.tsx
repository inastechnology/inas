import { useEffect, useLayoutEffect, useMemo, useRef, useState } from "react";
import Konva from "konva";
import type { KonvaEventObject } from "konva/lib/Node";
import { ArrowUp } from "lucide-react";
import { Arrow, Circle, Group, Layer, Line, Rect, Stage, Text, Transformer } from "react-konva";

import { PRESET_BY_ID } from "./presets";
import type { FieldLayout, LayoutSpace, Placement, PlacementPreset } from "./types";

export const CELL_PX = 34;

interface InstallationCanvasProps {
  layout: FieldLayout;
  space: LayoutSpace;
  selectedId: string | null;
  plantingByPlacementId: Record<string, string>;
  wateringSourceNamesByPlacementId: Record<string, string[]>;
  zoom: number;
  onZoomChange: (zoom: number) => void;
  onSelect: (id: string | null) => void;
  onPlacementChange: (id: string, patch: Partial<Placement>) => void;
  onAddPreset: (preset: PlacementPreset, x: number, y: number) => void;
  onOpenChild: (spaceId: string) => void;
}

interface CanvasSize {
  width: number;
  height: number;
}

export function InstallationCanvas({
  layout,
  space,
  selectedId,
  plantingByPlacementId,
  wateringSourceNamesByPlacementId,
  zoom,
  onZoomChange,
  onSelect,
  onPlacementChange,
  onAddPreset,
  onOpenChild,
}: InstallationCanvasProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const stageRef = useRef<Konva.Stage>(null);
  const transformerRef = useRef<Konva.Transformer>(null);
  const shapeRefs = useRef<Record<string, Konva.Group | null>>({});
  const [size, setSize] = useState<CanvasSize>({ width: 800, height: 600 });
  const [stagePosition, setStagePosition] = useState({ x: 40, y: 40 });

  useLayoutEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const updateSize = () => setSize({ width: Math.max(container.clientWidth, 320), height: Math.max(container.clientHeight, 420) });
    updateSize();
    const observer = new ResizeObserver(updateSize);
    observer.observe(container);
    return () => observer.disconnect();
  }, []);

  const fitView = () => {
    const contentWidth = space.grid.columns * CELL_PX;
    const contentHeight = space.grid.rows * CELL_PX;
    const nextZoom = Math.min(1.25, Math.max(0.2, Math.min((size.width - 72) / contentWidth, (size.height - 72) / contentHeight)));
    onZoomChange(nextZoom);
    setStagePosition({
      x: Math.max(28, (size.width - contentWidth * nextZoom) / 2),
      y: Math.max(28, (size.height - contentHeight * nextZoom) / 2),
    });
  };

  useEffect(() => {
    fitView();
    // A newly opened space should always start fully visible.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [space.id, size.width, size.height]);

  useEffect(() => {
    const transformer = transformerRef.current;
    if (!transformer) return;
    const node = selectedId ? shapeRefs.current[selectedId] : null;
    transformer.nodes(node ? [node] : []);
    transformer.getLayer()?.batchDraw();
  }, [selectedId, space.placements]);

  const gridLines = useMemo(() => {
    const lines: Array<{ key: string; points: number[]; strong: boolean }> = [];
    for (let column = 0; column <= space.grid.columns; column += 1) {
      lines.push({ key: `v-${column}`, points: [column * CELL_PX, 0, column * CELL_PX, space.grid.rows * CELL_PX], strong: column % 5 === 0 });
    }
    for (let row = 0; row <= space.grid.rows; row += 1) {
      lines.push({ key: `h-${row}`, points: [0, row * CELL_PX, space.grid.columns * CELL_PX, row * CELL_PX], strong: row % 5 === 0 });
    }
    return lines;
  }, [space.grid.columns, space.grid.rows]);

  const deviceConnections = useMemo(
    () => projectConnections(layout, space, selectedId),
    [layout, selectedId, space],
  );

  const handleWheel = (event: KonvaEventObject<WheelEvent>) => {
    event.evt.preventDefault();
    const stage = stageRef.current;
    if (!stage) return;
    const pointer = stage.getPointerPosition();
    if (!pointer) return;
    const point = { x: (pointer.x - stagePosition.x) / zoom, y: (pointer.y - stagePosition.y) / zoom };
    const direction = event.evt.deltaY > 0 ? -1 : 1;
    const nextZoom = Math.min(2.5, Math.max(0.2, direction > 0 ? zoom * 1.08 : zoom / 1.08));
    setStagePosition({ x: pointer.x - point.x * nextZoom, y: pointer.y - point.y * nextZoom });
    onZoomChange(nextZoom);
  };

  const handleDrop = (event: React.DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    const preset = event.dataTransfer.getData("application/x-ina-layout-preset") as PlacementPreset;
    if (!PRESET_BY_ID[preset]) return;
    const rect = containerRef.current?.getBoundingClientRect();
    if (!rect) return;
    const worldX = (event.clientX - rect.left - stagePosition.x) / zoom;
    const worldY = (event.clientY - rect.top - stagePosition.y) / zoom;
    onAddPreset(preset, Math.floor(worldX / CELL_PX), Math.floor(worldY / CELL_PX));
  };

  return (
    <div
      className="layout-canvas"
      ref={containerRef}
      onDragOver={(event) => event.preventDefault()}
      onDrop={handleDrop}
      aria-label={`${space.name}の設置グリッド`}
    >
      <Stage
        ref={stageRef}
        width={size.width}
        height={size.height}
        x={stagePosition.x}
        y={stagePosition.y}
        scaleX={zoom}
        scaleY={zoom}
        draggable
        onDragEnd={(event) => {
          if (event.target === event.target.getStage()) setStagePosition(event.target.position());
        }}
        onWheel={handleWheel}
        onMouseDown={(event) => {
          if (event.target === event.target.getStage()) onSelect(null);
        }}
      >
        <Layer>
          <Rect
            x={0}
            y={0}
            width={space.grid.columns * CELL_PX}
            height={space.grid.rows * CELL_PX}
            fill="#f7f8f3"
            stroke="#8f9a87"
            strokeWidth={2}
            onMouseDown={(event) => {
              event.cancelBubble = true;
              onSelect(null);
            }}
          />
          {gridLines.map((line) => (
            <Line
              key={line.key}
              points={line.points}
              stroke={line.strong ? "#c2c9bb" : "#dde2d8"}
              strokeWidth={line.strong ? 1.2 : 0.7}
              listening={false}
            />
          ))}
          {deviceConnections.map((connection) => (
            <Arrow
              key={connection.key}
              points={connection.points}
              stroke={connection.selected ? connection.selectedColor : connection.color}
              fill={connection.selected ? connection.selectedColor : connection.color}
              strokeWidth={connection.selected ? 4 : 3}
              dash={connection.dash}
              lineCap="round"
              pointerLength={9}
              pointerWidth={9}
              opacity={0.94}
              listening={false}
            />
          ))}
          {deviceConnections.filter((connection) => connection.externalLabel).map((connection) => (
            <Group key={`${connection.key}:external`} x={connection.externalPoint?.x ?? 0} y={connection.externalPoint?.y ?? 0} scaleX={1 / zoom} scaleY={1 / zoom} listening={false}>
              <Rect x={-48} y={-13} width={96} height={26} fill="#ffffff" stroke={connection.color} strokeWidth={2} cornerRadius={4} />
              <Text x={-43} y={-5} width={86} text={connection.externalLabel} fontFamily="system-ui, sans-serif" fontSize={10} fontStyle="bold" fill="#304039" align="center" ellipsis wrap="none" />
            </Group>
          ))}
          {space.placements
            .slice()
            .sort((left, right) => left.z - right.z)
            .map((placement) => (
              <PlacementNode
                key={placement.id}
                placement={placement}
                cropName={plantingByPlacementId[placement.id]}
                wateringSourceNames={wateringSourceNamesByPlacementId[placement.id] ?? []}
                selected={placement.id === selectedId}
                setRef={(node) => {
                  shapeRefs.current[placement.id] = node;
                }}
                onSelect={() => onSelect(placement.id)}
                onOpenChild={() => placement.child_space_id && onOpenChild(placement.child_space_id)}
                onChange={(patch) => onPlacementChange(placement.id, patch)}
                gridColumns={space.grid.columns}
                gridRows={space.grid.rows}
              />
            ))}
          <Transformer
            ref={transformerRef}
            rotateEnabled={false}
            flipEnabled={false}
            enabledAnchors={["top-left", "top-center", "top-right", "middle-left", "middle-right", "bottom-left", "bottom-center", "bottom-right"]}
            anchorSize={10}
            anchorCornerRadius={2}
            anchorFill="#ffffff"
            anchorStroke="#176b5b"
            borderStroke="#176b5b"
            borderStrokeWidth={2}
            boundBoxFunc={(oldBox, newBox) => (newBox.width < CELL_PX * zoom || newBox.height < CELL_PX * zoom ? oldBox : newBox)}
          />
        </Layer>
      </Stage>
      <button type="button" className="canvas-fit" onClick={fitView} title="全体を表示">
        全体表示
      </button>
      <div className="canvas-north-marker" aria-label={`北は画面上から時計回りに${space.north_angle_deg ?? 0}度`} role="img">
        <div className="canvas-north-needle" style={{ transform: `rotate(${space.north_angle_deg ?? 0}deg)` }}>
          <span style={{ transform: `rotate(-${space.north_angle_deg ?? 0}deg)` }}>N</span>
          <ArrowUp size={25} strokeWidth={2.5} />
        </div>
      </div>
      <div className="canvas-scale" aria-hidden="true">
        1マス = {space.grid.cell_size_m}m
      </div>
      <div className="canvas-connection-summary" aria-label="配置物の接続関係">
        {deviceConnections.map((connection) => <span key={connection.key} data-layout-connection data-external={connection.externalLabel ? "true" : "false"}>{connection.ariaLabel}</span>)}
      </div>
    </div>
  );
}

interface PlacementNodeProps {
  placement: Placement;
  cropName?: string;
  wateringSourceNames: string[];
  selected: boolean;
  setRef: (node: Konva.Group | null) => void;
  onSelect: () => void;
  onOpenChild: () => void;
  onChange: (patch: Partial<Placement>) => void;
  gridColumns: number;
  gridRows: number;
}

function PlacementNode({ placement, cropName, wateringSourceNames, selected, setRef, onSelect, onOpenChild, onChange, gridColumns, gridRows }: PlacementNodeProps) {
  const preset = PRESET_BY_ID[placement.preset];
  const width = placement.width * CELL_PX;
  const height = placement.height * CELL_PX;
  const compact = placement.width <= 2 || placement.height <= 1;
  const displayName = compact ? cropName || compactLabel(placement) : placement.name;
  const hasWateringSource = wateringSourceNames.length > 0;
  const wateringBadgeText = width >= 130
    ? `潅水: ${wateringSourceNames.length === 1 ? wateringSourceNames[0] : `${wateringSourceNames.length}台`}`
    : "水";
  const wateringBadgeWidth = width >= 130 ? Math.min(width - 8, 128) : 24;

  const finishTransform = (node: Konva.Group) => {
    const nextWidth = clamp(Math.round(placement.width * node.scaleX()), 1, gridColumns);
    const nextHeight = clamp(Math.round(placement.height * node.scaleY()), 1, gridRows);
    const nextX = clamp(Math.round(node.x() / CELL_PX), 0, gridColumns - nextWidth);
    const nextY = clamp(Math.round(node.y() / CELL_PX), 0, gridRows - nextHeight);
    node.scale({ x: 1, y: 1 });
    onChange({
      x: nextX,
      y: nextY,
      width: nextWidth,
      height: nextHeight,
    });
  };

  return (
    <Group
      ref={setRef}
      id={placement.id}
      x={placement.x * CELL_PX}
      y={placement.y * CELL_PX}
      width={width}
      height={height}
      draggable
      onMouseDown={(event) => {
        event.cancelBubble = true;
        onSelect();
      }}
      onTap={(event) => {
        event.cancelBubble = true;
        onSelect();
      }}
      onDblClick={onOpenChild}
      onDblTap={onOpenChild}
      onDragEnd={(event) => {
        const nextX = clamp(Math.round(event.target.x() / CELL_PX), 0, gridColumns - placement.width);
        const nextY = clamp(Math.round(event.target.y() / CELL_PX), 0, gridRows - placement.height);
        onChange({ x: nextX, y: nextY });
      }}
      onTransformEnd={(event) => finishTransform(event.target as Konva.Group)}
    >
      <Rect
        width={width}
        height={height}
        fill={preset.fill}
        stroke={selected ? "#176b5b" : hasWateringSource ? "#167da3" : preset.stroke}
        strokeWidth={selected ? 3 : hasWateringSource ? 2.5 : 1.5}
        cornerRadius={placement.preset === "irrigation_line" ? 10 : 4}
        shadowColor="#23332c"
        shadowOpacity={selected ? 0.18 : 0.08}
        shadowBlur={selected ? 8 : 3}
        shadowOffsetY={2}
      />
      <PresetPattern placement={placement} width={width} height={height} />
      {placement.binding && <Circle x={width - 9} y={9} radius={5} fill="#1d8b68" stroke="#ffffff" strokeWidth={2} />}
      {cropName && <Circle x={9} y={9} radius={5} fill="#4c8c3f" stroke="#ffffff" strokeWidth={2} />}
      {hasWateringSource && (
        <>
          <Rect x={width - wateringBadgeWidth - 4} y={4} width={wateringBadgeWidth} height={17} cornerRadius={3} fill="#167da3" opacity={0.96} listening={false} />
          <Text x={width - wateringBadgeWidth - 2} y={7} width={wateringBadgeWidth - 4} text={wateringBadgeText} fontFamily="system-ui, sans-serif" fontSize={9} fontStyle="bold" fill="#ffffff" align="center" ellipsis wrap="none" listening={false} />
        </>
      )}
      <Text
        x={6}
        y={Math.max(4, height / 2 - (compact ? 7 : cropName ? 14 : 9))}
        width={Math.max(12, width - 12)}
        text={displayName}
        fontFamily="system-ui, sans-serif"
        fontSize={compact ? 11 : 13}
        fontStyle="bold"
        fill="#24332d"
        align="center"
        ellipsis
        wrap="none"
        listening={false}
      />
      {cropName && !compact && (
        <Text
          x={8}
          y={Math.min(height - 18, height / 2 + 4)}
          width={Math.max(12, width - 16)}
          text={cropName}
          fontFamily="system-ui, sans-serif"
          fontSize={11}
          fontStyle="bold"
          fill="#356331"
          align="center"
          ellipsis
          wrap="none"
          listening={false}
        />
      )}
      {placement.child_space_id && width >= 100 && height >= 54 && (
        <Text
          x={8}
          y={height - 19}
          width={width - 16}
          text="ダブルクリックで内部へ"
          fontFamily="system-ui, sans-serif"
          fontSize={10}
          fill="#52645b"
          align="right"
          listening={false}
        />
      )}
    </Group>
  );
}

function PresetPattern({ placement, width, height }: { placement: Placement; width: number; height: number }) {
  if (placement.preset === "greenhouse") {
    return (
      <>
        <Line points={[width * 0.15, 7, width * 0.15, height - 7]} stroke="#69a588" opacity={0.7} listening={false} />
        <Line points={[width * 0.5, 7, width * 0.5, height - 7]} stroke="#69a588" opacity={0.7} listening={false} />
        <Line points={[width * 0.85, 7, width * 0.85, height - 7]} stroke="#69a588" opacity={0.7} listening={false} />
      </>
    );
  }
  if (placement.preset === "ridge" || placement.preset === "open_field") {
    const count = Math.max(1, Math.min(6, Math.floor(height / 16)));
    return (
      <>
        {Array.from({ length: count }).map((_, index) => (
          <Line key={index} points={[6, ((index + 1) * height) / (count + 1), width - 6, ((index + 1) * height) / (count + 1)]} stroke="#8f7b53" opacity={0.45} dash={[7, 5]} listening={false} />
        ))}
      </>
    );
  }
  if (placement.preset === "shade_area") {
    return <Rect x={6} y={6} width={Math.max(1, width - 12)} height={Math.max(1, height - 12)} fill="#7d9182" opacity={0.18} dash={[8, 5]} listening={false} />;
  }
  if (placement.preset === "hydroponic_bed" || placement.preset === "irrigation_line") {
    return <Line points={[7, height / 2, width - 7, height / 2]} stroke="#3186a4" strokeWidth={3} opacity={0.7} dash={[10, 5]} listening={false} />;
  }
  if (placement.preset === "tree") {
    return <Circle x={width / 2} y={height / 2} radius={Math.max(10, Math.min(width, height) * 0.34)} fill="#82b478" opacity={0.65} listening={false} />;
  }
  if (placement.preset === "pot" || placement.preset === "tank") {
    return <Circle x={width / 2} y={height / 2} radius={Math.max(8, Math.min(width, height) * 0.32)} fill={placement.preset === "tank" ? "#8eb5cc" : "#bd865e"} opacity={0.65} listening={false} />;
  }
  if (placement.preset === "grow_light") {
    return <Line points={[6, height / 2, width - 6, height / 2]} stroke="#c19a24" strokeWidth={5} opacity={0.72} listening={false} />;
  }
  if (placement.preset === "mister") {
    return <>{[0.3, 0.5, 0.7].map((ratio) => <Circle key={ratio} x={width * ratio} y={height * 0.58} radius={3} fill="#5aa0ae" opacity={0.65} listening={false} />)}</>;
  }
  if (placement.preset === "fan") {
    return <Circle x={width / 2} y={height / 2} radius={Math.max(8, Math.min(width, height) * 0.27)} stroke="#638277" strokeWidth={3} opacity={0.7} listening={false} />;
  }
  if (placement.preset === "hvac") {
    return <>{[0.35, 0.5, 0.65].map((ratio) => <Line key={ratio} points={[width * ratio, 7, width * ratio, height - 7]} stroke="#718198" strokeWidth={2} opacity={0.6} listening={false} />)}</>;
  }
  if (placement.preset === "camera") {
    const lensRadius = Math.max(7, Math.min(width, height) * 0.2);
    return (
      <>
        <Rect x={width * 0.18} y={height * 0.3} width={width * 0.64} height={height * 0.42} fill="#8f6aa5" opacity={0.28} cornerRadius={4} listening={false} />
        <Circle x={width / 2} y={height * 0.51} radius={lensRadius} fill="#6f4b87" opacity={0.7} listening={false} />
      </>
    );
  }
  return null;
}

function compactLabel(placement: Placement) {
  const fallback: Record<PlacementPreset, string> = {
    greenhouse: "H",
    open_field: "露地",
    shade_area: "日陰",
    ridge: "畝",
    tree: "木",
    pot: "鉢",
    hydroponic_bed: "水耕",
    watering_device: "潅水",
    sensor: "S",
    camera: "映像",
    irrigation_line: "配管",
    tank: "T",
    grow_light: "灯",
    mister: "霧",
    fan: "風",
    hvac: "空調",
  };
  return placement.name.length <= 8 ? placement.name : fallback[placement.preset];
}

interface ProjectedConnection {
  key: string;
  points: number[];
  selected: boolean;
  color: string;
  selectedColor: string;
  dash: number[];
  externalLabel: string;
  externalPoint: { x: number; y: number } | null;
  ariaLabel: string;
}

function projectConnections(layout: FieldLayout, activeSpace: LayoutSpace, selectedId: string | null): ProjectedConnection[] {
  const locations = new Map<string, { placement: Placement; spaceId: string }>();
  const parentByChildSpace = new Map<string, { placement: Placement; parentSpaceId: string }>();
  layout.spaces.forEach((candidateSpace) => candidateSpace.placements.forEach((placement) => {
    locations.set(placement.id, { placement, spaceId: candidateSpace.id });
    if (placement.child_space_id) parentByChildSpace.set(placement.child_space_id, { placement, parentSpaceId: candidateSpace.id });
  }));

  const representative = (location: { placement: Placement; spaceId: string }) => {
    if (location.spaceId === activeSpace.id) return location.placement;
    let currentSpaceId = location.spaceId;
    const visited = new Set<string>();
    while (!visited.has(currentSpaceId)) {
      visited.add(currentSpaceId);
      const parent = parentByChildSpace.get(currentSpaceId);
      if (!parent) return null;
      if (parent.parentSpaceId === activeSpace.id) return parent.placement;
      currentSpaceId = parent.parentSpaceId;
    }
    return null;
  };

  const connections: ProjectedConnection[] = [];
  locations.forEach((sourceLocation) => {
    const targets = sourceLocation.placement.binding?.target_placement_ids ?? [];
    targets.forEach((targetId) => {
      const targetLocation = locations.get(targetId);
      if (!targetLocation) return;
      const source = representative(sourceLocation);
      const target = representative(targetLocation);
      if (source && target && source.id === target.id) return;
      if (!source && !target) return;
      const style = connectionStyle(sourceLocation.placement.preset);
      const sourceCenter = source ? placementCenter(source) : null;
      const targetCenter = target ? placementCenter(target) : null;
      let externalPoint: { x: number; y: number } | null = null;
      let externalLabel = "";
      let points: number[];
      if (source && target && sourceCenter && targetCenter) {
        const endpoint = targetEdgePoint(sourceCenter, targetCenter, target);
        points = [sourceCenter.x, sourceCenter.y, endpoint.x, endpoint.y];
      } else if (source && sourceCenter) {
        externalPoint = { x: activeSpace.grid.columns * CELL_PX - 56, y: clamp(sourceCenter.y, 22, activeSpace.grid.rows * CELL_PX - 22) };
        externalLabel = `外: ${targetLocation.placement.name}`;
        points = [sourceCenter.x, sourceCenter.y, externalPoint.x, externalPoint.y];
      } else if (target && targetCenter) {
        externalPoint = { x: 56, y: clamp(targetCenter.y, 22, activeSpace.grid.rows * CELL_PX - 22) };
        externalLabel = `外: ${sourceLocation.placement.name}`;
        const endpoint = targetEdgePoint(externalPoint, targetCenter, target);
        points = [externalPoint.x, externalPoint.y, endpoint.x, endpoint.y];
      } else {
        return;
      }
      connections.push({
        key: `${sourceLocation.placement.id}:${targetId}:${activeSpace.id}`,
        points,
        selected: [sourceLocation.placement.id, targetId, source?.id, target?.id].includes(selectedId ?? ""),
        ...style,
        externalLabel,
        externalPoint,
        ariaLabel: `${sourceLocation.placement.name}から${targetLocation.placement.name}へ${style.kind}。${externalLabel ? "表示中の空間外へ接続" : "表示中の空間内で接続"}`,
      });
    });
  });
  return connections;
}

function placementCenter(placement: Placement) {
  return { x: (placement.x + placement.width / 2) * CELL_PX, y: (placement.y + placement.height / 2) * CELL_PX };
}

function targetEdgePoint(source: { x: number; y: number }, targetCenter: { x: number; y: number }, target: Placement) {
  const towardSource = { x: source.x - targetCenter.x, y: source.y - targetCenter.y };
  const edgeScale = towardSource.x === 0 && towardSource.y === 0 ? 0 : Math.min(
    towardSource.x === 0 ? Number.POSITIVE_INFINITY : (target.width * CELL_PX / 2 + 4) / Math.abs(towardSource.x),
    towardSource.y === 0 ? Number.POSITIVE_INFINITY : (target.height * CELL_PX / 2 + 4) / Math.abs(towardSource.y),
  );
  return { x: targetCenter.x + towardSource.x * edgeScale, y: targetCenter.y + towardSource.y * edgeScale };
}

function connectionStyle(preset: PlacementPreset) {
  if (preset === "watering_device" || preset === "mister") return { color: "#3184a3", selectedColor: "#0f6688", dash: [10, 6], kind: "潅水・噴霧" };
  if (preset === "sensor") return { color: "#9a8134", selectedColor: "#725b13", dash: [5, 6], kind: "計測" };
  if (preset === "camera") return { color: "#7d5793", selectedColor: "#55316b", dash: [12, 5], kind: "監視" };
  if (preset === "grow_light") return { color: "#b0841f", selectedColor: "#76570d", dash: [8, 5], kind: "補光" };
  return { color: "#58786d", selectedColor: "#2f5e4e", dash: [7, 5], kind: "設備制御" };
}

function clamp(value: number, minimum: number, maximum: number) {
  return Math.min(Math.max(value, minimum), Math.max(minimum, maximum));
}
