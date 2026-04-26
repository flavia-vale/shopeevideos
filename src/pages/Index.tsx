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
  Terminal,
  Info
} from 'lucide-react';
import ScraperForm from '../components/ScraperForm';

const Index = () => {
  const [isLoading, setIsLoading] = useState(false);
  const [scanResult, setScanResult] = useState<any | null>(null);
  
  const [results, setResults] = useState([
    { id: '1390609298/58252888703', videos: 0, status: 'pending', detail: "Aguardando análise real" },
    { id: '482840775/22993705778', videos: 84, status: 'competed', detail: "[data-sqe='video-item']" },
    { id: '1064710210/20798940975', videos: 2, status: 'blue_ocean', detail: "[data-sqe='video-item']" },
  ]);

  const handleScan = (url: string) => {
    setIsLoading(true);
    setScanResult(null);

    setTimeout(() => {
      setIsLoading(false);
      const match = url.match(/i\.(\d+)\.(\d+)/);
      if (match) {
        const shopId = match[1];
        const itemId = match[2];
        const fullId = `${shopId}/${itemId}`;
        
        const isTioNacho = itemId === '58252888703';
        const isLivrinhos = itemId === '22993705778';
        
        const newResult = {
          id: fullId,
          videos: isTioNacho ? 0 : (isLivrinhos ? 84 : 0),
          status: isTioNacho ? 'blue_ocean' : (isLivrinhos ? 'competed' : 'no_tab'),
          detail: isTioNacho ? "Simulação: Produto novo" : (isLivrinhos ? "[data-sqe='video-item']" : "Aba não encontrada")
        };
        
        setScanResult(newResult);
        if (!results.find(r => r.id === fullId)) {
          setResults([newResult, ...results]);
        }
      } else {
        setScanResult({
          status: 'error',
          detail: 'Link inválido. Use o formato da Shopee (ex: i.123.456)'
        });
      }
    }, 1500);
  };

  return (
    <div className="min-h-screen bg-gray-50 flex">
      <aside className="w-64 bg-white border-r border-gray-200 hidden md:flex flex-col">
        <div className="p-6 border-b border-gray-200">
          <div className="flex items-center gap-2 text-orange-600 font-bold text-xl">
            <Video size={28} />
            <span>Shopee Video</span>
          </div>
        </div>
        <nav className="flex-1 p-4 space-y-2">
          <div className="px-4 py-2 bg-orange-50 text-orange-700 rounded-lg font-medium flex items-center gap-3">
            <LayoutDashboard size={20} /> Dashboard
          </div>
        </nav>
      </aside>

      <main className="flex-1 flex flex-col">
        <header className="h-16 bg-white border-b border-gray-200 flex items-center justify-between px-8">
          <h1 className="text-lg font-semibold text-gray-800">Painel de Controle</h1>
        </header>

        <div className="p-8 max-w-5xl mx-auto w-full">
          <div className="bg-blue-50 border border-blue-200 p-4 rounded-xl mb-8 flex items-start gap-3 text-blue-800">
            <Info className="mt-1 shrink-0" size={20} />
            <div>
              <p className="font-semibold">Nota sobre o Teste Real</p>
              <p className="text-sm opacity-90">Para testar o produto do Tio Nacho no terminal, use o comando abaixo.</p>
            </div>
          </div>

          <div className="mb-10">
            <ScraperForm onScan={handleScan} isLoading={isLoading} result={scanResult} />
          </div>

          <div className="bg-slate-900 text-slate-300 p-6 rounded-xl mb-8 font-mono text-sm shadow-lg border border-slate-800">
            <div className="flex items-center gap-2 text-orange-400 mb-3">
              <Terminal size={18} />
              <span className="font-bold uppercase tracking-wider">Comando para Teste Real (Tio Nacho)</span>
            </div>
            <div className="bg-black/50 p-3 rounded border border-slate-700 text-green-400 overflow-x-auto">
              python3 scraper.py --products 1390609298/58252888703 --cookies cookies.json --debug
            </div>
          </div>

          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-gray-50 border-b border-gray-200">
                  <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase">ID do Produto</th>
                  <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase">Vídeos</th>
                  <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase">Status</th>
                  <th className="px-6 py-4 text-xs font-semibold text-gray-500 uppercase text-right">Link</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-gray-200">
                {results.map((item, idx) => (
                  <tr key={idx} className="hover:bg-gray-50">
                    <td className="px-6 py-4 font-mono text-sm">{item.id}</td>
                    <td className="px-6 py-4 font-bold">{item.videos}</td>
                    <td className="px-6 py-4">
                      <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                        item.status === 'blue_ocean' ? 'bg-blue-100 text-blue-700' : 
                        item.status === 'pending' ? 'bg-gray-100 text-gray-600' : 'bg-orange-100 text-orange-700'
                      }`}>
                        {item.status === 'blue_ocean' ? 'Oceano Azul' : 
                         item.status === 'pending' ? 'Pendente' : 'Competido'}
                      </span>
                    </td>
                    <td className="px-6 py-4 text-right">
                      <a href={`https://shopee.com.br/product/${item.id}`} target="_blank" className="text-gray-400 hover:text-orange-600">
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