import React, { useCallback, useEffect, useMemo, useState } from 'react';
import DeckGL from '@deck.gl/react';
import { COORDINATE_SYSTEM, OrbitView } from '@deck.gl/core';
import { ArcLayer, LineLayer, ScatterplotLayer } from '@deck.gl/layers';
import { Button, Segmented, theme } from 'antd';
import { CloseOutlined } from '@ant-design/icons';

import styles from './GraphPage.module.css';

export interface GraphSnapshot {
    nodeCount: number;
    edgeCount: number;
    ids: number[];
    usernames: string[];
    profileUrls: string[];
    x: number[];
    y: number[];
    z: number[];
    size: number[];
    inDegree: number[];
    outDegree: number[];
    src: number[];
    dst: number[];
}

export interface ParsedGraphSnapshot {
    nodeCount: number;
    edgeCount: number;
    ids: Uint32Array;
    usernames: string[];
    profileUrls: string[];
    positions: Float32Array;
    sizes: Float32Array;
    inDegree: Uint32Array;
    outDegree: Uint32Array;
    src: Uint32Array;
    dst: Uint32Array;
}

interface HoverInfo {
    index: number;
    x: number;
    y: number;
}

interface ViewState {
    target: [number, number, number];
    rotationX: number;
    rotationOrbit: number;
    zoom: number;
}
type VisualProfileKey = 'constellation' | 'traffic' | 'structure';
type EdgeMode = 'line' | 'arc';
type PositionMode = 'layout' | 'wave' | 'shell';

interface VisualProfile {
    label: string;
    nodeColor: [number, number, number, number];
    edgeColor: [number, number, number, number];
    highlightColor: [number, number, number, number];
    edgeWidth: number;
    edgeMode: EdgeMode;
    positionMode: PositionMode;
    radiusScale: number;
    stroked: boolean;
    lineWidthMinPixels: number;
}

interface GraphViewerProps {
    graph: ParsedGraphSnapshot;
}

const INITIAL_VIEW_STATE = {
    target: [0, 0, 0] as [number, number, number],
    rotationX: 58,
    rotationOrbit: -28,
    zoom: -5,
} satisfies ViewState;

const VISUAL_PROFILES: Record<VisualProfileKey, VisualProfile> = {
    constellation: {
        label: 'Topology',
        nodeColor: [70, 137, 230, 220],
        edgeColor: [16, 185, 129, 42],
        highlightColor: [255, 255, 255, 255],
        edgeWidth: 1,
        edgeMode: 'line',
        positionMode: 'layout',
        radiusScale: 1,
        stroked: false,
        lineWidthMinPixels: 0,
    },
    traffic: {
        label: 'Arc Flow',
        nodeColor: [250, 204, 21, 210],
        edgeColor: [244, 63, 94, 70],
        highlightColor: [255, 255, 255, 255],
        edgeWidth: 1.2,
        edgeMode: 'arc',
        positionMode: 'wave',
        radiusScale: 0.85,
        stroked: false,
        lineWidthMinPixels: 0,
    },
    structure: {
        label: 'Shells',
        nodeColor: [226, 232, 240, 190],
        edgeColor: [56, 189, 248, 24],
        highlightColor: [15, 23, 42, 220],
        edgeWidth: 0.7,
        edgeMode: 'line',
        positionMode: 'shell',
        radiusScale: 0.72,
        stroked: true,
        lineWidthMinPixels: 1,
    },
};

const MOVE_KEYS = new Set(['w', 'a', 's', 'd', 'arrowup', 'arrowleft', 'arrowdown', 'arrowright', ' ', 'shift']);

const shouldIgnoreKeydown = (event: KeyboardEvent) => {
    const target = event.target as HTMLElement | null;
    if (!target) return false;
    return ['A', 'BUTTON', 'INPUT', 'SELECT', 'TEXTAREA'].includes(target.tagName);
};

