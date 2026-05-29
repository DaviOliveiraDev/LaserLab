import React from 'react';

export default function OMAViewer({ job }) {
  if (!job) {
    return (
      <div className="oma-viewer-empty">
        <span style={{ opacity: 0.4 }}>[NENHUM TRANSMISSOR OMA SELECIONADO]</span>
      </div>
    );
  }

  const { oma_data, filename } = job;

  if (!oma_data) {
    return (
      <div className="oma-viewer-empty">
        <span style={{ opacity: 0.4 }}>NENHUM DADO OMA REGISTRADO PARA ESTE PEDIDO</span>
      </div>
    );
  }

  // Parse and colorize OMA lines
  const lines = oma_data.split('\n');

  const colorizeLine = (line) => {
    const parts = line.split('=');
    if (parts.length < 2) return <span className="oma-line-raw">{line}</span>;

    const tag = parts[0];
    const value = parts.slice(1).join('=');

    let tagClass = 'oma-tag-default';
    let valueClass = 'oma-value-default';

    if (['JOB', 'REQ', 'LMS'].includes(tag)) {
      tagClass = 'oma-tag-header';
      valueClass = 'oma-value-cyan';
    } else if (['EYE', 'LNAM', 'AXIS', 'ADD', 'LDG'].includes(tag)) {
      tagClass = 'oma-tag-key';
      valueClass = 'oma-value-yellow';
    } else if (tag.startsWith('TRCFMT')) {
      tagClass = 'oma-tag-shape';
      valueClass = 'oma-value-dim';
    }

    return (
      <>
        <span className={tagClass}>{tag}</span>
        <span className="oma-separator">=</span>
        <span className={valueClass}>{value}</span>
      </>
    );
  };

  return (
    <div className="oma-viewer-container">
      <div className="terminal-header">
        <span>💾 TELETRATAMENTO OMA: {filename}</span>
      </div>
      <div className="terminal-body monospace-font">
        {lines.map((line, idx) => {
          if (!line.trim()) return null;
          return (
            <div key={idx} className="oma-viewer-line">
              <span className="oma-line-num">{(idx + 1).toString().padStart(3, '0')} </span>
              {colorizeLine(line)}
            </div>
          );
        })}
      </div>
    </div>
  );
}
