import { Navigate } from 'react-router-dom';

// Not wired to any route (App.tsx routes "/" to Dashboard instead) — kept as
// a harmless redirect rather than deleted, since file deletion needs explicit
// user action.
const Index = () => {
  return <Navigate to="/" replace />;
};

export default Index;
