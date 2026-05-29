import React, { useState, useEffect } from 'react';

export default function TemplateManager({ backendUrl, onEditTemplate, onCreateTemplate }) {
  const [templates, setTemplates] = useState([]);
  const [search, setSearch] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  // History Audit Sidebar state
  const [selectedTemplateForHistory, setSelectedTemplateForHistory] = useState(null);
  const [historyLogs, setHistoryLogs] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);

  const fetchTemplates = () => {
    setLoading(true);
    setError(null);
    const url = search 
      ? `${backendUrl}/api/templates?search=${encodeURIComponent(search)}` 
      : `${backendUrl}/api/templates`;

    fetch(url)
      .then((res) => {
        if (!res.ok) throw new Error('Falha ao buscar templates.');
        return res.json();
      })
      .then((data) => {
        setTemplates(data);
        setLoading(false);
      })
      .catch((err) => {
        console.error(err);
        setError(err.message);
        setLoading(false);
      });
  };

  useEffect(() => {
    fetchTemplates();
  }, [search]);

  // Load audit history for a single template
  const viewHistory = (template) => {
    setSelectedTemplateForHistory(template);
    setLoadingHistory(true);
    setHistoryLogs([]);

    fetch(`${backendUrl}/api/templates/${template.id}/history`)
      .then((res) => {
        if (!res.ok) throw new Error('Erro ao buscar histórico.');
        return res.json();
      })
      .then((data) => {
        setHistoryLogs(data);
        setLoadingHistory(false);
      })
      .catch((err) => {
        console.error(err);
        setLoadingHistory(false);
      });
  };

  // Toggle template status
  const handleToggle = (id) => {
    fetch(`${backendUrl}/api/templates/${id}/toggle`, { method: 'POST' })
      .then((res) => {
        if (!res.ok) throw new Error('Erro ao alterar status.');
        return res.json();
      })
      .then(() => {
        fetchTemplates();
        if (selectedTemplateForHistory?.id === id) {
          // Refresh history if open
          viewHistory(selectedTemplateForHistory);
        }
      })
      .catch((err) => alert(err.message));
  };

  // Duplicate template
  const handleDuplicate = (id) => {
    fetch(`${backendUrl}/api/templates/${id}/duplicate`, { method: 'POST' })
      .then((res) => {
        if (!res.ok) throw new Error('Erro ao duplicar template.');
        return res.json();
      })
      .then(() => {
        fetchTemplates();
      })
      .catch((err) => alert(err.message));
  };

  const getActionLabelColor = (action) => {
    switch (action) {
      case 'CREATE': return 'var(--green-glow)';
      case 'UPDATE': return 'var(--cyan-glow)';
      case 'DUPLICATE': return '#a855f7'; // Purple
      case 'ACTIVATE': return 'var(--green-glow)';
      case 'DEACTIVATE': return 'var(--red-glow)';
      default: return '#fff';
    }
  };

  return (
    <div className="template-manager-layout" style={{ display: 'grid', gridTemplateColumns: selectedTemplateForHistory ? '1fr 360px' : '1fr', gap: '16px', height: '100%', minHeight: 0 }}>
      {/* List Panel */}
      <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div className="panel-header">
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <span>BANCO DE TEMPLATES LENS</span>
            <span className="status-badge online" style={{ fontSize: '0.65rem', padding: '2px 8px' }}>
              {templates.length} Registrados
            </span>
          </div>
          <button className="btn btn-cyan" onClick={onCreateTemplate} style={{ flex: 'none', padding: '6px 12px', fontSize: '0.75rem' }}>
            + Novo Template
          </button>
        </div>

        {/* Search & Filter Bar */}
        <div style={{ padding: '12px 16px', borderBottom: '1px solid var(--border-glass)', display: 'flex', gap: '12px' }}>
          <input
            type="text"
            className="form-input"
            placeholder="Pesquisar por modelo, fabricante ou tipo..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            style={{ flex: 1, background: '#090d16' }}
          />
          <button className="btn btn-glass" onClick={fetchTemplates} style={{ flex: 'none', padding: '8px' }}>
            🔄
          </button>
        </div>

        {/* Templates Table Container */}
        <div style={{ flex: 1, overflowY: 'auto', padding: '16px' }}>
          {loading && <div className="empty-state"><h3>Buscando base de dados...</h3></div>}
          {error && <div className="empty-state"><h3 style={{ color: 'var(--red-glow)' }}>{error}</h3></div>}
          
          {!loading && !error && templates.length === 0 && (
            <div className="empty-state">
              <svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1" strokeLinecap="round" strokeLinejoin="round">
                <rect width="18" height="18" x="3" y="3" rx="2" />
                <path d="M9 17h6" />
                <path d="M9 12h6" />
                <path d="M9 7h6" />
              </svg>
              <h3>Nenhum Template Encontrado</h3>
              <p>Crie um novo template geométrico ou ajuste os termos de busca.</p>
            </div>
          )}

          {!loading && !error && templates.length > 0 && (
            <table className="cnc-table" style={{ width: '100%', borderCollapse: 'collapse', fontFamily: 'monospace', fontSize: '0.8rem', textAlign: 'left' }}>
              <thead>
                <tr style={{ borderBottom: '2px solid var(--cyan-fade)', color: 'var(--text-secondary)', textTransform: 'uppercase', fontSize: '0.7rem' }}>
                  <th style={{ padding: '10px 8px' }}>Status</th>
                  <th style={{ padding: '10px 8px' }}>Modelo da Lente</th>
                  <th style={{ padding: '10px 8px' }}>Fabricante</th>
                  <th style={{ padding: '10px 8px' }}>Tipo</th>
                  <th style={{ padding: '10px 8px', textAlign: 'center' }}>Offset X / Y</th>
                  <th style={{ padding: '10px 8px', textAlign: 'center' }}>Rotação</th>
                  <th style={{ padding: '10px 8px', textAlign: 'center' }}>Cruz M.</th>
                  <th style={{ padding: '10px 8px', textAlign: 'center' }}>Ref Pt</th>
                  <th style={{ padding: '10px 8px', textAlign: 'right' }}>Ações</th>
                </tr>
              </thead>
              <tbody>
                {templates.map((tpl) => (
                  <tr key={tpl.id} className="cnc-row" style={{ borderBottom: '1px solid var(--border-glass)', transition: 'background 0.2s' }}>
                    <td style={{ padding: '12px 8px' }}>
                      <span 
                        onClick={() => handleToggle(tpl.id)}
                        className={`status-badge ${tpl.is_active === 1 ? 'online' : 'offline'}`}
                        style={{ cursor: 'pointer', display: 'inline-flex', padding: '2px 8px', fontSize: '0.65rem' }}
                      >
                        <span className={`dot ${tpl.is_active === 1 ? 'pulse' : ''}`} />
                        {tpl.is_active === 1 ? 'Ativo' : 'Inativo'}
                      </span>
                    </td>
                    <td style={{ padding: '12px 8px', fontWeight: 'bold', color: '#fff' }}>
                      {tpl.name}
                    </td>
                    <td style={{ padding: '12px 8px', color: 'var(--text-secondary)' }}>{tpl.manufacturer}</td>
                    <td style={{ padding: '12px 8px', color: 'var(--text-secondary)' }}>{tpl.lens_type}</td>
                    <td style={{ padding: '12px 8px', textAlign: 'center', color: 'var(--cyan-glow)' }}>
                      {tpl.offset_x > 0 ? `+${tpl.offset_x.toFixed(2)}` : tpl.offset_x.toFixed(2)} / {tpl.offset_y > 0 ? `+${tpl.offset_y.toFixed(2)}` : tpl.offset_y.toFixed(2)} mm
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'center', color: 'var(--orange-glow)' }}>
                      {tpl.rotation > 0 ? `+${tpl.rotation.toFixed(1)}` : tpl.rotation.toFixed(1)}°
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'center', color: '#eab308' }}>
                      +{tpl.fitting_cross_dist.toFixed(1)} mm
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'center', fontWeight: 'bold' }}>
                      <span style={{ border: '1px solid var(--border-glass)', padding: '2px 4px', borderRadius: '4px', background: 'rgba(255,255,255,0.03)' }}>
                        {tpl.reference_point}
                      </span>
                    </td>
                    <td style={{ padding: '12px 8px', textAlign: 'right' }}>
                      <div style={{ display: 'inline-flex', gap: '6px' }}>
                        <button 
                          className="btn btn-glass" 
                          onClick={() => viewHistory(tpl)} 
                          style={{ padding: '4px 8px', fontSize: '0.7rem' }}
                          title="Visualizar Auditoria de Operações"
                        >
                          📜 Histórico
                        </button>
                        <button 
                          className="btn btn-glass" 
                          onClick={() => handleDuplicate(tpl.id)} 
                          style={{ padding: '4px 8px', fontSize: '0.7rem' }}
                          title="Duplicar Configurações"
                        >
                          👥 Duplicar
                        </button>
                        <button 
                          className="btn btn-cyan" 
                          onClick={() => onEditTemplate(tpl)} 
                          style={{ padding: '4px 10px', fontSize: '0.7rem', color: '#000' }}
                        >
                          Editar
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* History Audit Sidebar */}
      {selectedTemplateForHistory && (
        <div className="glass-panel" style={{ display: 'flex', flexDirection: 'column', minHeight: 0, borderLeft: '2px solid var(--cyan-fade)' }}>
          <div className="panel-header" style={{ borderBottom: '1px solid var(--cyan-fade)' }}>
            <span style={{ fontSize: '0.75rem', letterSpacing: '0.5px' }}>AUDITORIA DE MODIFICAÇÕES</span>
            <button 
              onClick={() => setSelectedTemplateForHistory(null)} 
              style={{ background: 'none', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', fontSize: '1rem' }}
            >
              ✕
            </button>
          </div>

          <div style={{ padding: '12px 16px', background: 'rgba(9, 13, 22, 0.5)', borderBottom: '1px solid var(--border-glass)' }}>
            <h4 style={{ fontSize: '0.8rem', color: '#fff', marginBottom: '4px' }}>{selectedTemplateForHistory.name}</h4>
            <p style={{ fontSize: '0.7rem', color: 'var(--text-secondary)' }}>Fabricante: {selectedTemplateForHistory.manufacturer}</p>
          </div>

          {/* Change log container */}
          <div style={{ flex: 1, overflowY: 'auto', padding: '16px', display: 'flex', flexDirection: 'column', gap: '12px', background: '#05070a', fontFamily: 'monospace' }}>
            {loadingHistory && <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)' }}>Carregando log de auditoria...</p>}
            
            {!loadingHistory && historyLogs.length === 0 && (
              <p style={{ fontSize: '0.75rem', color: 'var(--text-secondary)', textAlign: 'center', marginTop: '24px' }}>
                Nenhum log registrado para este template.
              </p>
            )}

            {!loadingHistory && historyLogs.map((log) => (
              <div 
                key={log.id} 
                style={{ 
                  padding: '10px', 
                  borderRadius: '6px', 
                  border: '1px solid var(--border-glass)', 
                  background: 'rgba(15, 23, 42, 0.4)',
                  fontSize: '0.7rem',
                  lineHeight: '1.4'
                }}
              >
                <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '6px' }}>
                  <span style={{ fontWeight: 'bold', color: getActionLabelColor(log.action), border: `1px solid ${getActionLabelColor(log.action)}`, padding: '1px 4px', borderRadius: '3px', fontSize: '0.55rem' }}>
                    {log.action}
                  </span>
                  <span style={{ color: 'var(--text-secondary)', fontSize: '0.65rem' }}>
                    {new Date(log.timestamp).toLocaleString('pt-BR')}
                  </span>
                </div>

                {/* Changed fields diff parser */}
                {log.changed_fields && (
                  <div style={{ marginTop: '6px', color: '#94a3b8', fontSize: '0.65rem' }}>
                    {log.action === 'UPDATE' ? (
                      Object.entries(log.changed_fields).map(([key, val]) => (
                        <div key={key} style={{ marginTop: '2px' }}>
                          • <strong style={{ color: '#cbd5e1' }}>{key}</strong>: 
                          <span style={{ color: 'var(--red-glow)', textDecoration: 'line-through', marginLeft: '4px' }}>{String(val[0])}</span> 
                          <span style={{ color: 'var(--green-glow)', marginLeft: '4px' }}>➔ {String(val[1])}</span>
                        </div>
                      ))
                    ) : log.action === 'CREATE' ? (
                      <div>
                        {Object.entries(log.changed_fields).map(([key, val]) => (
                          <div key={key}>• {key}: {String(val)}</div>
                        ))}
                      </div>
                    ) : log.action === 'DUPLICATE' ? (
                      <div>
                        Duplicado de ID: <strong style={{ color: '#fff' }}>{log.changed_fields.source_template_id}</strong> ({log.changed_fields.source_template_name})
                      </div>
                    ) : (
                      <div>
                        {Object.entries(log.changed_fields).map(([key, val]) => (
                          <div key={key}>• {key}: {String(val)}</div>
                        ))}
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
