import { createBrowserRouter, Navigate } from "react-router-dom";
import { lazy, Suspense } from "react";
import AppShell from "./components/layout/AppShell.jsx";
import { LoadingState } from "./components/common/States.jsx";
import Login from "./pages/Login.jsx";

// Lazy-loaded pages for performance
const Dashboard = lazy(() => import("./pages/Dashboard.jsx"));
// LiveMap removed — map module disabled
const Cameras = lazy(() => import("./pages/Cameras.jsx"));
const CameraDetail = lazy(() => import("./pages/CameraDetail.jsx"));
const CrowdManagement = lazy(() => import("./pages/CrowdManagement.jsx"));
const Crowd = lazy(() => import("./pages/Crowd.jsx"));
const Queue = lazy(() => import("./pages/Queue.jsx"));
const Zones = lazy(() => import("./pages/Zones.jsx"));
const ZoneDetail = lazy(() => import("./pages/ZoneDetail.jsx"));
const FRS = lazy(() => import("./pages/FRS.jsx"));
const FRSHistory = lazy(() => import("./pages/FRSHistory.jsx"));
const FRSCameraDetail = lazy(() => import("./pages/FRSCameraDetail.jsx"));
const MissingPersons = lazy(() => import("./pages/MissingPersons.jsx"));
const Alerts = lazy(() => import("./pages/Alerts.jsx"));
const Incidents = lazy(() => import("./pages/Incidents.jsx"));
const Predictions = lazy(() => import("./pages/Predictions.jsx"));
const Analytics = lazy(() => import("./pages/Analytics.jsx"));
// const Operations = lazy(() => import("./pages/Operations.jsx")); // commented out by design
const Reports = lazy(() => import("./pages/Reports.jsx"));
const SystemHealth = lazy(() => import("./pages/SystemHealth.jsx"));
const Settings = lazy(() => import("./pages/Settings.jsx"));
const AIDeployment = lazy(() => import("./pages/AIDeployment.jsx"));
const AddCamera = lazy(() => import("./pages/AddCamera.jsx"));

const PageWrapper = ({ children }) => (
  <Suspense fallback={<div className="cc-page"><LoadingState /></div>}>
    {children}
  </Suspense>
);

export const router = createBrowserRouter([
  {
    path: "/login",
    element: <Login />,
  },
  {
    path: "/",
    element: <AppShell />,
    children: [
      { index: true, element: <Navigate to="/dashboard" replace /> },
      { path: "dashboard", element: <PageWrapper><Dashboard /></PageWrapper> },
      { path: "cameras", element: <PageWrapper><Cameras /></PageWrapper> },
      { path: "cameras/add", element: <PageWrapper><AddCamera /></PageWrapper> },
      { path: "cameras/:id", element: <PageWrapper><CameraDetail /></PageWrapper> },
      { path: "crowd-management", element: <PageWrapper><CrowdManagement /></PageWrapper> },
      { path: "crowd", element: <Navigate to="/crowd-management" replace /> },
      { path: "queue", element: <Navigate to="/crowd-management" replace /> },
      { path: "zones", element: <Navigate to="/crowd-management" replace /> },
      { path: "zones/:id", element: <PageWrapper><ZoneDetail /></PageWrapper> },
      { path: "frs", element: <PageWrapper><FRS /></PageWrapper> },
      { path: "frs/history", element: <PageWrapper><FRSHistory /></PageWrapper> },
      { path: "frs/cameras/:cameraId", element: <PageWrapper><FRSCameraDetail /></PageWrapper> },
      { path: "missing-persons", element: <PageWrapper><MissingPersons /></PageWrapper> },
      { path: "alerts", element: <PageWrapper><Alerts /></PageWrapper> },
      { path: "incidents", element: <PageWrapper><Incidents /></PageWrapper> },
      { path: "predictions", element: <PageWrapper><Predictions /></PageWrapper> },
      { path: "analytics", element: <PageWrapper><Analytics /></PageWrapper> },
      // { path: "operations", element: <PageWrapper><Operations /></PageWrapper> },
      { path: "reports", element: <PageWrapper><Reports /></PageWrapper> },
      { path: "system-health", element: <PageWrapper><SystemHealth /></PageWrapper> },
      { path: "ai-deployment", element: <PageWrapper><AIDeployment /></PageWrapper> },
      { path: "settings", element: <PageWrapper><Settings /></PageWrapper> },
    ],
  },
  { path: "*", element: <Navigate to="/dashboard" replace /> },
]);

export default router;