const buildProfilePositions = (graph: ParsedGraphSnapshot, mode: PositionMode) => {
    if (mode === 'layout') return graph.positions;

    const positions = new Float32Array(graph.positions.length);

    for (let nodeIndex = 0; nodeIndex < graph.nodeCount; nodeIndex += 1) {
        const readIndex = nodeIndex * 3;
        const x = graph.positions[readIndex];
        const y = graph.positions[readIndex + 1];
        const z = graph.positions[readIndex + 2];

        if (mode === 'wave') {
            const totalDegree = graph.inDegree[nodeIndex] + graph.outDegree[nodeIndex];
            const lift = Math.log1p(totalDegree) * 12;
            positions[readIndex] = x;
            positions[readIndex + 1] = y;
            positions[readIndex + 2] = z + Math.sin(x * 0.006) * 85 + Math.cos(y * 0.006) * 85 + lift;
            continue;
        }

        const length = Math.max(1, Math.hypot(x, y, z));
        const size = graph.sizes[nodeIndex];
        const totalDegree = graph.inDegree[nodeIndex] + graph.outDegree[nodeIndex];
        const shellRadius = 280 + size * 42 + Math.log1p(totalDegree) * 18;
        positions[readIndex] = (x / length) * shellRadius;
        positions[readIndex + 1] = (y / length) * shellRadius;
        positions[readIndex + 2] = (z / length) * shellRadius;
    }

    return positions;
};

