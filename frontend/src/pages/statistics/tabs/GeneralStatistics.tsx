import { useState } from "react";
import { Button, theme, Skeleton, Space } from "antd";
import styles from "../Statistics.module.css"
import { useEffect, useRef } from "react";
import gsap from "gsap";
import { apiUrl } from "../../../api";
import { Bar, Doughnut } from "react-chartjs-2";
import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    BarElement,
    Title,
    Tooltip,
    Legend,
    ArcElement,
} from 'chart.js';

import type { ChartData, ChartOptions } from "chart.js";
// import { MdOutlineExpandMore } from "react-icons/md";

ChartJS.register(
    CategoryScale,
    LinearScale,
    BarElement,
    Title,
    Tooltip,
    Legend,
    ArcElement,
);

const GeneralStatistics = ({ playSignal }: { playSignal: number }) => {

    interface BriefStats {
        total_users: number;
        total_sponsorships: number;
        top_sponsoring: {
            username: string;
            avatar_url: string;
            total_sponsoring: number;
        };
        top_sponsored: {
            username: string;
            avatar_url: string;
            total_sponsors: number;
        };
    }

    const [briefData, setBriefData] = useState<BriefStats>();
    const [isLoading, setIsLoading] = useState(true);

    const getBrief = async () => {
        try {
            const response = await fetch(`${apiUrl}/stats/brief`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json() as BriefStats;
            setBriefData(data);
        } catch (error) {
            console.log(error);
        } finally {
            setIsLoading(false);
        }
    };


    const containerRef = useRef<HTMLDivElement>(null);
    const { token } = theme.useToken();
    useEffect(() => {
        const ctx = gsap.context(() => {
            gsap.from(`.${styles.Card}`, {
                opacity: 0,
                y: 24,
                scale: 0.98,
                duration: 0.6,
                ease: "power2.out",
                stagger: 0.08,
            });
        }, containerRef);
        return () => ctx.revert();
    }, [playSignal]);

    useEffect(() => {
        getBrief();
    }, []);

    return (
        <>
            <section className="h-full flex flex-col min-h-0 overflow-hidden">
                {/* <div>
                    <Button type="text" className="flex items-center" >Advanced Statistics <MdOutlineExpandMore className="text-[20px]" /></Button>
                </div> */}
                <div
                    ref={containerRef}
                    className={styles.statsGrid}
                >
                    <div
                        style={{ borderColor: token.colorBorder, backgroundColor: token.cardBg }}
                        className={`${styles.Card} ${styles.summaryCard} md:col-span-3 xl:col-span-3`}
                    >
                        {isLoading ? <Skeleton active paragraph={{ rows: 1 }} /> : (
                            <>
                                <h1 className="font-medium">Total Active Entities</h1>
                                <h2 style={{ color: token.colorTextSecondary }}>{briefData?.total_users}</h2>
                            </>
                        )}
                    </div>
                    <div
                        style={{ borderColor: token.colorBorder, backgroundColor: token.cardBg }}
                        className={`${styles.Card} ${styles.summaryCard} md:col-span-3 xl:col-span-3`}
                    >
                        {isLoading ? <Skeleton active paragraph={{ rows: 1 }} /> : (
                            <>
                                <h1 className="font-medium">Total Sponsorships</h1>
                                <h2 style={{ color: token.colorTextSecondary }}>{briefData?.total_sponsorships}</h2>
                            </>
                        )}
                    </div>
                    <div
                        style={{ borderColor: token.colorBorder, backgroundColor: token.cardBg }}
                        className={`${styles.Card} ${styles.summaryCard} md:col-span-3 xl:col-span-3`}
                    >
                        {isLoading ? <Skeleton active paragraph={{ rows: 1 }} /> : (
                            <>
                                <h1 className="font-medium">Top Sponsoring Entity</h1>
                                <span className='flex items-center justify-start gap-2'>
                                    <img src={briefData?.top_sponsoring.avatar_url} alt={briefData?.top_sponsoring.username} className='w-8 h-8 rounded-full' />
                                    <h2 style={{ color: token.colorTextSecondary }} className='pb-1 text-[18px] font-semibold'>{briefData?.top_sponsoring.username}</h2>
                                </span>
                            </>
                        )}
                    </div>
                    <div
                        style={{ borderColor: token.colorBorder, backgroundColor: token.cardBg }}
                        className={`${styles.Card} ${styles.summaryCard} md:col-span-3 xl:col-span-3`}
                    >
                        {isLoading ? <Skeleton active paragraph={{ rows: 1 }} /> : (
                            <>
                                <h1 className="font-medium">Top Sponsored Entity</h1>
                                <span className='flex items-center justify-start gap-2'>
                                    <img src={briefData?.top_sponsored.avatar_url} alt={briefData?.top_sponsored.username} className='w-8 h-8 rounded-full' />
                                    <h2 style={{ color: token.colorTextSecondary }} className='pb-1 text-[18px] font-semibold'>{briefData?.top_sponsored.username}</h2>
                                </span>
                            </>
                        )}
                    </div>

                    {/* Largest graph */}
                    <div
                        style={{ borderColor: token.colorBorder, backgroundColor: token.cardBg }}
                        className={`${styles.Card} ${styles.barGraphCard} md:col-span-4 xl:col-span-8 md:row-span-4 xl:row-span-6`}
                    >
                        <LocationRolesGraph />
                    </div>

                    {/* Right-side graphs */}
                    <div
                        style={{ borderColor: token.colorBorder, backgroundColor: token.cardBg }}
                        className={`${styles.Card} ${styles.pieGraphCard} md:col-span-2 xl:col-span-4 md:row-span-2 xl:row-span-3`}
                    >
                        <SponsorshipRolesByTypeGraph />
                    </div>
                    <div
                        style={{ borderColor: token.colorBorder, backgroundColor: token.cardBg }}
                        className={`${styles.Card} ${styles.pieGraphCard} md:col-span-2 xl:col-span-4 md:row-span-2 xl:row-span-3`}
                    >
                        <GenderDistributionGraph />
                    </div>
                </div>
            </section>
        </>
    );
}

export default GeneralStatistics;


const LocationRolesGraph = () => {
    interface LocationRole {
        location: string;
        sponsored_only: number;
        sponsoring_only: number;
        both_roles: number;
        total_active: number;
    }
    const { token } = theme.useToken();
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [chartData, setChartData] = useState<ChartData<'bar'>>({ labels: [], datasets: [] });

    const chartOptions: ChartOptions<'bar'> = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { display: true, position: "top", align: "start", labels: { color: token.colorTextSecondary } },
            tooltip: {
                backgroundColor: '#1f2937', titleColor: '#e5e7eb', bodyColor: '#fff',
                borderColor: '#4b5563', borderWidth: 1, mode: 'index', intersect: false
            },
        },
        scales: { x: { stacked: true }, y: { stacked: true } }
    };

    useEffect(() => {
        const fetchData = async () => {
            try {
                const response = await fetch(`${apiUrl}/location-sponsorship-roles`);
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const data: LocationRole[] = await response.json();

                const topData = data.slice(0, 20);

                setChartData({
                    labels: topData.map(d => d.location),
                    datasets: [
                        {
                            label: 'Sponsored Only', data: topData.map(d => d.sponsored_only),
                            backgroundColor: 'rgba(181, 97, 146, 0.7)', borderColor: 'rgba(255, 128, 202, 1)',
                            borderWidth: 1.5, stack: 'Stack 0', barPercentage: 1, categoryPercentage: 0.8, borderRadius: 6,
                        },
                        {
                            label: 'Sponsoring Only', data: topData.map(d => d.sponsoring_only),
                            backgroundColor: 'rgba(117, 91, 165, 0.7)', borderColor: 'rgba(180, 140, 255, 1)',
                            borderWidth: 1.5, stack: 'Stack 0', barPercentage: 1, categoryPercentage: 0.8, borderRadius: 6,
                        },
                        {
                            label: 'Both Roles', data: topData.map(d => d.both_roles),
                            backgroundColor: 'rgba(93, 138, 159, 0.7)', borderColor: 'rgba(137, 207, 240, 1)',
                            borderWidth: 1.5, stack: 'Stack 0', barPercentage: 1, categoryPercentage: 0.8, borderRadius: 6,
                        },
                    ],
                });
            } catch (error) {
                console.error("Failed to fetch location roles data:", error);
            } finally {
                setIsLoading(false);
            }
        };
        fetchData();
    }, []);

    return (
        <div className={styles.chartShell}>
            {isLoading ? <Skeleton active /> : (
                <div className={`${styles.scrollChartShell} custom-scrollbar`}>
                    <h1 className="font-medium pl-0.5 text-nowrap pb-3">Sponsorship Roles by Location (Top 20)</h1>
                    <div className={styles.locationBarCanvas}>
                        <Bar options={chartOptions} data={chartData} />
                    </div>
                </div>
            )}
        </div>
    );
};

