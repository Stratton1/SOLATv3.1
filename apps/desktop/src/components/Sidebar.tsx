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
          <Link to="/" className={`nav-item ${isActive("/") ? "active" : ""}`}>
            <span className="nav-icon">&#9675;</span> Home
          </Link>
        </div>

        <div className="nav-group">
          <div className="nav-group-label">Analysis</div>
          <Link to="/dashboard" className={`nav-item ${isActive("/dashboard") ? "active" : ""}`}>
            <span className="nav-icon">&#8862;</span> Dashboard
          </Link>
          <Link to="/terminal" className={`nav-item ${isActive("/terminal") ? "active" : ""}`}>
             <span className="nav-icon">&#9636;</span> Charts
          </Link>
          <Link to="/playground" className={`nav-item ${isActive("/playground") ? "active" : ""}`}>
             <span className="nav-icon">&#9881;</span> Playground
          </Link>
        </div>

        <div className="nav-group">
          <div className="nav-group-label">Strategy</div>
          <Link to="/bots" className={`nav-item ${isActive("/bots") ? "active" : ""}`}>
             <span className="nav-icon">&#9733;</span> Bots
          </Link>
          <Link to="/backtests" className={`nav-item ${isActive("/backtests") ? "active" : ""}`}>
             <span className="nav-icon">&#9654;</span> Backtests
          </Link>
          <Link to="/optimise" className={`nav-item ${isActive("/optimise") ? "active" : ""}`}>
             <span className="nav-icon">&#9878;</span> Optimise
          </Link>
          <Link to="/allowlist" className={`nav-item ${isActive("/allowlist") ? "active" : ""}`}>
             <span className="nav-icon">&#9745;</span> Allowlist
          </Link>
        </div>

        <div className="nav-group">
          <div className="nav-group-label">Execution</div>
          <Link to="/blotter" className={`nav-item ${isActive("/blotter") ? "active" : ""}`}>
             <span className="nav-icon">&#9776;</span> Blotter
          </Link>
        </div>

        <div className="nav-group">
          <div className="nav-group-label">System</div>
          <Link to="/system" className={`nav-item ${isActive("/system") ? "active" : ""}`}>
             <span className="nav-icon">&#9889;</span> System
          </Link>
        </div>
      </nav>
    </aside>
  );
}
