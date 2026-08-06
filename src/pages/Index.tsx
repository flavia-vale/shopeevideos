import { useEffect, useMemo, useState } from 'react';
import {
  AlertTriangle,
  Compass,
  Download,
  ExternalLink,
  Loader2,
  Search,
} from 'lucide-react';

type Result = {
  entry: string;
  shop_id: number | null;
  item_id: number | null;
  sales: number | null;
  affiliates: number | null;
  ratio: number | null;
  status: string;
  error: string | null;
};

type Health = {
  cookies_present: boolean;
  cookies_ok: boolean;
  endpoint_configured: boolean;
};

const STATUS_LABEL: Record<string, string> = {
  blue_ocean: 'Oceano Azul',
  competed: 'Competido',
  low_demand: 'Pouca venda',
  no_data: 'Sem dado de afiliados',
  expired: 'Cookies expirados',
  error: 'Erro',
};

const STATUS_STYLE: Record<string, string> = {
  blue_ocean: 'bg-blue-100 text-blue-700',
  competed: 'bg-orange-100 text-orange-700',
  low_demand: 'bg-gray-100 text-gray-600',
  no_data: 'bg-amber-100 text-amber-700',
  expired: 'bg-red-100 text-red-700',
  error: 'bg-red-100 text-red-700',
};

const PLACEHOLDER = `Cole um link por linha:

https://s.shopee.com.br/4LILktFNEi
https://shopee.com.br/nome-do-produto-i.123456.7890123
303419140/57563387424`;

