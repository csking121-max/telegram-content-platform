// Pack items are managed via the Content Packs detail view.
// This page is kept as a redirect for backward compatibility.
import { Navigate } from "react-router-dom";
export default function PackItems() {
  return <Navigate to="/content-packs" replace />;
}