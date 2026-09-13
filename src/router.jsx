import { createBrowserRouter, Navigate } from "react-router-dom";
import { lazy, Suspense } from "react";
import AppShell from "./components/layout/AppShell.jsx";
import { LoadingState } from "./components/common/States.jsx";
import Login from "./pages/Login.jsx";

const Dashboard       = lazy(() => import("./pages/Dashboard.jsx"));
const Cameras         = lazy(() => import("./pages/Cameras.jsx"));
const CameraDetail    = lazy(() => import("./pages/CameraDetail.jsx"));
const AddCamera       = lazy(() => import("./pages/AddCamera.jsx"));
const ZoneDetail      = lazy(() => import("./pages/ZoneDetail.jsx"));
const FRS             = lazy(() => import("./pages/FRS.jsx"));
const FRSHistory      = lazy(() => import("./pages/FRSHistory.jsx"));
const FRSCameraDetail = lazy(() => import("./pages/FRSCameraDetail.jsx"));
const Alerts          = lazy(() => import("./pages/Alerts.jsx"));
const Analytics       = lazy(() => import("./pages/Analytics.jsx"));
const Reports         = lazy(() => import("./pages/Reports.jsx"));
const Settings        = lazy(() => import("./pages/Settings.jsx"));
const Events          = lazy(() => import("./pages/Events.jsx"));
const EventAccess     = lazy(() => import("./pages/EventAccess.jsx"));
const Sites           = lazy(() => import("./pages/Sites.jsx"));
const CrowdManagement = lazy(() => import("./pages/CrowdManagement.jsx"));

const PageWrapper = ({ children }) => (
  <Suspense fallback={<div className="cc-page"><LoadingState /></div>}>
    {children}
  </Suspense>
);

export const router = createBrowserRouter([
  { path: "/login", element: <Login /> },
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true,                   element: <Navigate to="/dashboard" replace /> },
      { path: "dashboard",             element: <PageWrapper><Dashboard /></PageWrapper> },
      { path: "cameras",               element: <PageWrapper><Cameras /></PageWrapper> },
      { path: "cameras/add",           element: <PageWrapper><AddCamera /></PageWrapper> },
      { path: "cameras/:id",           element: <PageWrapper><CameraDetail /></PageWrapper> },
      { path: "zones/:id",             element: <PageWrapper><ZoneDetail /></PageWrapper> },
      { path: "frs",                   element: <PageWrapper><FRS /></PageWrapper> },
      { path: "frs/history",           element: <PageWrapper><FRSHistory /></PageWrapper> },
      { path: "frs/cameras/:cameraId", element: <PageWrapper><FRSCameraDetail /></PageWrapper> },
      { path: "alerts",                element: <PageWrapper><Alerts /></PageWrapper> },
      { path: "analytics",             element: <PageWrapper><Analytics /></PageWrapper> },
      { path: "reports",               element: <PageWrapper><Reports /></PageWrapper> },
      { path: "events",                element: <PageWrapper><Events /></PageWrapper> },
      { path: "events/:eventId/access",element: <PageWrapper><EventAccess /></PageWrapper> },
      { path: "sites",                 element: <PageWrapper><Sites /></PageWrapper> },
      { path: "crowd-management",      element: <PageWrapper><CrowdManagement /></PageWrapper> },
      { path: "settings",              element: <PageWrapper><Settings /></PageWrapper> },
    ],
  },
  { path: "*", element: <Navigate to="/dashboard" replace /> },
]);

export default router;