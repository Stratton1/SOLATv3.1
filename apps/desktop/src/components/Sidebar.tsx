import { Link, useLocation } from "react-router-dom";

export function Sidebar() {
  const location = useLocation();
  const isActive = (path: string) => location.pathname === path;

  return (
    <aside className="app-sidebar">
      <div className="sidebar-header">
        <img src="/image_logo.png" alt="SOLAT" className="sidebar-logo" />
      </div>

      <nav className="sidebar-nav">
        <div className="nav-group">
          <div className="nav-group-label">Analysis</div>
          <Link to="/" className={`nav-item ${isActive("/") ? "active" : ""}`}>
            <span className="nav-icon">⊞</span> Dashboard
          </Link>
          <Link to="/terminal" className={`nav-item ${isActive("/terminal") ? "active" : ""}`}>
             <span className="nav-icon">📈</span> Charts
          </Link>
        </div>

        <div className="nav-group">
          <div className="nav-group-label">Strategy</div>
          <Link to="/backtests" className={`nav-item ${isActive("/backtests") ? "active" : ""}`}>
             <span className="nav-icon">▶</span> Backtests
          </Link>
          <Link to="/optimise" className={`nav-item ${isActive("/optimise") ? "active" : ""}`}>
             <span className="nav-icon">⚙</span> Optimise
          </Link>
        </div>

        <div className="nav-group">
          <div className="nav-group-label">Execution</div>
          <Link to="/blotter" className={`nav-item ${isActive("/blotter") ? "active" : ""}`}>
             <span className="nav-icon">☰</span> Blotter
          </Link>
        </div>

        <div className="nav-group">
          <div className="nav-group-label">System</div>
          <Link to="/system" className={`nav-item ${isActive("/system") ? "active" : ""}`}>
             <span className="nav-icon">⚡</span> System
          </Link>
        </div>
      </nav>
    </aside>
  );
}