const SponsorshipRolesByTypeGraph = () => {
    interface RolesByType {
        entity_type: string;
        active_sponsored_only: number;
        active_sponsoring_only: number;
        active_both: number;
    }
    const { token } = theme.useToken();
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [chartData, setChartData] = useState<ChartData<'doughnut'>>({ labels: [], datasets: [] });
    const [dataType, setDataType] = useState<'user' | 'organization' | 'total'>('total');
    const [allData, setAllData] = useState<{
        user: ChartData<'doughnut'>,
        organization: ChartData<'doughnut'>,
        total: ChartData<'doughnut'>
    } | null>(null);

    const chartOptions: ChartOptions<'doughnut'> = {
        responsive: true, maintainAspectRatio: false,
        plugins: {
            legend: { display: true, position: "right", labels: { color: token.colorTextSecondary } },
            tooltip: {
                backgroundColor: '#1f2937', titleColor: '#e5e7eb', bodyColor: '#fff',
                borderColor: '#4b5563', borderWidth: 1,
                callbacks: {
                    label: (context) => {
                        const label = context.label || '';
                        const value = context.raw as number;
                        const total = (context.chart.data.datasets[0].data as number[]).reduce((a, b) => a + b, 0);
                        const percentage = total > 0 ? ((value / total) * 100).toFixed(1) + '%' : '0%';
                        return `${label}: ${value} (${percentage})`;
                    }
                }
            },
        },
    };

    useEffect(() => {
        const fetchData = async () => {
            try {
                const response = await fetch(`${apiUrl}/sponsorship-roles-by-type`);
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const data: RolesByType[] = await response.json();

                const createChartData = (row: RolesByType | undefined): ChartData<'doughnut'> => {
                    if (!row) return { labels: [], datasets: [] };
                    return {
                        labels: ["Sponsored Only", "Sponsoring Only", "Both Roles"],
                        datasets: [{
                            data: [
                                Number(row.active_sponsored_only),
                                Number(row.active_sponsoring_only),
                                Number(row.active_both)
                            ],
                            backgroundColor: ['rgba(181, 97, 146, 0.7)', 'rgba(117, 91, 165, 0.7)', 'rgba(93, 138, 159, 0.7)'],
                            borderColor: ['rgba(255, 128, 202, 1)', 'rgba(180, 140, 255, 1)', 'rgba(137, 207, 240, 1)'],
                            borderWidth: 2,
                        }],
                    };
                };

                const allChartData = {
                    user: createChartData(data.find(d => d.entity_type === 'User')),
                    organization: createChartData(data.find(d => d.entity_type === 'Organization')),
                    total: createChartData(data.find(d => d.entity_type === 'Overall Total')),
                };

                setAllData(allChartData);
                setChartData(allChartData.total);

            } catch (error) {
                console.error("Failed to fetch sponsorship roles by type:", error);
            } finally {
                setIsLoading(false);
            }
        };
        fetchData();
    }, []);

    useEffect(() => {
        if (allData) {
            if (dataType === 'user') setChartData(allData.user);
            else if (dataType === 'organization') setChartData(allData.organization);
            else setChartData(allData.total);
        }
    }, [dataType, allData]);

    return (
        <div className={styles.pieGraphShell}>
            {isLoading ? <Skeleton active /> : (
                <>
                    <div className={styles.chartHeader}>
                        <h1 className="font-medium">Sponsorship Roles By Type</h1>
                        <Space.Compact>
                            <Button type={dataType === 'user' ? 'primary' : 'default'} onClick={() => setDataType('user')}>User</Button>
                            <Button type={dataType === 'organization' ? 'primary' : 'default'} onClick={() => setDataType('organization')}>Org</Button>
                            <Button type={dataType === 'total' ? 'primary' : 'default'} onClick={() => setDataType('total')}>Total</Button>
                        </Space.Compact>
                    </div>
                    <div className={styles.pieChartBody}>
                        <Doughnut options={chartOptions} data={chartData} />
                    </div>
                </>
            )}
        </div>
    );
};

