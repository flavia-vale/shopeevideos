"use client";

import React, { useState } from 'react';
import { 
  LayoutDashboard, 
  Video, 
  Search, 
  AlertCircle, 
  CheckCircle2, 
  ExternalLink,
  BarChart3,
  Settings,
  Terminal
} from 'lucide-react';
import ScraperForm from '../components/ScraperForm';

const Index = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [scanResult, setScanResult] = useState<any | null>(null);
  
  const [results, setResults] = useState([
    { id: '1064710210/20798940975', videos: 2, status: 'blue_ocean', detail: "[data-sqe='video-item']" },
    { id: '123456789/234567890', videos: 15, status: 'competed', detail: "[data-sqe='video-item']" },
  ]);

  const handleScan = (url: string) => {
    setIsLoading(true);
    setScanResult(null);

    // Simulação da chamada ao backend Python
    // Em um ambiente real, aqui faríamos um fetch para uma API que roda o scraper.py
    setTimeout(() => {
      setIsLoading(false);
      
      // Lógica para extrair IDs do link fornecido pelo usuário
      // Ex: https://shopee.com.br/...-i.482840775.22993705778
      const match = url.match(/i\.(\d+)\.(\d+)/);
      if (match) {
        const shopId = match[1];
        const itemId = match[2];
        const fullId = `${shopId}/${itemId}`;
        
        // Resultado simulado para o produto específico solicitado
        const newResult = {
          id: fullId,
          videos: 4, // Exemplo para o produto de livrinhos
          status: 'blue_ocean',
          detail: "[data-sqe='video-item']"
        };
        
        setScanResult(newResult);
        setResults([newResult, ...results]);
      } else {
        setScanResult({
          status: 'error',
          detail: 'Link inválido. Certifique-se de que o link contém o ID do produto (ex: i.123.456)'
        });
      }
    }, 2000);
  };

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
          <h1 className="text-lg font-semibold text-gray-800">Painel de Controle</h1>
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2 text-xs font-medium text-green-600 bg-green-50 px-3 py-1 rounded-full border border-green-100">
              <div className="w-2 h-2 bg-green-500 rounded-full animate-pulse"></div>
              Sistema Online
            </div>
          </div>
        </header>

        <div className="p-8 max-w-5xl mx-auto w-full">
          {/* Scraper Section */}
          <div className="mb-10">
            <ScraperForm onScan={handleScan} isLoading={isLoading} result={scanResult} />
          </div>

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
              <p className="text-sm text-gray-500 mb-1 text-orange-600">Competidos</p>
              <p className="text-2xl font-bold text-gray-900">{results.filter(r => r.status === 'competed').length}</p>
            </div>
          </div>

          {/* Instructions for Real Test */}
          <div className="bg-slate-900 text-slate-300 p-6 rounded-xl mb-8 font-mono text-sm shadow-lg border border-slate-800">
            <div className="flex items-center gap-2 text-orange-400 mb-3">
              <Terminal size={18} />
              <span className="font-bold uppercase tracking-wider">Executar Teste Real no Terminal</span>
            </div>
            <p className="mb-4 text-slate-400">Para rodar o scraper real com o link que você forneceu, execute este comando no terminal abaixo:</p>
            <div className="bg-black/50 p-3 rounded border border-slate-700 text-green-400 overflow-x-auto">
              python3 scraper.py --products 482840775/22993705778 --cookies cookies.json
            </div>
          </div>

          {/* Table */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200 bg-gray-50/50">
              <h3 className="font-semibold text-gray-700">Histórico de Varredura</h3>
            </div>
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">ID do Produto</th>
                  <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Vídeos</th>
                  <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
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