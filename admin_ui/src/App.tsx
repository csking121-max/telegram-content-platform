import { Routes, Route, Navigate } from "react-router-dom";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import Users from "./pages/Users";
import Bots from "./pages/Bots";
import ContentPacks from "./pages/ContentPacks";
import Tokens from "./pages/Tokens";
import Credits from "./pages/Credits";
import Memberships from "./pages/Memberships";
import Referrals from "./pages/Referrals";
import Analytics from "./pages/Analytics";
import MembershipPlans from "./pages/MembershipPlans";
import UpiSettings from "./pages/UpiSettings";
import PaymentManagement from "./pages/PaymentManagement";
import Settings from "./pages/Settings";
import TestPanel from "./pages/TestPanel";
import Logs from "./pages/Logs";
import CreditPackages from "./pages/CreditPackages";
import Streaks from "./pages/Streaks";
import DeadLetterQueue from "./pages/DeadLetterQueue";
import WelcomeMessageBuilder from "./pages/WelcomeMessageBuilder";
import ContentFactory from "./pages/ContentFactory";
import ContentManager from "./pages/ContentManager";
import Tutorials from "./pages/Tutorials";
import Backups from "./pages/Backups";
import Cooldowns from "./pages/Cooldowns";

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<Login />} />

      {/* Protected admin routes inside Layout */}
      <Route element={<ProtectedRoute />}>
        <Route element={<Layout />}>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/users" element={<Users />} />
          <Route path="/bots" element={<Bots />} />
          <Route path="/content-packs" element={<ContentPacks />} />
          <Route path="/tokens" element={<Tokens />} />
          <Route path="/credits" element={<Credits />} />
          <Route path="/memberships" element={<Memberships />} />
          <Route path="/referrals" element={<Referrals />} />
          <Route path="/analytics" element={<Analytics />} />
          <Route path="/membership-plans" element={<MembershipPlans />} />
          <Route path="/upi-settings" element={<UpiSettings />} />
          <Route path="/payments" element={<PaymentManagement />} />
          <Route path="/cooldowns" element={<Cooldowns />} />
          <Route path="/settings" element={<Settings />} />
          <Route path="/test" element={<TestPanel />} />
          <Route path="/logs" element={<Logs />} />
          <Route path="/credit-packages" element={<CreditPackages />} />
          <Route path="/streaks" element={<Streaks />} />
          <Route path="/dlq" element={<DeadLetterQueue />} />
          <Route path="/welcome-builder" element={<WelcomeMessageBuilder />} />
          <Route path="/content-factory" element={<ContentFactory />} />
          <Route path="/content-manager" element={<ContentManager />} />
          <Route path="/tutorials" element={<Tutorials />} />
          <Route path="/backups" element={<Backups />} />
        </Route>
      </Route>
    </Routes>
  );
}
