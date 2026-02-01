import { Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route } from 'react-router';
import { ConfigProvider, theme as antdTheme, Spin } from 'antd';

import { ThemeProvider, useTheme } from './context/ThemeContext';
import { theme as appTheme } from './theme.ts';
import { usePageViews } from "./hooks/useAnalytics";

import type { AliasToken } from 'antd/es/theme/internal';

// Lazy load page components
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Leaderboard = lazy(() => import('./pages/leaderboard/Leaderboard'));
const Statistics = lazy(() => import('./pages/statistics/Statistics'));
const RequestUser = lazy(() => import('./pages/users/RequestUser.tsx'));
const User = lazy(() => import('./pages/users/User'));

interface CustomToken extends AliasToken {
  cardBg: string;
}

const RouteTracker = () => {
  usePageViews();
  return null;
};

// A new component to access the context provided by ThemeProvider
const ThemedApp = () => {
  const { theme } = useTheme();
  const themeColors = appTheme.extend.colors;

  return (
    <ConfigProvider
      theme={{
        algorithm: theme === 'dark' ? antdTheme.darkAlgorithm : antdTheme.defaultAlgorithm,
        token: {
          // Primary Color
          colorPrimary: theme === 'dark' ? themeColors.primary.dark : themeColors.primary.light,
          colorBgContainer: theme === 'dark' ? '#111' : '#fff',
          borderColor: theme === 'dark' ? themeColors.border.dark : themeColors.border.light,
          cardBg: theme === 'dark' ? themeColors.cardBg.dark : themeColors.cardBg.light,
          linkHover: theme === 'dark' ? themeColors.text.linkHover.dark : themeColors.text.linkHover.light,
          gridColor: theme === 'dark' ? themeColors.gridColor.dark : themeColors.gridColor.light,
          colorTextSecondary: theme === 'dark' ? themeColors.text.secondary.dark : themeColors.text.secondary.light,
        } as Partial<CustomToken>,
      }}
    >
      <BrowserRouter>
        <RouteTracker />
        <Suspense fallback={<div className="flex justify-center items-center h-screen w-full"><Spin size="large" /></div>}>
          <Routes>
            <Route path='/' element={<Dashboard />}>
              <Route path='' element={<Leaderboard />} />
              <Route path="/user/:id" element={<User />} />
              <Route path='statistics' element={<Statistics />} />
              <Route path='request-user' element={<RequestUser />} />
            </Route>
          </Routes>
        </Suspense>
      </BrowserRouter>
    </ConfigProvider>
  );
};

export default function App() {
  return (
    // Wrap the entire app in the ThemeProvider
    <ThemeProvider>
      <ThemedApp />
    </ThemeProvider>
  );
}
