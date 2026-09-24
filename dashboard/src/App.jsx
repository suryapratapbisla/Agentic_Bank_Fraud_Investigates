import { Routes, Route } from 'react-router-dom';
import Navbar from './components/Navbar';
import Dashboard from './components/Dashboard';
import CaseDetail from './components/CaseDetail';
import GraphView from './components/GraphView';

export default function App() {
  return (
    <div className="min-h-screen bg-gray-950 flex flex-col">
      <Navbar />
      <main className="flex-1">
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/case/:id" element={<CaseDetail />} />
          <Route path="/graph/:id" element={<GraphView />} />
        </Routes>
      </main>
    </div>
  );
}