const Index = () => {
  const [links, setLinks] = useState('');
  const [minSales, setMinSales] = useState(100);
  const [maxAffiliates, setMaxAffiliates] = useState(50);
  const [results, setResults] = useState<Result[]>([]);
  const [jobId, setJobId] = useState<string | null>(null);
  const [progress, setProgress] = useState({ done: 0, total: 0 });
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [health, setHealth] = useState<Health | null>(null);

  useEffect(() => {
    fetch('/api/status')
      .then((r) => r.json())
      .then(setHealth)
      .catch(() => setHealth(null));
  }, []);

  // Enquanto o job roda, busca o progresso a cada 2s.
  useEffect(() => {
    if (!jobId) return;

    const timer = setInterval(async () => {
      try {
        const res = await fetch(`/api/scan/${jobId}`);
        const job = await res.json();
        setResults(job.results ?? []);
        setProgress({ done: job.done ?? 0, total: job.total ?? 0 });

        if (job.status !== 'running') {
          setRunning(false);
          setJobId(null);
          if (job.error) setError(job.error);
        }
      } catch {
        setError('Perdi contato com o servidor. Ele ainda está rodando?');
        setRunning(false);
        setJobId(null);
      }
    }, 2000);

    return () => clearInterval(timer);
  }, [jobId]);

  const lineCount = links.split('\n').filter((l) => l.trim() && !l.startsWith('#')).length;

  const startScan = async () => {
    setError(null);
    setResults([]);
    setRunning(true);

    try {
      const res = await fetch('/api/scan', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ links, min_sales: minSales, max_affiliates: maxAffiliates }),
      });
      const data = await res.json();

      if (!res.ok) throw new Error(data.error ?? 'Falha ao iniciar a varredura');

      setJobId(data.job_id);
      setProgress({ done: 0, total: data.total });
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setRunning(false);
    }
  };

  // Melhor razão primeiro: é a ordem em que vale a pena olhar os achados.
  const sorted = useMemo(
    () => [...results].sort((a, b) => (b.ratio ?? -1) - (a.ratio ?? -1)),
    [results],
  );

  const blueOceans = sorted.filter((r) => r.status === 'blue_ocean').length;

  const downloadCsv = () => {
    const header = 'produto,vendas,afiliados,vendas_por_afiliado,status,erro';
    const rows = sorted.map((r) =>
      [
        r.shop_id ? `${r.shop_id}/${r.item_id}` : r.entry,
        r.sales ?? '',
        r.affiliates ?? '',
        r.ratio ?? '',
        r.status,
        `"${(r.error ?? '').replace(/"/g, "'")}"`,
      ].join(','),
    );

    const blob = new Blob([[header, ...rows].join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `oceanos-azuis-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-5xl mx-auto px-6 h-16 flex items-center gap-2 text-orange-600 font-bold text-lg">
          <Compass size={24} />
          <span>Oceano Azul Shopee</span>
          <span className="text-gray-400 font-normal text-sm ml-2">vendas x afiliados</span>
        </div>
      </header>

      <main className="max-w-5xl mx-auto px-6 py-8 space-y-6">
        {health && !health.endpoint_configured && (
          <div className="bg-amber-50 border border-amber-200 text-amber-800 p-4 rounded-xl flex gap-3">
            <AlertTriangle size={20} className="shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="font-semibold">Endpoint de afiliados ainda não configurado</p>
              <p className="opacity-90">
                Sem o <code>endpoints.json</code> a contagem de afiliados pode vir vazia
                (status "Sem dado de afiliados"). Capture o tráfego do app e rode{' '}
                <code>find_affiliate_field.py</code> — o passo a passo está no
                ABORDAGEM_AFILIADOS.md.
              </p>
            </div>
          </div>
        )}

        {health && !health.cookies_ok && (
          <div className="bg-red-50 border border-red-200 text-red-800 p-4 rounded-xl flex gap-3">
            <AlertTriangle size={20} className="shrink-0 mt-0.5" />
            <div className="text-sm">
              <p className="font-semibold">
                {health.cookies_present ? 'Cookies sem sessão válida' : 'cookies.json não encontrado'}
              </p>
              <p className="opacity-90">
                Exporte a sessão da Shopee do navegador para <code>cookies.json</code> na raiz do
                projeto, senão toda varredura volta com 403.
              </p>
            </div>
          </div>
        )}

        <div className="bg-white p-6 rounded-xl border border-gray-200 shadow-sm space-y-4">
          <h2 className="font-semibold text-gray-800 flex items-center gap-2">
            <Search size={18} className="text-orange-600" />
            Produtos para analisar
          </h2>

          <textarea
            value={links}
            onChange={(e) => setLinks(e.target.value)}
            placeholder={PLACEHOLDER}
            rows={8}
            disabled={running}
            className="w-full px-4 py-3 border border-gray-300 rounded-lg font-mono text-sm outline-none focus:ring-2 focus:ring-orange-500 focus:border-orange-500 disabled:bg-gray-50"
          />

          <div className="flex flex-wrap items-end gap-4">
            <label className="text-sm">
              <span className="block text-gray-600 mb-1">Vendas mínimas</span>
              <input
                type="number"
                min={0}
                value={minSales}
                onChange={(e) => setMinSales(Number(e.target.value))}
                disabled={running}
                className="w-28 px-3 py-2 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-orange-500"
              />
            </label>

            <label className="text-sm">
              <span className="block text-gray-600 mb-1">Máx. de afiliados</span>
              <input
                type="number"
                min={0}
                value={maxAffiliates}
                onChange={(e) => setMaxAffiliates(Number(e.target.value))}
                disabled={running}
                className="w-28 px-3 py-2 border border-gray-300 rounded-lg outline-none focus:ring-2 focus:ring-orange-500"
              />
            </label>

            <button
              onClick={startScan}
              disabled={running || lineCount === 0}
              className="ml-auto bg-orange-600 text-white px-6 py-2 rounded-lg font-medium hover:bg-orange-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
            >
              {running ? (
                <>
                  <Loader2 size={18} className="animate-spin" />
                  {progress.done}/{progress.total}
                </>
              ) : (
                `Analisar ${lineCount || ''} ${lineCount === 1 ? 'produto' : 'produtos'}`
              )}
            </button>
          </div>

          {running && (
            <div className="space-y-1">
              <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className="h-full bg-orange-500 transition-all duration-500"
                  style={{
                    width: `${progress.total ? (progress.done / progress.total) * 100 : 0}%`,
                  }}
                />
              </div>
              <p className="text-xs text-gray-500">
                Uma pausa de 2s entre produtos evita o bloqueio anti-bot. Pode deixar rodando.
              </p>
            </div>
          )}

          {error && <p className="text-sm text-red-600">{error}</p>}
        </div>

        {sorted.length > 0 && (
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-200 flex items-center justify-between">
              <p className="text-sm text-gray-600">
                {sorted.length} analisados ·{' '}
                <span className="font-semibold text-blue-700">{blueOceans} oceanos azuis</span>
              </p>
              <button
                onClick={downloadCsv}
                className="text-sm text-gray-600 hover:text-orange-600 flex items-center gap-1.5"
              >
                <Download size={16} /> CSV
              </button>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-left border-collapse">
                <thead>
                  <tr className="bg-gray-50 border-b border-gray-200 text-xs font-semibold text-gray-500 uppercase">
                    <th className="px-6 py-3">Produto</th>
                    <th className="px-6 py-3 text-right">Vendas</th>
                    <th className="px-6 py-3 text-right">Afiliados</th>
                    <th className="px-6 py-3 text-right">Vendas/afiliado</th>
                    <th className="px-6 py-3">Status</th>
                    <th className="px-6 py-3" />
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-200 text-sm">
                  {sorted.map((r, i) => (
                    <tr
                      key={`${r.entry}-${i}`}
                      className={r.status === 'blue_ocean' ? 'bg-blue-50/50' : 'hover:bg-gray-50'}
                    >
                      <td className="px-6 py-3 font-mono text-xs">
                        {r.shop_id ? `${r.shop_id}/${r.item_id}` : r.entry}
                        {r.error && <p className="text-red-600 font-sans mt-1">{r.error}</p>}
                      </td>
                      <td className="px-6 py-3 text-right">{r.sales ?? '—'}</td>
                      <td className="px-6 py-3 text-right">{r.affiliates ?? '—'}</td>
                      <td className="px-6 py-3 text-right font-bold">
                        {r.ratio != null ? r.ratio.toFixed(2) : '—'}
                      </td>
                      <td className="px-6 py-3">
                        <span
                          className={`px-2 py-1 rounded-full text-xs font-medium whitespace-nowrap ${
                            STATUS_STYLE[r.status] ?? 'bg-gray-100 text-gray-600'
                          }`}
                        >
                          {STATUS_LABEL[r.status] ?? r.status}
                        </span>
                      </td>
                      <td className="px-6 py-3 text-right">
                        {r.shop_id && (
                          <a
                            href={`https://shopee.com.br/product/${r.shop_id}/${r.item_id}`}
                            target="_blank"
                            rel="noreferrer"
                            className="text-gray-400 hover:text-orange-600 inline-block"
                          >
                            <ExternalLink size={16} />
                          </a>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </main>
    </div>
  );
};

export default Index;
