import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { Alert, Button, Skeleton, theme } from 'antd';

import { apiUrl } from '../../api';
import GraphViewer from './GraphViewer';
import styles from './GraphPage.module.css';

import type { GraphSnapshot, ParsedGraphSnapshot } from './GraphViewer';

type LoadState = 'loading' | 'loaded' | 'error';

const parseGraphSnapshot = (snapshot: GraphSnapshot): ParsedGraphSnapshot => {
    const positions = new Float32Array(snapshot.nodeCount * 3);
    for (let index = 0; index < snapshot.nodeCount; index += 1) {
        const writeIndex = index * 3;
        positions[writeIndex] = snapshot.x[index] ?? 0;
        positions[writeIndex + 1] = snapshot.y[index] ?? 0;
        positions[writeIndex + 2] = snapshot.z[index] ?? 0;
    }

    return {
        nodeCount: snapshot.nodeCount,
        edgeCount: snapshot.edgeCount,
        ids: Uint32Array.from(snapshot.ids),
        usernames: snapshot.usernames,
        positions,
        sizes: Float32Array.from(snapshot.size),
        inDegree: Uint32Array.from(snapshot.inDegree),
        outDegree: Uint32Array.from(snapshot.outDegree),
        src: Uint32Array.from(snapshot.src),
        dst: Uint32Array.from(snapshot.dst),
    };
};

const validateSnapshot = (snapshot: GraphSnapshot) => {
    const nodeKeys: Array<keyof GraphSnapshot> = ['ids', 'usernames', 'x', 'y', 'z', 'size', 'inDegree', 'outDegree'];
    const edgeKeys: Array<keyof GraphSnapshot> = ['src', 'dst'];

    for (const key of nodeKeys) {
        if ((snapshot[key] as unknown[]).length !== snapshot.nodeCount) {
            throw new Error(`Invalid graph payload: ${key} length does not match nodeCount.`);
        }
    }

    for (const key of edgeKeys) {
        if ((snapshot[key] as unknown[]).length !== snapshot.edgeCount) {
            throw new Error(`Invalid graph payload: ${key} length does not match edgeCount.`);
        }
    }

    for (const nodeIndex of snapshot.src.concat(snapshot.dst)) {
        if (nodeIndex < 0 || nodeIndex >= snapshot.nodeCount) {
            throw new Error('Invalid graph payload: edge index is outside the node range.');
        }
    }
};

const GraphPage: React.FC = () => {
    const [loadState, setLoadState] = useState<LoadState>('loading');
    const [graph, setGraph] = useState<ParsedGraphSnapshot | null>(null);
    const [error, setError] = useState<string>('');
    const { token } = theme.useToken();

    const loadGraph = useCallback(async () => {
        setLoadState('loading');
        setError('');

        try {
            const response = await fetch(`${apiUrl}/graph/sponsorships/snapshot`);
            const data = await response.json();

            if (!response.ok) {
                throw new Error(data.detail || data.error || `Graph request failed with status ${response.status}.`);
            }

            validateSnapshot(data);
            setGraph(parseGraphSnapshot(data));
            setLoadState('loaded');
        } catch (err) {
            setGraph(null);
            setError(err instanceof Error ? err.message : 'Failed to load sponsorship graph.');
            setLoadState('error');
        }
    }, []);

    useEffect(() => {
        loadGraph();
    }, [loadGraph]);

    const graphStats = useMemo(() => {
        if (!graph) return null;
        return {
            nodes: graph.nodeCount.toLocaleString(),
            edges: graph.edgeCount.toLocaleString(),
        };
    }, [graph]);

    return (
        <div className={styles.page}>
            <div className={styles.header}>
                <div className={styles.titleGroup}>
                    <h2 className={styles.title}>Sponsorship Graph</h2>
                    <p className={styles.subtitle} style={{ color: token.colorTextSecondary }}>
                        Active public sponsor relationships rendered from the precomputed graph layout.
                    </p>
                </div>
                {graphStats && (
                    <div className={styles.stats}>
                        <span className={styles.statPill} style={{ borderColor: token.colorBorder }}>
                            {graphStats.nodes} nodes
                        </span>
                        <span className={styles.statPill} style={{ borderColor: token.colorBorder }}>
                            {graphStats.edges} edges
                        </span>
                    </div>
                )}
            </div>

            {loadState === 'loading' && (
                <div className={styles.statusPanel} style={{ borderColor: token.colorBorder }}>
                    <div className={styles.statusContent}>
                        <Skeleton active paragraph={{ rows: 6 }} />
                    </div>
                </div>
            )}

            {loadState === 'error' && (
                <div className={styles.statusPanel} style={{ borderColor: token.colorBorder }}>
                    <div className={styles.statusContent}>
                        <Alert type="error" showIcon message="Graph unavailable" description={error} />
                        <Button type="primary" onClick={loadGraph}>Retry</Button>
                    </div>
                </div>
            )}

            {loadState === 'loaded' && graph && (
                <div className={styles.viewerShell} style={{ borderColor: token.colorBorder }}>
                    <GraphViewer graph={graph} />
                </div>
            )}
        </div>
    );
};

export default GraphPage;
