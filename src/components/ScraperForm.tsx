"use client";

import React, { useState } from 'react';
import { Search, Loader2, AlertCircle, CheckCircle2, Video } from 'lucide-react';

interface ScraperFormProps {
  onScan: (url: string) => void;
  isLoading: boolean;
  result: any | null;
}

const ScraperForm = ({ onScan, isLoading, result }: ScraperFormProps) => {
  const [url, setUrl] = useState('');

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (url.trim()) {
      onScan(url);
    }
  };

  return (
    <div className="space-y-6">
      <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm">
        <h2 className="text-lg font-semibold text-gray-800 mb-4 flex items-center gap-2">
          <Search size={20} className="text-orange-600" />
          Analisar Novo Produto
        </h2>
        <form onSubmit={handleSubmit} className="flex flex-col md:flex-row gap-3">
          <input
            type="text"
            placeholder="Cole o link do produto Shopee aqui..."
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-orange-500 focus:border-orange-500 outline-none transition-all"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            disabled={isLoading}
          />
          <button
            type="submit"
            disabled={isLoading || !url.trim()}
            className="bg-orange-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-orange-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2 min-w-[140px]"
          >
            {isLoading ? (
              <>
                <Loader2 size={18} className="animate-spin" />
                Analisando...
              </>
            ) : (
              'Analisar'
            )}
          </button>
        </form>
        <p className="mt-2 text-xs text-gray-500">
          Ex: https://shopee.com.br/nome-do-produto-i.SHOPID.ITEMID
        </p>
      </div>

      {result && (
        <div className={`p-6 rounded-xl border animate-in fade-in slide-in-from-top-4 duration-300 ${
          result.status === 'error' ? 'bg-red-50 border-red-200' : 'bg-blue-50 border-blue-200'
        }`}>
          <div className="flex items-start gap-4">
            <div className={`p-2 rounded-full ${
              result.status === 'error' ? 'bg-red-100 text-red-600' : 'bg-blue-100 text-blue-600'
            }`}>
              {result.status === 'error' ? <AlertCircle size={24} /> : <CheckCircle2 size={24} />}
            </div>
            <div className="flex-1">
              <h3 className={`font-bold text-lg ${
                result.status === 'error' ? 'text-red-800' : 'text-blue-800'
              }`}>
                {result.status === 'error' ? 'Falha na Análise' : 'Análise Concluída'}
              </h3>
              
              {result.status !== 'error' ? (
                <div className="mt-2 space-y-2">
                  <div className="flex items-center gap-2 text-blue-700">
                    <Video size={18} />
                    <span className="font-medium">Vídeos encontrados:</span>
                    <span className="text-2xl font-black">{result.videos}</span>
                  </div>
                  <p className="text-blue-600 text-sm">
                    Status: <span className="font-bold uppercase">{result.status === 'blue_ocean' ? 'Oceano Azul 🎯' : 'Competido ❌'}</span>
                  </p>
                  <p className="text-xs text-blue-500 italic">Seletor: {result.detail}</p>
                </div>
              ) : (
                <p className="mt-1 text-red-700">{result.detail}</p>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
};

export default ScraperForm;