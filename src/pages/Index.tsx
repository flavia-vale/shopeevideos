import React, { useState } from 'react';
import { 
  LayoutDashboard, 
  Video, 
  Search, 
  AlertCircle, 
  CheckCircle2, 
  ExternalLink,
  BarChart3,
  Settings
} from 'lucide-react';

const Index = () => {
  // Dados de exemplo baseados no que o seu scraper produz
  const [results] = useState([
    { id: '1064710210/20798940975', videos: 2, status: 'blue_ocean', detail: "[data-sqe='video-item']" },
    { id: '123456789/234567890', videos: 15, status: 'competed', detail: "[data-sqe='video-item']" },
    { id: '345678901/456789012', videos: null, status: 'error', detail: "timeout ao navegar" },
    { id: '111111111/222222222', videos: 0, status: 'no_tab', detail: "aba não encontrada" },
  ]);

  const getStatusBadge = (status: string) => {
    switch (status) {
      case 'blue_ocean':
        return <span className="px-2 py-1 text-xs font-medium bg-blue-100 text-blue-700 rounded-full flex items-center gap-1"><CheckCircle2 size={12} /> Oceano Azul</span>;
      case 'competed':
        return <span className="px-2 py-1 text-xs font-medium bg-orange-100 text-orange-700 rounded-full flex items-center gap-1"><BarChart3 size={12} /> Competido</span>;
      case 'error':
        return <span className="px-2 py-1 text-xs font-medium bg-red-100 text-red-700 rounded-full flex items-center gap-1"><AlertCircle size={12} /> Erro</span>;
      default:
        return <span className="px-2 py-1 text-xs font-medium bg-gray-100 text-gray-700 rounded-full">Sem Aba</span>;
    }
  };

  return (
    <div className="min-h-screen bg-gray-50 flex">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-gray-200 hidden md:flex flex-col">
        <div className="p-6 border-b border-gray-200">
          <div className="flex items-center gap-2 text-orange-600 font-bold text-xl">
            <Video size={28} />
            <span>Shopee Video</span>
          </div>
        </div>
        <nav className="flex-1 p-4 space-y-2">
          <a href="#" className="flex items-center gap-3 px-4 py-2 bg-orange-50 text-orange-700 rounded-lg font-medium">
            <LayoutDashboard size={20} /> Dashboard
          </a>
          <a href="#" className="flex items-center gap-3 px-4 py-2 text-gray-600 hover:bg-gray-50 rounded-lg transition-colors">
            <Search size={20} /> Scraper
          </a>
          <a href="#" className="flex items-center gap-3 px-4 py-2 text-gray-600 hover:bg-gray-50 rounded-lg transition-colors">
            <Settings size={20} /> Configurações
          </a>
        </nav>
      </aside>

      {/* Main Content */}
      <main className="flex-1 flex flex-col">
        <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-8">
          <h1 className="text-lg font-semibold text-gray-800">Resultados do Scraper</h1>
          <div className="flex items-center gap-4">
            <button className="bg-orange-600 text-white px-4 py-2 rounded-lg text-sm font-medium hover:bg-orange-700 transition-colors">
              Novo Scan
            </button>
          </div>
        </header>

        <div className="p-8">
          {/* Stats */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8">
            <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
              <p className="text-sm text-gray-500 mb-1">Total Processado</p>
              <p className="text-2xl font-bold text-gray-900">{results.length}</p>
            </div>
            <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
              <p className="text-sm text-gray-500 mb-1 text-blue-600">Oceanos Azuis</p>
              <p className="text-2xl font-bold text-gray-900">{results.filter(r => r.status === 'blue_ocean').length}</p>
            </div>
            <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
              <p className="text-sm text-gray-500 mb-1 text-red-600">Erros</p>
              <p className="text-2xl font-bold text-gray-900">{results.filter(r => r.status === 'error').length}</p>
            </div>
          </div>

          {/* Table */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">ID do Produto</th>
                  <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Vídeos</th>
                  <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
                  <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Detalhe</th>
                  <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider text-right">Ação</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {results.map((item, idx) => (
                  <tr key={idx} className="hover:bg-gray-50 transition-colors">
                    <td className="px-6 py-4 font-mono text-sm text-gray-600">{item.id}</td>
                    <td className="px-6 py-4">
                      <span className="font-semibold text-gray-900">{item.videos ?? 'N/A'}</span>
                    </td>
                    <td className="px-6 py-4">
                      {getStatusBadge(item.status)}
                    </td>
                    <td className="px-6 py-4 text-sm text-gray-500">
                      {item.detail}
                    </td>
                    <td className="px-6 py-4 text-right">
                      <a 
                        href={`https://shopee.com.br/product/${item.id}`} 
                        target="_blank" 
                        rel="noopener noreferrer"
                        className="text-gray-400 hover:text-orange-600 transition-colors"
                      >
                        <ExternalLink size={18} />
                      </a>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </main>
    </div>
  );
};

export default Index;