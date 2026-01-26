import React, { useEffect, useState, useRef, useLayoutEffect, useContext } from 'react'
import styles from './Leaderboard.module.css'
import { Table, Pagination, Button, Modal, Checkbox, message, Row, Col, InputNumber, Divider, theme } from 'antd'; // Added Divider
import { useNavigate } from 'react-router';
import { apiUrl } from '../../api';
import { createStyles } from 'antd-style';
import Carousel from '../../components/Carousel';
import { SearchContext } from '../../context/SearchContext';
import { MdClear, MdFileDownload } from "react-icons/md"; // Added MdFileDownload
import { useDebounce } from '../../hooks/debounce';

import type { TableProps, TablePaginationConfig, GetProp } from 'antd';
import type { LeaderboardUser, Location, LeaderboardStatsData } from '../../types/LeaderboardUserModel';
import type { ColumnsType } from 'antd/es/table';
import type { FilterValue, SortOrder } from 'antd/es/table/interface';


type CheckboxValueType = GetProp<typeof Checkbox.Group, 'value'>[number];

// Map display names to API keys
const EXPORT_OPTIONS = [
    { label: 'Username', value: 'username' },
    { label: 'Name', value: 'name' },
    { label: 'Type', value: 'type' },
    { label: 'Gender', value: 'gender' },
    { label: 'Location', value: 'location' },
    { label: 'Followers', value: 'followers' },
    { label: 'Following', value: 'following' },
    { label: 'Public Repos', value: 'public_repos' },
    { label: 'Total Sponsors', value: 'total_sponsors' },
    { label: 'Total Sponsoring', value: 'total_sponsoring' },
    { label: 'Est. Earnings', value: 'estimated_earnings' },
    { label: 'Email', value: 'email' },
    { label: 'Twitter', value: 'twitter_username' },
    { label: 'Website', value: 'profile_url' },
];

const useStyle = createStyles(({ css, prefixCls }) => {
    return {
        customTable: css`
      .${prefixCls}-table {
        .${prefixCls}-table-container {
          .${prefixCls}-table-body,
          .${prefixCls}-table-content {
            scrollbar-width: thin;
            scrollbar-color: #474747 transparent;
            scrollbar-gutter: stable;
          }
        }
        /* Add this rule to prevent header text from wrapping */
        .${prefixCls}-table-thead > tr > th {
          white-space: nowrap;
          user-select: none;
        }
        .${prefixCls}-ant-table-column-title {
        }
      }
    `,
    };
});

