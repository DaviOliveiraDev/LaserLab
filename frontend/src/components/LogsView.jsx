import React from 'react';

export default function LogsView({ logs }) {
  
  const formatTime = (isoString) => {
    try {
      const date = new Date(isoString);
      return date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    } catch {
      return '';
    }
  };

  return (
    <div className="panel-column glass-panel" style={{ flex: 1 }}>
      <div className="panel-header">
        <span>Console do Sistema (Logs)</span>
      </div>
      <div className="panel-body" style={{ padding: '10px' }}>
        <div className="terminal-window">
          {logs.length === 0 ? (
            <div style={{ color: 'var(--text-secondary)' }}>Nenhum log registrado. Aguardando atividade...</div>
          ) : (
            logs.map((log) => (
              <div key={log.id} className={`log-line ${log.level}`}>
                [{formatTime(log.timestamp)}] [{log.level}] {log.message}
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
