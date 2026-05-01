import React, { useContext, useState } from 'react';
import { useNavigate, useLocation, Outlet, Link } from 'react-router';
import { Layout, Menu, theme, Drawer, Button } from 'antd';
import { MenuOutlined } from '@ant-design/icons';
import Search from '../components/SearchBar';
import { SearchProvider, SearchContext } from '../context/SearchContext';
import { useTheme } from '../context/ThemeContext';
import DarkmodeButton from '../components/DarkmodeButton';

import { AiFillGithub } from "react-icons/ai";
import { MdSpaceDashboard } from "react-icons/md";
import { MdDarkMode, MdLightMode } from 'react-icons/md';
import { MdAccountTree } from 'react-icons/md';
import { IoMdStats } from "react-icons/io";


const { Header, Content, Sider } = Layout;

const DashboardContent: React.FC = () => {

    const navigate = useNavigate();
    const location = useLocation();
    const searchContext = useContext(SearchContext);
    const [mobileDrawerOpen, setMobileDrawerOpen] = useState(false);
    const { theme: appThemeMode, toggleTheme } = useTheme();

    if (!searchContext) {
        throw new Error('useSearch must be used within a SearchProvider');
    }
    const { setSearchTerm } = searchContext;

    const routes: { [key: string]: string } = {
        '1': '/',
        '2': '/statistics',
        '3': '/graph',
        // '3': '/request-user',
        // '4': '/docs'
    };

    const menuKeyMap = Object.fromEntries(
        Object.entries(routes).map(([key, path]) => [path, key])
    );

    const handleMenuClick = ({ key }: { key: string }) => {
        if (routes[key]) {
            navigate(routes[key]);
        }
    };

    const {
        token: { colorBgContainer, colorBgLayout, borderRadiusLG, colorBorder, linkHover, },
    } = theme.useToken();


    return (
        <Layout className='h-screen' style={{ background: colorBgLayout }}>
            <Header
                style={{ background: colorBgContainer, borderBottom: `1px solid ${colorBorder}` }}
                className='flex items-center justify-between gap-3 px-5'
            >
                {/* Desktop: logo + title on the left */}
                <div className='hidden md:flex items-center gap-5 min-w-0'>
                    <Link
                        to={"/"}
                        style={{ color: 'inherit' }}
                        onMouseEnter={(e) => (e.currentTarget.style.color = linkHover)}
                        onMouseLeave={(e) => (e.currentTarget.style.color = 'inherit')}
                        className="flex items-center gap-1.5 px-1 shrink-0"
                    >
                        <AiFillGithub className='text-[22px]' />
                        <h1 className='font-semibold text-[18px] whitespace-nowrap'>Github Sponsorships</h1>
                    </Link>

                    {location.pathname === '/' && (
                        <div className='flex items-center min-w-0 flex-1'>
                            <Search onSubmit={e => { setSearchTerm(e) }} />
                        </div>
                    )}
                </div>

                {/* Mobile */}
                {location.pathname === '/' ? (
                    /* Home: centered logo + search + hamburger (hamburger sits to the right of search) */
                    <div className='flex md:hidden items-center justify-center gap-2 flex-1 min-w-0'>
                        <Link
                            to={"/"}
                            style={{ color: 'inherit' }}
                            onMouseEnter={(e) => (e.currentTarget.style.color = linkHover)}
                            onMouseLeave={(e) => (e.currentTarget.style.color = 'inherit')}
                            className="flex items-center gap-1.5 px-1 shrink-0"
                            aria-label='Home'
                        >
                            <AiFillGithub className='text-[22px]' />
                        </Link>

                        <div className='flex items-center gap-2 flex-1 min-w-0 justify-center'>
                            <Search onSubmit={e => { setSearchTerm(e) }} />
                            <Button
                                type="text"
                                icon={<MenuOutlined />}
                                onClick={() => setMobileDrawerOpen(true)}
                                aria-label='Open navigation menu'
                                className='shrink-0'
                            />
                        </div>
                    </div>
                ) : (
                    /* Other pages (e.g. Statistics): logo+text on left, hamburger on right */
                    <div className='flex md:hidden items-center justify-between gap-3 flex-1 min-w-0'>
                        <Link
                            to={"/"}
                            style={{ color: 'inherit' }}
                            onMouseEnter={(e) => (e.currentTarget.style.color = linkHover)}
                            onMouseLeave={(e) => (e.currentTarget.style.color = 'inherit')}
                            className="flex items-center gap-1.5 px-1 min-w-0"
                            aria-label='Home'
                        >
                            <AiFillGithub className='text-[22px] shrink-0' />
                            <span className='font-semibold text-[18px] whitespace-nowrap truncate'>Github Sponsorships</span>
                        </Link>

                        <Button
                            type="text"
                            icon={<MenuOutlined />}
                            onClick={() => setMobileDrawerOpen(true)}
                            aria-label='Open navigation menu'
                            className='shrink-0'
                        />
                    </div>
                )}

                {/* Desktop actions */}
                <div className='hidden md:flex items-center gap-3 pr-[20px] shrink-0'>
                    <DarkmodeButton />
                </div>
            </Header>
            <Layout
                style={{ background: colorBgContainer, borderRadius: borderRadiusLG }} className='h-full px-[20px] py-[20px]'
            >
                {/* Desktop Sider - hidden on screens smaller than md */}
                <Sider
                    style={{ background: colorBgContainer }}
                    width={200}
                    collapsed
                    collapsedWidth={64}
                    className='hidden md:block'
                >
                    <Menu
                        mode='inline'
                        defaultSelectedKeys={['1']}
                        defaultOpenKeys={['sub1']}
                        style={{ height: '100%', paddingRight: 15 }}
                        selectedKeys={[menuKeyMap[location.pathname]]}
                        onClick={handleMenuClick}
                        items={[
                            {
                                key: '1',
                                label: 'Overview',
                                icon: <MdSpaceDashboard />
                            },
                            {
                                key: '2',
                                label: 'Analytics',
                                icon: <IoMdStats />
                            },
                            {
                                key: '3',
                                label: 'Graph',
                                icon: <MdAccountTree />
                            },
                        ]}
                    />
                </Sider>

                {/* Mobile Navigation Drawer */}
                <Drawer
                    title={
                        <div className='flex items-center gap-2'>
                            <AiFillGithub className='text-[20px]' />
                            <span>Menu</span>
                        </div>
                    }
                    placement="left"
                    onClose={() => setMobileDrawerOpen(false)}
                    open={mobileDrawerOpen}
                    bodyStyle={{ padding: 0 }}
                >
                    <Menu
                        mode='inline'
                        defaultSelectedKeys={['1']}
                        style={{ borderRight: 'none' }}
                        selectedKeys={[menuKeyMap[location.pathname]]}
                        onClick={(e) => {
                            handleMenuClick(e);
                            setMobileDrawerOpen(false);
                        }}
                        items={[
                            {
                                key: '1',
                                label: 'Overview',
                                icon: <MdSpaceDashboard />
                            },
                            {
                                key: '2',
                                label: 'Analytics',
                                icon: <IoMdStats />
                            },
                            {
                                key: '3',
                                label: 'Graph',
                                icon: <MdAccountTree />
                            },
                        ]}
                    />

                    <div className='px-2 py-2'>
                        <Button
                            type='text'
                            block
                            onClick={toggleTheme}
                            className='h-auto py-2 flex items-center justify-between'
                        >
                            <span className='font-medium'>Dark mode</span>
                            {appThemeMode === 'dark' ? (
                                <MdDarkMode className='text-[18px]' />
                            ) : (
                                <MdLightMode className='text-[18px]' />
                            )}
                        </Button>
                    </div>
                </Drawer>

                <Content style={{ padding: '0 10px', minHeight: 280, }}>
                    <Outlet />
                </Content>
            </Layout>
        </Layout >
    );
};

const Dashboard: React.FC = () => {
    return (
        <SearchProvider>
            <DashboardContent />
        </SearchProvider>
    );
};
export default Dashboard;
