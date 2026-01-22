import React, { useEffect, useMemo } from 'react' // Import useMemo
import { useState } from 'react'
import { useNavigate, useParams } from 'react-router'
import styles from "./User.module.css"
import { Button, Skeleton, theme, Segmented } from 'antd' // Import Segmented
import { apiUrl } from '../../api'
import { Line } from 'react-chartjs-2';
import { IoChevronBackOutline } from "react-icons/io5";

import type { UserModel, YearlyActivityData } from '../../types/UserModel'
import type { ChartData, ChartOptions } from 'chart.js';

import {
    Chart as ChartJS,
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend,
    Filler,
} from 'chart.js';

ChartJS.register(
    CategoryScale,
    LinearScale,
    PointElement,
    LineElement,
    Title,
    Tooltip,
    Legend,
    Filler
);

type ViewMode = 'Activity' | 'Sponsorships';

const User: React.FC = () => {

    const { token } = theme.useToken();
    const { id } = useParams<{ id: string }>();
    const [user, setUser] = useState<UserModel>();
    const [isLoading, setIsLoading] = useState<boolean>(true);
    const [viewMode, setViewMode] = useState<ViewMode>('Activity');
    const [historyInterval, setHistoryInterval] = useState<'W' | 'M'>('W'); // New State
    const [sponsorshipHistory, setSponsorshipHistory] = useState<any[]>([]); // Store API data
    const navigate = useNavigate();

    // -- CHART DATA LOGIC --

    // 1. Calculate Activity Data (Existing Logic, wrapped in useMemo)
    const activityChartData: ChartData<'line'> = useMemo(() => {
        if (!user || !user.yearly_activity_data) return { labels: [], datasets: [] };

        const labels: string[] = [];
        const datasets = {
            commits: [] as number[],
            issues: [] as number[],
            prs: [] as number[],
            reviews: [] as number[]
        };

        (user.yearly_activity_data ?? []).slice().reverse().forEach((d: YearlyActivityData) => {
            labels.push(d.year.toString());
            datasets.commits.push(d.activity_data.commits);
            datasets.issues.push(d.activity_data.issues);
            datasets.prs.push(d.activity_data.pull_requests);
            datasets.reviews.push(d.activity_data.reviews);
        });

        return {
            labels,
            datasets: [
                {
                    label: 'Commits',
                    data: datasets.commits,
                    borderColor: '#A855F7',
                    backgroundColor: 'rgba(168, 85, 247, 0.2)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                },
                {
                    label: 'Issues',
                    data: datasets.issues,
                    borderColor: '#EC4899',
                    backgroundColor: 'rgba(236, 72, 153, 0.2)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                },
                {
                    label: 'Pull Requests',
                    data: datasets.prs,
                    borderColor: '#22D3EE',
                    backgroundColor: 'rgba(34, 211, 238, 0.2)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                },
                {
                    label: 'Code Reviews',
                    data: datasets.reviews,
                    borderColor: '#60A5FA',
                    backgroundColor: 'rgba(96, 165, 250, 0.2)',
                    fill: true,
                    tension: 0.4,
                    pointRadius: 3,
                },
            ]
        };
    }, [user]);

    // 2. Calculate Sponsorship Data (Placeholder logic until backend sends history)
    const sponsorshipChartData: ChartData<'line'> = useMemo(() => {
        if (!sponsorshipHistory || sponsorshipHistory.length === 0) return { labels: [], datasets: [] };

        return {
            labels: sponsorshipHistory.map((d: any) => d.date),
            datasets: [{
                label: 'Active Sponsors',
                data: sponsorshipHistory.map((d: any) => d.active_count),
                borderColor: '#10B981',
                backgroundColor: 'rgba(16, 185, 129, 0.2)',
                fill: true,
                tension: 0.4,
                pointRadius: 4,
            }]
        };
    }, [sponsorshipHistory]);

    // Choose which data to display
    const currentChartData = viewMode === 'Activity' ? activityChartData : sponsorshipChartData;

    const chartOptions: ChartOptions<'line'> = {
        responsive: true,
        maintainAspectRatio: false,
        plugins: {
            legend: {
                display: true,
                labels: { color: token.colorTextSecondary }
            },
            tooltip: {
                backgroundColor: '#1f2937',
                titleColor: '#e5e7eb',
                bodyColor: '#fff',
                borderColor: '#4b5563',
                borderWidth: 1,
                mode: 'index',
                intersect: false
            },
        },
        scales: {
            x: {
                display: true,
                grid: { color: token.gridColor },
                ticks: { color: '#9ca3af' },
            },
            y: {
                beginAtZero: true,
                grid: { color: token.gridColor },
                ticks: { color: '#9ca3af' },
            },
        },
    };

    if (!id) return null;

    const navigateLeaderboard = () => {
        navigate("/");
    };

    const getUserData = async () => {
        try {
            const response = await fetch(`${apiUrl}/user/${id}`)
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data = await response.json();
            setUser(data);
        } catch (error) {
            console.log(error)
        } finally {
            setIsLoading(false);
        }
    }

    // Fetch History when ID or Interval changes
    useEffect(() => {
        const fetchHistory = async () => {
            if (!id) return;
            try {
                // Pass interval param
                const res = await fetch(`${apiUrl}/user/${id}/sponsorship-history?interval=${historyInterval}`);
                const data = await res.json();
                setSponsorshipHistory(data);
            } catch (e) {
                console.error(e);
            }
        };
        fetchHistory();
    }, [id, historyInterval]);

    useEffect(() => {
        getUserData();
    }, [id]);

    return (
        <>
            <div className='h-full'>
                <div className="flex flex-col h-full px-5 gap-5 pb-5 overflow-hidden">
                    <Button className='w-min' type='text' onClick={navigateLeaderboard}><IoChevronBackOutline /> Back To Dashboard</Button>

                    <section className='flex-grow grid grid-cols-[2fr_minmax(20em,28em)] 2xl:grid-cols-[2fr_minmax(24em,36em)] grid-rows-[minmax(0,1fr)_minmax(0,1fr)] gap-5 min-h-0'>

                        {/* TOP LEFT: USER PROFILE (Unchanged) */}
                        <div className={`${styles.profileCard} row-span-1 flex flex-col justify-between border-solid overflow-hidden p-6`} style={{ borderColor: token.colorBorder }}>
                            <div className='flex flex-col gap-3 pr-1'>
                                <div className='flex items-center gap-4'>
                                    {isLoading == false ? (
                                        <img src={user?.avatar_url} alt="user profile image" className='w-[5em] h-[5em] rounded-full' />
                                    ) : (<Skeleton />)}
                                    <div>
                                        {user?.name ? (
                                            <span className='flex items-center gap-2'>
                                                <h1 className='text-2xl font-semibold'>{user.name}</h1>
                                            </span>
                                        ) : (
                                            <span className='flex items-center gap-2'>
                                                <h1 className='text-2xl font-semibold'>{user?.username}</h1>
                                            </span>
                                        )}
                                        <p className='text-lg font-light text-gray-400'>{user?.username}</p>
                                    </div>
                                </div>

                                {user?.bio && <p className='text-base'>{user?.bio}</p>}

                                <div className='flex flex-col gap-1  mt-2'>
                                    {user?.company && (
                                        <span className='flex items-center gap-2'>
                                            <p>Company</p>
                                            <p className='font-medium'>{user.company}</p>
                                        </span>
                                    )}
                                    {user?.location && (
                                        <span className='flex items-center gap-2'>
                                            <p>Location: </p>
                                            <p className='font-medium'>{user.location}</p>
                                        </span>
                                    )}
                                    {user?.email && (
                                        <span className='flex items-center gap-2'>
                                            <p>Email: </p>
                                            <a href={`mailto:${user.email}`} className='hover:underline'>{user.email}</a>
                                        </span>
                                    )}
                                    {user?.profile_url && (
                                        <span className='flex items-center gap-2'>
                                            <p>Github: </p>
                                            <a href={`${user.profile_url}`}>{user?.username}</a>
                                        </span>
                                    )}
                                    {user?.twitter_username && (
                                        <span className='flex items-center gap-2'>
                                            <p>Twitter: </p>
                                            <a href={`https:twitter.com/${user.twitter_username}`}>{user.twitter_username}</a>
                                        </span>
                                    )}
                                </div>
                            </div>
                            <div className='flex gap-4 text-base justify-between items-center'>
                                <div className='flex gap-2 text-gray-300'>
                                    <span><span className='font-bold text-white'>{user?.followers?.toLocaleString()}</span> followers</span>
                                    <span>·</span>
                                    <span><span className='font-bold text-white'>{user?.following?.toLocaleString()}</span> following</span>
                                </div>
                                <Button
                                    className='font-semibold border-opacity-50 hover:border-opacity-100'
                                    type='primary'
                                    ghost
                                    href={user?.profile_url} // filepath: /Users/rylanhiltz/Developer/mini-computer-vm/Github-Sponsor-Dashboard-ICSE-2026/frontend/src/pages/users/User.tsx
                                    target='_blank'
                                >
                                    Visit Profile
                                </Button>
                            </div>
                        </div>

                        {/* RIGHT COLUMN: STATS CARD (Unchanged) */}
                        <div className={`${styles.profileCard} row-span-2 flex flex-col min-h-0 p-6`} style={{ borderColor: token.colorBorder }}>
                            {/* ... existing stats content ... */}
                            <div className="flex flex-col flex-1 gap-4 xl:gap-5 pr-2 overflow-y-hidden">
                                {(() => {
                                    const StatRow = ({ label, value, format }: { label: string, value: any, format?: 'currency' | 'date' | 'number' }) => {
                                        let displayValue = 'N/A';
                                        if (value != null) {
                                            switch (format) {
                                                case 'currency':
                                                    displayValue = `$${Number(value).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
                                                    break;
                                                case 'date':
                                                    displayValue = new Date(value).toLocaleDateString('en-US', { year: 'numeric', month: 'short', day: 'numeric' });
                                                    break;
                                                default:
                                                    displayValue = value.toLocaleString();
                                            }
                                        }
                                        return (
                                            <div className="flex justify-between items-center py-1.5 xl:py-2 2xl:py-2.5 border-b border-[#434343] last:border-b-0">
                                                <p className="text-gray-400 text-xs xl:text-sm">{label}</p>
                                                {isLoading ? (
                                                    <Skeleton.Input active={true} size="small" style={{ width: 100 }} />
                                                ) : (
                                                    <p className="text-sm xl:text-base font-semibold ">{displayValue}</p>
                                                )}
                                            </div>
                                        );
                                    };
                                    return (
                                        <>
                                            {/* ... Stat Groups ... */}
                                            <div>
                                                <h2 className="text-base xl:text-lg font-semibold mb-1 xl:mb-2">User Activity</h2>
                                                <div className="rounded-lg pl-2 2xl:pl-4">
                                                    <StatRow label="Total Commits" value={user?.total_commits} />
                                                    <StatRow label="Total Issues" value={user?.total_issues} />
                                                    <StatRow label="Total Pull Requests" value={user?.total_pull_requests} />
                                                    <StatRow label="Total Code Reviews" value={user?.total_reviews} />
                                                </div>
                                            </div>
                                            {/* ... Sponsorships Group ... */}
                                            <div>
                                                <h2 className="text-base xl:text-lg font-semibold mb-1 xl:mb-2">Sponsorships</h2>
                                                <div className="rounded-lg pl-2 2xl:pl-4">
                                                    <StatRow label="Sponsors" value={user?.total_sponsors} />
                                                    <StatRow label="Sponsoring" value={user?.total_sponsoring} />
                                                    <StatRow label="Minimum Tier" value={user?.min_sponsor_cost} format="currency" />
                                                    <StatRow label="Est. Min Earnings" value={null} format="currency" />
                                                </div>
                                            </div>
                                            {/* ... Account Data Group ... */}
                                            <div>
                                                <h2 className="text-base xl:text-lg font-semibold mb-1 xl:mb-2">Account Data</h2>
                                                <div className="rounded-lg pl-2 2xl:pl-4">
                                                    <StatRow label="Public Repositories" value={user?.public_repos} />
                                                    <StatRow label="Public Gists" value={user?.public_gists} />
                                                    <StatRow label="Account Created" value={user?.github_created_at} format="date" />
                                                    <StatRow label="Last Checked" value={user?.last_scraped} format="date" />
                                                </div>
                                            </div>
                                        </>
                                    );
                                })()}
                            </div>
                        </div>

                        {/* BOTTOM LEFT: CHART CARD */}
                        <div className={`${styles.profileCard} row-span-1 flex flex-col min-h-0 gap-5 p-5`} style={{ borderColor: token.colorBorder }}>
                            <div className='flex justify-between items-center'>
                                <div className="flex gap-4 items-center">
                                    <h2 className="text-xl font-semibold">
                                        {viewMode === 'Activity' ? 'Visualized User Activity' : 'Sponsorship Growth'}
                                    </h2>

                                    {/* Show Time Toggle ONLY when looking at Sponsorships */}
                                    {viewMode === 'Sponsorships' && (
                                        <Segmented
                                            size="small"
                                            options={[
                                                { label: 'Weekly', value: 'W' },
                                                { label: 'Monthly', value: 'M' }
                                            ]}
                                            value={historyInterval}
                                            onChange={(val) => setHistoryInterval(val as 'W' | 'M')}
                                        />
                                    )}
                                </div>

                                <Segmented<ViewMode>
                                    options={['Activity', 'Sponsorships']}
                                    value={viewMode}
                                    onChange={(value) => setViewMode(value)}
                                    disabled={isLoading}
                                />
                            </div>
                            <div className='relative flex-grow min-h-0 w-full'>
                                {isLoading ? (
                                    <Skeleton active />
                                ) : (
                                    <Line options={chartOptions} data={currentChartData} />
                                )}
                            </div>
                        </div>

                    </section>
                </div >
            </div >
        </>
    )
}

export default User