const Leaderboard: React.FC = () => {

    const { token } = theme.useToken();

    // Navigation handle for user pages
    const navigate = useNavigate();

    // Table consts (styles, dynamic height for scrolling, loading state)
    const tablestyles = useStyle();
    const [scrollY, setScrollY] = useState<number>();
    const ref1 = useRef<HTMLDivElement | null>(null)
    const [loading, setLoading] = useState(false);

    const [users, setUsers] = useState<LeaderboardUser[]>([]);
    const [locationFilters, setLocationFilters] = useState<Location[]>([])
    const [leaderboardData, setLeaderboardData] = useState<LeaderboardStatsData | null>(null);

    const searchContext = useContext(SearchContext);
    if (!searchContext) {
        throw new Error('Leaderboard must be used within a SearchProvider');
    }
    const { searchTerm, setSearchTerm } = searchContext;
    const debouncedSearchTerm = useDebounce(searchTerm, 600); // Create debounced value

    // Table data consts
    const [pagination, setPagination] = useState<TablePaginationConfig>({
        current: 1,
        pageSize: 10,
        total: 0,
    });
    const [filters, setFilters] = useState<Record<string, FilterValue | null>>({});
    const [sorters, setSorters] = useState<Record<string, SortOrder | null>>({});

    // -- EXPORT STATE --
    const [isExportModalOpen, setIsExportModalOpen] = useState(false);
    const [exportLoading, setExportLoading] = useState(false);
    const [selectedExportCols, setSelectedExportCols] = useState<CheckboxValueType[]>(['username', 'name', 'type', 'total_sponsors']);
    const [exportStartRow, setExportStartRow] = useState<number>(1);
    const [exportLimit, setExportLimit] = useState<number>(1000);
    // ------------------

    const handleClearFilters = () => {
        setFilters({});
        setSorters({}); // Reset to unfiltered state (backend will handle default order)
        setSearchTerm('');
        setPagination(prev => ({ ...prev, current: 1 }));
    };

    // New function to handle data export
    const handleExport = async () => {
        if (selectedExportCols.length === 0) {
            message.warning("Please select at least one column to export.");
            return;
        }

        setExportLoading(true);

        // 1. Construct query params for the dedicated export endpoint
        const queryParams = new URLSearchParams({
            start_row: exportStartRow.toString(),
            count: exportLimit.toString(),
        });

        if (searchTerm) {
            queryParams.append("search", searchTerm);
        }

        Object.entries(filters).forEach(([key, value]) => {
            if (value && Array.isArray(value) && value.length > 0) {
                (value as string[]).forEach(v => queryParams.append(key, v));
            }
        });

        Object.entries(sorters).forEach(([field, order]) => {
            if (order) {
                queryParams.append("sortField", field);
                queryParams.append("sortOrder", order);
            }
        });

        try {
            // 2. Fetch Data from Export Endpoint
            const response = await fetch(`${apiUrl}/users/export?${queryParams.toString()}`);
            if (!response.ok) {
                // Handle rate limit specifically
                if (response.status === 429) {
                    throw new Error("Daily export limit reached.");
                }
                throw new Error('Export request failed');
            }
            const data = await response.json();
            const usersToExport = data.users || [];

            if (usersToExport.length === 0) {
                message.info("No users match the current filters to export.");
                setExportLoading(false);
                return;
            }

            // 3. Convert to CSV
            const headers = selectedExportCols.map(col => String(col)).join(",");
            const csvRows = usersToExport.map((user: any) => {
                return selectedExportCols.map(col => {
                    const val = user[col as string];
                    if (val === null || val === undefined) return '';
                    // Escape quotes and wrap in quotes to handle commas in data
                    const stringVal = String(val).replace(/"/g, '""');
                    return `"${stringVal}"`;
                }).join(",");
            });

            const csvContent = [headers, ...csvRows].join("\n");

            // 4. Trigger Download
            const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
            const url = URL.createObjectURL(blob);
            const link = document.createElement("a");
            link.href = url;
            link.setAttribute("download", `github_sponsors_export_${new Date().toISOString().slice(0, 10)}.csv`);
            document.body.appendChild(link);
            link.click();
            document.body.removeChild(link);

            message.success(`Allocated ${usersToExport.length} rows for export.`);
            setIsExportModalOpen(false);

        } catch (error) {
            console.error("Export error:", error);
            message.error("Failed to export data.");
        } finally {
            setExportLoading(false);
        }
    };

    const fetchUsers = async (
        currentPagination: TablePaginationConfig,
        currentFilters: Record<string, FilterValue | null>,
        currentSorters: Record<string, SortOrder | null>
    ) => {
        setLoading(true);

        const queryParams = new URLSearchParams({
            page: (currentPagination.current || 1).toString(),
            per_page: (currentPagination.pageSize || 10).toString(),
        });

        // Check if search term has been provided
        if (searchTerm) {
            queryParams.append("search", searchTerm);
        }

        Object.entries(currentFilters).forEach(([key, value]) => {
            // Safely handle null/undefined filter values from Ant Design
            if (value && Array.isArray(value) && value.length > 0) {
                (value as string[]).forEach(v => queryParams.append(key, v));
            }
        });

        Object.entries(currentSorters).forEach(([field, order]) => {
            if (order) { // Only add if an order is set (not null)
                queryParams.append("sortField", field);
                queryParams.append("sortOrder", order);
            }
        });

        try {
            const response = await fetch(`${apiUrl}/users?${queryParams.toString()}`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

            const data = await response.json(); // Expects { users: [], total: number }

            const mappedUsers = data.users.map((user: LeaderboardUser) =>
                Object.fromEntries(
                    Object.entries(user).map(([key, value]) => [
                        key,
                        value === null ? "None" : value === "Organization" ? "Org" : value,
                    ])
                ) as LeaderboardUser
            );

            setUsers(mappedUsers);
            setPagination(prev => ({
                ...prev,
                total: data.total, // Set total from the API response
            }));

        } catch (error) {
            console.error("Error fetching users:", error);
        } finally {
            setLoading(false);
        }
    };

    async function getLocations() {
        try {
            const response = await fetch(`${apiUrl}/users/location`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);

            const data = await response.json();
            const locationData = data.map((location: string) => ({
                text: location,
                value: location,
            }));
            setLocationFilters(locationData);

        } catch (error) {
        }
    }

    // Get leaderboard statistics every 15 seconds for live updating carousel
    const getLeaderboardStats = async (_signal?: AbortSignal) => {
        try {
            const response = await fetch(`${apiUrl}/stats/brief`);
            if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
            const data: LeaderboardStatsData = await response.json();
            setLeaderboardData(data);
        } catch (error) {
            console.error("Error fetching leaderboard stats:", error);
        }
    };

    const columns: ColumnsType<LeaderboardUser> = [
        {
            title: "Username",
            dataIndex: "username",
            key: "username",
            width: 115,
            sortDirections: ["descend", "ascend"],
            sorter: true,
            sortOrder: sorters.username || null,
            render: (_: any, record: LeaderboardUser) => (
                <>
                    <span className='flex items-center gap-1'>
                        <img src={record.avatar_url} alt={record.username} style={{ width: 24, borderRadius: '25%', marginRight: 8 }} />
                        {record.username && record.username.length > 15 ? `${record.username.slice(0, 13)}...` : record.username}
                    </span>
                </>
            ),
            onCell: () => ({
                style: {
                    whiteSpace: 'normal',
                    textOverflow: "hidden",
                },
            }),
        },
        {
            title: "Name",
            dataIndex: "name",
            key: "name",
            width: 110,
            sorter: true,
            sortOrder: sorters.name || null,
            sortDirections: ["descend", "ascend"],
            render: (text: string) =>
                text && text.length > 13 ? `${text.slice(0, 11)}...` : text,
        },
        {
            title: "Type",
            dataIndex: "type",
            key: "type",
            width: 70,
            filters: [
                {
                    text: 'User',
                    value: 'User',
                },
                {
                    text: 'Organization',
                    value: 'Organization',
                },
            ],
            filteredValue: filters.type || null,
        },
        {
            title: "Gender",
            dataIndex: "gender",
            key: "gender",
            width: 85,
            filters: [
                {
                    text: 'Male',
                    value: 'Male',
                },
                {
                    text: 'Female',
                    value: 'Female',
                },
                {
                    text: 'Other',
                    value: 'Other',
                },
                {
                    text: 'Unknown',
                    value: 'Unknown',
                },
            ],
            filteredValue: filters.gender || null,
        },
        {
            title: "Location",
            dataIndex: "location",
            key: "location",
            width: 110,
            filters: locationFilters,
            filterSearch: true,
            filteredValue: filters.location || null,
        },
        {
            title: "Followers",
            dataIndex: "followers",
            key: "followers",
            width: 100,
            sorter: true,
            sortOrder: sorters.followers || null,
            sortDirections: ["descend", "ascend"],

        },
        {
            title: "Following",
            dataIndex: "following",
            key: "following",
            width: 100,
            sorter: true,
            sortOrder: sorters.following || null,
            sortDirections: ["descend", "ascend"]
        },
        {
            title: "Repos",
            dataIndex: "public_repos",
            key: "repos",
            width: 75,
            sorter: true,
            sortOrder: sorters.public_repos || null,
            sortDirections: ["descend", "ascend"]
        },
        {
            title: "Sponsors",
            dataIndex: "total_sponsors",
            key: "sponsors",
            width: 100,
            sorter: true,
            sortOrder: sorters.total_sponsors || null,
            sortDirections: ["descend", "ascend"]
        },
        {
            title: "Sponsoring",
            dataIndex: "total_sponsoring",
            key: "sponsoring",
            width: 110,
            sorter: true,
            sortOrder: sorters.total_sponsoring || null,
            sortDirections: ["descend", "ascend"]
        },
        {
            title: "Min. Earnings (Estimate)",
            dataIndex: "estimated_earnings",
            className: styles.nowrapHeader,
            key: "earnings",
            width: 200,
            render: (_: any, record: LeaderboardUser) => (
                <span style={{ fontWeight: 600 }}>
                    ${Math.round(record.estimated_earnings)}<span style={{ fontWeight: 400, fontSize: 12 }}>+ USD/mo</span>
                </span>
            ),
            sorter: true,
            sortOrder: sorters.estimated_earnings || null,
            sortDirections: ["descend", "ascend"]
        },
    ];

    const handleTableChange: TableProps<LeaderboardUser>['onChange'] = (
        _pagination,
        newFilters,
        newSorters
    ) => {
        const sortersArray = Array.isArray(newSorters) ? newSorters : [newSorters];
        const formattedSorters = sortersArray.reduce((acc, s) => {
            if (s.field && s.order) {
                const key = Array.isArray(s.field) ? s.field.join('.') : String(s.field);
                acc[key] = s.order;
            }
            return acc;
        }, {} as Record<string, SortOrder>);

        setSorters(formattedSorters);
        setFilters(newFilters);
        // Reset to page 1 when filters or sorters change
        setPagination(prev => ({
            ...prev,
            current: 1,
        }));
    };

    const getDynamicHeight = () => {
        let height = ref1.current?.clientHeight;
        console.log(height);
        if (height) {
            setScrollY(height - 47);
        }
    }

    useLayoutEffect(() => {
        getDynamicHeight();
        window.addEventListener('resize', getDynamicHeight);
        return () => {
            window.removeEventListener('resize', getDynamicHeight);
        }
    }, []);


    useEffect(() => {
        // Poll once immediately, then every 15s. Clean up to avoid duplicate timers in StrictMode.
        const controller = new AbortController();
        let timer: number | undefined;
        let inFlight = false;
        getLocations();

        const tick = async () => {
            if (inFlight) return; // prevent overlap
            inFlight = true;
            await getLeaderboardStats(controller.signal);
            inFlight = false;
            timer = window.setTimeout(tick, 15000);
        };

        tick(); // immediate first fetch

        return () => {
            controller.abort();                     // cancel in-flight request
            if (timer) window.clearTimeout(timer);  // clear scheduled poll
        };
    }, []);


    useEffect(() => {
        // When a new search is performed, filters or sorters are changed, reset to page 1
        if (pagination.current !== 1) {
            setPagination(prev => ({ ...prev, current: 1 }));
        } else {
            // Otherwise, fetch users with the current state
            fetchUsers(pagination, filters, sorters);
        }
    }, [debouncedSearchTerm]); // Use debouncedSearchTerm here

    useEffect(() => {
        fetchUsers(pagination, filters, sorters);

    }, [pagination.current, pagination.pageSize, filters, sorters]);


    return (
        <>
            <section className='grid grid-cols-1 grid-rows-[_1.2fr,5fr] h-full pl-2 gap-3'>
                <div className='flex flex-col flex-shrink-0 gap-2 w-full h-full'>
                    <h1 className='text-[24px] font-semibold pb-1'>Leaderboard Statistics</h1>
                    <div className='flex-1 flex'>
                        {leaderboardData && <Carousel {...leaderboardData} />}
                    </div>
                </div>
                <div className='row-span-2 flex flex-col'>
                    <div ref={ref1} className='flex-grow overflow-y-hidden custom-scrollbar'>
                        <Table
                            className={tablestyles.styles.customTable}
                            columns={columns}
                            dataSource={users}
                            loading={loading}
                            showSorterTooltip={{ target: 'sorter-icon' }}
                            tableLayout='fixed'
                            onRow={(record) => ({
                                onClick: () => navigate(`/user/${record.id}`, { state: record }),
                                style: { cursor: "pointer" }
                            })}
                            onChange={handleTableChange}
                            scroll={{ x: 'max-content', y: scrollY }}
                            size="middle"
                            pagination={false}

                        />
                    </div>
                    <div className='flex-shrink-0 flex justify-end pt-2'>
                        <div className='flex w-full justify-between items-center'>
                            {/* Group Filters and Export button */}
                            <div className='flex gap-2'>
                                <Button icon={<MdClear />} iconPosition='end' onClick={handleClearFilters}>
                                    Clear Filters
                                </Button>
                                <Button
                                    icon={<MdFileDownload />}
                                    onClick={() => setIsExportModalOpen(true)}
                                >
                                    Export CSV
                                </Button>
                            </div>

                            <Pagination
                                simple
                                current={pagination.current}
                                pageSize={pagination.pageSize}
                                total={pagination.total} // Use total from state
                                showSizeChanger
                                pageSizeOptions={['10', '20', '50', '100']}
                                onChange={(page, size) => {
                                    setPagination(prev => ({
                                        ...prev,
                                        current: page,
                                        pageSize: size,
                                    }));
                                }}
                            />
                        </div>
                    </div>
                </div>
            </section >

            {/* Export Modal */}
            <Modal
                title="Export Data"
                open={isExportModalOpen}
                onOk={handleExport}
                onCancel={() => setIsExportModalOpen(false)}
                okText={exportLoading ? "Exporting..." : "Download CSV"}
                confirmLoading={exportLoading}
                centered
                width={550} // Increased width slightly
            >
                <p className="text-gray-500 mb-6">
                    Export user data to CSV based on your active filters and search terms.
                </p>

                <div className='flex flex-col gap-1'>
                    <div>
                        <div className="flex justify-between items-center mb-2">
                            <p className="font-semibold">1. Select Columns</p>
                            <Checkbox
                                indeterminate={selectedExportCols.length > 0 && selectedExportCols.length < EXPORT_OPTIONS.length}
                                onChange={(e) => setSelectedExportCols(e.target.checked ? EXPORT_OPTIONS.map(opt => opt.value) : [])}
                                checked={selectedExportCols.length === EXPORT_OPTIONS.length}
                            >
                                Select All
                            </Checkbox>
                        </div>
                        <div className={`p-4 rounded-lg border`} style={{ borderColor: token.colorBorder }}>
                            <Checkbox.Group
                                style={{ width: '100%' }}
                                value={selectedExportCols}
                                onChange={(checkedValues) => setSelectedExportCols(checkedValues as CheckboxValueType[])}
                            >
                                <Row gutter={[12, 12]}>
                                    {EXPORT_OPTIONS.map((opt) => (
                                        <Col span={12} key={opt.value}>
                                            <Checkbox value={opt.value}>{opt.label}</Checkbox>
                                        </Col>
                                    ))}
                                </Row>
                            </Checkbox.Group>
                        </div>
                    </div>

                    <Divider style={{ margin: '24px 0' }} />

                    <div>
                        <p className="mb-4 font-semibold">2. Range Configuration</p>
                        <Row gutter={16}>
                            <Col span={12}>
                                <div className="flex flex-col">
                                    <span className="text-sm font-medium mb-1">Starting Row</span>
                                    <InputNumber
                                        min={1}
                                        value={exportStartRow}
                                        onChange={(val) => setExportStartRow(val || 1)}
                                        style={{ width: '100%' }}
                                    />
                                    <span className="text-xs text-gray-400 mt-1">
                                        Row number to start export from. If 100, exports 100 and up.
                                    </span>
                                </div>
                            </Col>
                            <Col span={12}>
                                <div className="flex flex-col">
                                    <span className="text-sm font-medium mb-1">Quantity to Export</span>
                                    <InputNumber
                                        min={1}
                                        max={2000}
                                        value={exportLimit}
                                        onChange={(val) => setExportLimit(val || 1000)}
                                        style={{ width: '100%' }}
                                        addonAfter="rows"
                                    />
                                    <span className="text-xs text-gray-400 mt-1">
                                        Maximum 2000 rows per export
                                    </span>
                                </div>
                            </Col>
                        </Row>
                    </div>
                </div>
            </Modal >
        </>
    )
}
export default Leaderboard;