import React, { useEffect, useRef } from 'react';

export default function GcodePreview({ gcodeText, currentLineIndex, isStreaming }) {
  const containerRef = useRef(null);
  const activeLineRef = useRef(null);

  const lines = gcodeText ? gcodeText.split('\n') : [];

  useEffect(() => {
    if (activeLineRef.current && isStreaming) {
      activeLineRef.current.scrollIntoView({
        behavior: 'smooth',
        block: 'center',
      });
    }
  }, [currentLineIndex, isStreaming]);

  if (!gcodeText) {
    return (
      <div className="gcode-terminal-empty">
        <span style={{ opacity: 0.4 }}>[NENHUM G-CODE CARREGADO]</span>
      </div>
    );
  }

  return (
    <div className="gcode-terminal-panel">
      <div className="terminal-header">
        <span>🤖 CONSOLE DE EXECUÇÃO G-CODE</span>
        {isStreaming && (
          <span className="terminal-live-badge pulse">
            LIVE: LINHA {currentLineIndex} / {lines.length}
          </span>
        )}
      </div>
      <div className="terminal-body" ref={containerRef}>
        {lines.map((line, idx) => {
          // Adjust for 1-indexed backend line count vs 0-indexed map
          const isActive = isStreaming && idx === (currentLineIndex - 1);
          const isComment = line.trim().startsWith(';') || line.trim().startsWith('(');

          return (
            <div
              key={idx}
              ref={isActive ? activeLineRef : null}
              className={`terminal-line ${isActive ? 'active-gcode' : ''} ${isComment ? 'comment-gcode' : ''}`}
            >
              <span className="line-num">{(idx + 1).toString().padStart(4, '0')}</span>
              <span className="line-pointer">{isActive ? '► ' : '  '}</span>
              <span className="line-text">{line}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}