const GraphViewer: React.FC<GraphViewerProps> = ({ graph }) => {
    const [hoverInfo, setHoverInfo] = useState<HoverInfo | null>(null);
    const [selectedInfo, setSelectedInfo] = useState<HoverInfo | null>(null);
    const [viewState, setViewState] = useState<ViewState>(INITIAL_VIEW_STATE);
    const [visualProfileKey, setVisualProfileKey] = useState<VisualProfileKey>('constellation');
    const { token } = theme.useToken();
    const visualProfile = VISUAL_PROFILES[visualProfileKey];

    const profilePositions = useMemo(
        () => buildProfilePositions(graph, visualProfile.positionMode),
        [graph, visualProfile.positionMode],
    );

    const { sourcePositions, targetPositions } = useMemo(() => {
        const source = new Float32Array(graph.edgeCount * 3);
        const target = new Float32Array(graph.edgeCount * 3);

        for (let edgeIndex = 0; edgeIndex < graph.edgeCount; edgeIndex += 1) {
            const sourceNodeIndex = graph.src[edgeIndex] * 3;
            const targetNodeIndex = graph.dst[edgeIndex] * 3;
            const writeIndex = edgeIndex * 3;

            source[writeIndex] = profilePositions[sourceNodeIndex];
            source[writeIndex + 1] = profilePositions[sourceNodeIndex + 1];
            source[writeIndex + 2] = profilePositions[sourceNodeIndex + 2];
            target[writeIndex] = profilePositions[targetNodeIndex];
            target[writeIndex + 1] = profilePositions[targetNodeIndex + 1];
            target[writeIndex + 2] = profilePositions[targetNodeIndex + 2];
        }

        return { sourcePositions: source, targetPositions: target };
    }, [graph, profilePositions]);

    const moveView = useCallback((deltaX: number, deltaY: number, deltaZ: number) => {
        setViewState((current) => {
            const speed = Math.max(12, 42 * 2 ** Math.max(0, -current.zoom - 4));
            return {
                ...current,
                target: [
                    current.target[0] + deltaX * speed,
                    current.target[1] + deltaY * speed,
                    current.target[2] + deltaZ * speed,
                ] as [number, number, number],
            };
        });
    }, []);

    useEffect(() => {
        const handleKeydown = (event: KeyboardEvent) => {
            const key = event.key.toLowerCase();
            if (!MOVE_KEYS.has(key) || shouldIgnoreKeydown(event)) return;

            event.preventDefault();
            if (key === 'w' || key === 'arrowup') moveView(0, -1, 0);
            if (key === 's' || key === 'arrowdown') moveView(0, 1, 0);
            if (key === 'a' || key === 'arrowleft') moveView(-1, 0, 0);
            if (key === 'd' || key === 'arrowright') moveView(1, 0, 0);
            if (key === ' ') moveView(0, 0, 1);
            if (key === 'shift') moveView(0, 0, -1);
        };

        window.addEventListener('keydown', handleKeydown);
        return () => window.removeEventListener('keydown', handleKeydown);
    }, [moveView]);

    const layers = useMemo(() => {
        const edgeLayer = visualProfile.edgeMode === 'arc'
            ? new ArcLayer({
                id: 'sponsorship-edge-arcs',
                data: {
                    length: graph.edgeCount,
                    attributes: {
                        getSourcePosition: { value: sourcePositions, size: 3 },
                        getTargetPosition: { value: targetPositions, size: 3 },
                    },
                } as any,
                coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
                getSourceColor: visualProfile.edgeColor,
                getTargetColor: [56, 189, 248, Math.min(110, visualProfile.edgeColor[3] + 26)] as [number, number, number, number],
                getHeight: 0.42,
                getWidth: visualProfile.edgeWidth,
                pickable: false,
                widthUnits: 'pixels',
            })
            : new LineLayer({
                id: 'sponsorship-edges',
                data: {
                    length: graph.edgeCount,
                    attributes: {
                        getSourcePosition: { value: sourcePositions, size: 3 },
                        getTargetPosition: { value: targetPositions, size: 3 },
                    },
                } as any,
                coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
                getColor: visualProfile.edgeColor,
                getWidth: visualProfile.edgeWidth,
                opacity: 1,
                pickable: false,
                widthUnits: 'pixels',
            });

        return [
            edgeLayer,
            new ScatterplotLayer({
                id: 'sponsorship-nodes',
                data: {
                    length: graph.nodeCount,
                    attributes: {
                        getPosition: { value: profilePositions, size: 3 },
                        getRadius: { value: graph.sizes, size: 1 },
                    },
                } as any,
                coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
                getFillColor: visualProfile.nodeColor,
                getLineColor: visualProfile.highlightColor,
                lineWidthMinPixels: visualProfile.lineWidthMinPixels,
                radiusUnits: 'pixels',
                radiusScale: visualProfile.radiusScale,
                pickable: true,
                stroked: visualProfile.stroked,
                onHover: (info: any) => {
                    if (typeof info.index === 'number' && info.index >= 0) {
                        setHoverInfo({ index: info.index, x: info.x, y: info.y });
                    } else {
                        setHoverInfo(null);
                    }
                },
                onClick: (info: any) => {
                    if (typeof info.index === 'number' && info.index >= 0) {
                        setSelectedInfo({ index: info.index, x: info.x, y: info.y });
                    }
                },
            }),
        ];
    }, [graph, profilePositions, sourcePositions, targetPositions, visualProfile]);

    const activeInfo = selectedInfo ?? hoverInfo;
    const activeUser = activeInfo ? {
        username: graph.usernames[activeInfo.index],
        profileUrl: graph.profileUrls[activeInfo.index] || `https://github.com/${graph.usernames[activeInfo.index]}`,
        sponsors: graph.inDegree[activeInfo.index],
        sponsoring: graph.outDegree[activeInfo.index],
    } : null;

    return (
        <>
            <div className={styles.graphControls} style={{ background: token.colorBgElevated, borderColor: token.colorBorder }}>
                <Segmented
                    size="small"
                    value={visualProfileKey}
                    options={Object.entries(VISUAL_PROFILES).map(([value, profile]) => ({
                        label: profile.label,
                        value,
                    }))}
                    onChange={(value) => setVisualProfileKey(value as VisualProfileKey)}
                />
            </div>
            <DeckGL
                views={new OrbitView({ orbitAxis: 'Y' })}
                viewState={viewState}
                onViewStateChange={({ viewState: nextViewState }) => {
                    setViewState(nextViewState as ViewState);
                }}
                controller
                layers={layers}
                style={{ background: token.colorBgContainer }}
            />
            {activeInfo && activeUser && (
                <div
                    className={styles.tooltip}
                    style={{
                        left: activeInfo.x + 12,
                        top: activeInfo.y + 12,
                        color: token.colorText,
                        background: token.colorBgElevated,
                        borderColor: token.colorBorder,
                    }}
                >
                    {selectedInfo && (
                        <Button
                            aria-label="Close profile popup"
                            className={styles.tooltipClose}
                            icon={<CloseOutlined />}
                            size="small"
                            type="text"
                            onClick={() => setSelectedInfo(null)}
                        />
                    )}
                    <a
                        className={styles.tooltipLink}
                        href={activeUser.profileUrl}
                        target="_blank"
                        rel="noreferrer"
                    >
                        {activeUser.username}
                    </a>
                    <div style={{ color: token.colorTextSecondary }}>
                        {activeUser.sponsors.toLocaleString()} sponsors
                    </div>
                    <div style={{ color: token.colorTextSecondary }}>
                        {activeUser.sponsoring.toLocaleString()} sponsoring
                    </div>
                </div>
            )}
        </>
    );
};

export default GraphViewer;
