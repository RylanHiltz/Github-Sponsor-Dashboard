import React, { useMemo, useState } from 'react';
import DeckGL from '@deck.gl/react';
import { COORDINATE_SYSTEM, OrbitView } from '@deck.gl/core';
import { LineLayer, ScatterplotLayer } from '@deck.gl/layers';
import { theme } from 'antd';

import styles from './GraphPage.module.css';

export interface GraphSnapshot {
    nodeCount: number;
    edgeCount: number;
    ids: number[];
    usernames: string[];
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

interface GraphViewerProps {
    graph: ParsedGraphSnapshot;
}

const INITIAL_VIEW_STATE = {
    target: [0, 0, 0] as [number, number, number],
    rotationX: 58,
    rotationOrbit: -28,
    zoom: -5,
};

const NODE_COLOR: [number, number, number, number] = [70, 137, 230, 220];
const EDGE_COLOR: [number, number, number, number] = [16, 185, 129, 42];
const HIGHLIGHT_COLOR: [number, number, number, number] = [255, 255, 255, 255];

const GraphViewer: React.FC<GraphViewerProps> = ({ graph }) => {
    const [hoverInfo, setHoverInfo] = useState<HoverInfo | null>(null);
    const { token } = theme.useToken();

    const { sourcePositions, targetPositions } = useMemo(() => {
        const source = new Float32Array(graph.edgeCount * 3);
        const target = new Float32Array(graph.edgeCount * 3);

        for (let edgeIndex = 0; edgeIndex < graph.edgeCount; edgeIndex += 1) {
            const sourceNodeIndex = graph.src[edgeIndex] * 3;
            const targetNodeIndex = graph.dst[edgeIndex] * 3;
            const writeIndex = edgeIndex * 3;

            source[writeIndex] = graph.positions[sourceNodeIndex];
            source[writeIndex + 1] = graph.positions[sourceNodeIndex + 1];
            source[writeIndex + 2] = graph.positions[sourceNodeIndex + 2];
            target[writeIndex] = graph.positions[targetNodeIndex];
            target[writeIndex + 1] = graph.positions[targetNodeIndex + 1];
            target[writeIndex + 2] = graph.positions[targetNodeIndex + 2];
        }

        return { sourcePositions: source, targetPositions: target };
    }, [graph]);

    const layers = useMemo(() => [
        new LineLayer({
            id: 'sponsorship-edges',
            data: {
                length: graph.edgeCount,
                attributes: {
                    getSourcePosition: { value: sourcePositions, size: 3 },
                    getTargetPosition: { value: targetPositions, size: 3 },
                },
            } as any,
            coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
            getColor: EDGE_COLOR,
            getWidth: 1,
            opacity: 1,
            pickable: false,
            widthUnits: 'pixels',
        }),
        new ScatterplotLayer({
            id: 'sponsorship-nodes',
            data: {
                length: graph.nodeCount,
                attributes: {
                    getPosition: { value: graph.positions, size: 3 },
                    getRadius: { value: graph.sizes, size: 1 },
                },
            } as any,
            coordinateSystem: COORDINATE_SYSTEM.CARTESIAN,
            getFillColor: NODE_COLOR,
            getLineColor: HIGHLIGHT_COLOR,
            lineWidthMinPixels: 0,
            radiusUnits: 'pixels',
            radiusScale: 1,
            pickable: true,
            stroked: false,
            onHover: (info: any) => {
                if (typeof info.index === 'number' && info.index >= 0) {
                    setHoverInfo({ index: info.index, x: info.x, y: info.y });
                } else {
                    setHoverInfo(null);
                }
            },
        }),
    ], [graph, sourcePositions, targetPositions]);

    const hoveredUser = hoverInfo ? {
        username: graph.usernames[hoverInfo.index],
        sponsors: graph.inDegree[hoverInfo.index],
        sponsoring: graph.outDegree[hoverInfo.index],
    } : null;

    return (
        <>
            <DeckGL
                views={new OrbitView({ orbitAxis: 'Y' })}
                initialViewState={INITIAL_VIEW_STATE}
                controller
                layers={layers}
                style={{ background: token.colorBgContainer }}
            />
            {hoverInfo && hoveredUser && (
                <div
                    className={styles.tooltip}
                    style={{
                        left: hoverInfo.x + 12,
                        top: hoverInfo.y + 12,
                        color: token.colorText,
                        background: token.colorBgElevated,
                        borderColor: token.colorBorder,
                    }}
                >
                    <div className="font-semibold">{hoveredUser.username}</div>
                    <div style={{ color: token.colorTextSecondary }}>
                        {hoveredUser.sponsors.toLocaleString()} sponsors
                    </div>
                    <div style={{ color: token.colorTextSecondary }}>
                        {hoveredUser.sponsoring.toLocaleString()} sponsoring
                    </div>
                </div>
            )}
        </>
    );
};

export default GraphViewer;