const GenderDistributionGraph = () => {
    interface GenderDataRow {
        Category: string;
        Male: string;
        Female: string;
        Other: string;
        Unknown: string;
        Total: number;
    }

    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [chartData, setChartData] = useState<ChartData<'doughnut'>>({ labels: [], datasets: [] });
    const [dataType, setDataType] = useState<'specified' | 'inferred'>('specified');
    const [allData, setAllData] = useState<{ specified: ChartData<'doughnut'>, inferred: ChartData<'doughnut'> } | null>(null);
    const { token } = theme.useToken();

    const chartOptions: ChartOptions<'doughnut'> = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: { display: true, position: "right", labels: { color: token.colorTextSecondary } },
            tooltip: {
                backgroundColor: '#1f2937', titleColor: '#e5e7eb', bodyColor: '#fff',
                borderColor: '#4b5563', borderWidth: 1,
                callbacks: {
                    label: (context) => {
                        const label = context.label || '';
                        const value = context.raw as number;
                        const total = (context.chart.data.datasets[0].data as number[]).reduce((a, b) => a + b, 0);
                        const percentage = total > 0 ? ((value / total) * 100).toFixed(1) + '%' : '0%';
                        return `${label}: ${value} (${percentage})`;
                    }
                }
            },
        },
    };

    useEffect(() => {
        const fetchData = async () => {
            try {
                const response = await fetch(`${apiUrl}/gender-distribution-table`);
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const data: GenderDataRow[] = await response.json();

                const specifiedRow = data.find(d => d.Category === 'Pronouns Specified');
                const inferredRow = data.find(d => d.Category === 'Pronouns Not Specified (Inferred)');

                const parseCount = (str: string) => parseInt(str.split(' ')[0], 10) || 0;

                const createChartData = (row: GenderDataRow | undefined): ChartData<'doughnut'> => {
                    if (!row) return { labels: [], datasets: [] };
                    return {
                        labels: ['Male', 'Female', 'Other', 'Unknown'],
                        datasets: [{
                            data: [
                                parseCount(row.Male),
                                parseCount(row.Female),
                                parseCount(row.Other),
                                parseCount(row.Unknown),
                            ],
                            backgroundColor: [
                                'rgba(55, 135, 188, 0.5)',
                                'rgba(255, 99, 132, 0.5)',
                                'rgba(75, 192, 192, 0.5)',
                                'rgba(105, 105, 105, 0.391)',
                            ],
                            borderColor: [
                                'rgba(54, 162, 235, 1)',
                                'rgba(255, 99, 132, 1)',
                                'rgba(75, 192, 192, 1)',
                                'rgba(90, 90, 90, 0.63)',
                            ],
                            borderWidth: 2,
                        }],
                    };
                };

                const allChartData = {
                    specified: createChartData(specifiedRow),
                    inferred: createChartData(inferredRow),
                };

                setAllData(allChartData);
                setChartData(allChartData.specified);

            } catch (error) {
                console.error("Failed to fetch gender distribution table data:", error);
            } finally {
                setIsLoading(false);
            }
        };
        fetchData();
    }, []);

    useEffect(() => {
        if (allData) {
            setChartData(dataType === 'specified' ? allData.specified : allData.inferred);
        }
    }, [dataType, allData]);

    return (
        <div className={styles.pieGraphShell}>
            {isLoading ? <Skeleton active /> : (
                <>
                    <div className={styles.chartHeader}>
                        <h1 className="font-medium">User Gender Distribution</h1>
                        <Space.Compact>
                            <Button
                                type={dataType === 'specified' ? 'primary' : 'default'}
                                onClick={() => setDataType('specified')}
                            >
                                Specified
                            </Button>
                            <Button
                                type={dataType === 'inferred' ? 'primary' : 'default'}
                                onClick={() => setDataType('inferred')}
                            >
                                Inferred
                            </Button>
                        </Space.Compact>
                    </div>
                    <div className={styles.pieChartBody}>
                        <Doughnut options={chartOptions} data={chartData} />
                    </div>
                </>
            )}
        </div>
    );
};
