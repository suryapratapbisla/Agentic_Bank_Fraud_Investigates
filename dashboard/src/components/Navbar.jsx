import { NavLink, useLocation } from 'react-router-dom';
import { cases } from '../data';

export default function Navbar() {
  const location = useLocation();
  const onCase = location.pathname.startsWith('/case/');
  const onGraph = location.pathname.startsWith('/graph/');

  const linkClass = ({ isActive }) =>
    `px-3 py-2 text-sm font-medium transition-colors border-b-2 ${
      isActive
        ? 'text-violet-400 border-violet-500'
        : 'text-gray-400 border-transparent hover:text-gray-200'
    }`;

  return (
    <header className="border-b border-gray-800 bg-gray-900/80 backdrop-blur sticky top-0 z-50">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 flex items-center justify-between h-14">
        <NavLink to="/" className="flex items-center gap-2">
          <span className="text-xl font-bold bg-gradient-to-r from-violet-400 to-blue-500 bg-clip-text text-transparent">
            FraudIQ
          </span>
          <span className="text-xs text-gray-500 hidden sm:inline">
            Investigation Console
          </span>
        </NavLink>
        <nav className="flex items-center gap-1">
          <NavLink to="/" end className={linkClass}>
            Dashboard
          </NavLink>
          <NavLink
            to={onCase ? location.pathname : `/case/${cases[0]?.case_id ?? 'HHG-001'}`}
            className={linkClass}
            end={false}
          >
            Cases
          </NavLink>
          <NavLink
            to={onGraph ? location.pathname : `/graph/${cases[0]?.case_id ?? 'HHG-001'}`}
            className={linkClass}
            end={false}
          >
            Graph
          </NavLink>
        </nav>
      </div>
    </header>
  );
}
